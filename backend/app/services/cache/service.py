"""The four-layer cache (sections 17, 18, 19, 44).

    EXACT    -> Redis          hot, TTL-based, fast, NOT the source of truth
    SEMANTIC -> PostgreSQL     pgvector, partition-filtered, guard-protected
    ARCHIVE  -> archive_refs   SerpApi Searches Archive, costs no credit
    LIVE     -> SerpApi        the only layer that spends

Two entry points, and the difference between them is the product thesis:

* ``inspect`` answers "is this step satisfiable without spending?" *before* the
  plan is chosen. The planner calls it for every step of every candidate, which
  is what makes marginal cost a real number rather than a post-hoc observation.
* ``lookup`` is what the executor calls when it is about to run a step.

Executor-level caching alone would not satisfy section 14. The planner has to
know the cache state at ranking time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.caching import ArchiveRef, CacheEntry, SemanticGuardRejection
from app.integrations.llm.base import freshness_max_age_seconds
from app.integrations.llm.embedding import embed
from app.services.cache import guard
from app.services.cache.keys import CacheKey, build_key, is_identifier_lookup
from app.services.cache.redis_client import hot_delete_pattern, hot_get, hot_set, hot_ttl
from app.services.cache.ttl import TTLDecision, top_results_digest

log = get_logger("serpflow.cache")

LAYER_EXACT = "exact"
LAYER_SEMANTIC = "semantic"
LAYER_ARCHIVE = "archive"
LAYER_LIVE = "live"
LAYER_MISS = "miss"


@dataclass(slots=True)
class CacheState:
    """What the planner needs to know about one step, before executing it."""

    layer: str = LAYER_MISS
    available: bool = False
    # Available is not the same as acceptable. A warm entry only counts toward
    # marginal savings when it also satisfies the step's freshness requirement.
    acceptable: bool = False
    freshness_requirement: str = "stable"
    age_seconds: int | None = None
    ttl_remaining: int | None = None
    ttl_source: str | None = None
    similarity: float | None = None
    matched_query: str | None = None
    cache_entry_id: str | None = None
    archive_search_id: str | None = None
    payload_ref: str | None = None
    reason: str = "no cached entry for this request"
    guard_rejections: int = 0
    lookup_ms: float = 0.0

    @property
    def is_warm(self) -> bool:
        """Warm means free AND fresh enough to use."""
        return self.available and self.acceptable

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "available": self.available,
            "acceptable": self.acceptable,
            "warm": self.is_warm,
            "freshness_requirement": self.freshness_requirement,
            "age_seconds": self.age_seconds,
            "ttl_remaining": self.ttl_remaining,
            "ttl_source": self.ttl_source,
            "similarity": self.similarity,
            "matched_query": self.matched_query,
            "cache_entry_id": self.cache_entry_id,
            "archive_search_id": self.archive_search_id,
            "reason": self.reason,
            "guard_rejections": self.guard_rejections,
            "lookup_ms": round(self.lookup_ms, 3),
        }


@dataclass(slots=True)
class CacheHit:
    """A resolved hit with its payload, returned to the executor."""

    state: CacheState
    payload: dict[str, Any] | None = None
    entry: CacheEntry | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class CacheService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        org_id: str,
        project_id: str,
        scope: str | None = None,
        semantic_threshold: float | None = None,
    ) -> None:
        self.session = session
        self.org_id = org_id
        self.project_id = project_id
        self.scope = scope or settings.cache_partition_scope
        self.threshold = semantic_threshold or settings.semantic_similarity_threshold

    # ------------------------------------------------------------------ keys
    def key_for(self, engine: str, params: dict[str, Any]) -> CacheKey:
        return build_key(
            engine,
            params,
            project_id=self.project_id,
            org_id=self.org_id,
            scope=self.scope,
        )

    # --------------------------------------------------------------- inspect
    async def inspect(
        self,
        engine: str,
        params: dict[str, Any],
        *,
        freshness: str = "stable",
        allow_semantic: bool = True,
        allow_archive: bool = True,
    ) -> CacheState:
        """Is this step satisfiable without a live call, and is it fresh enough?

        Called by the planner for every step of every candidate plan, so it is
        read-only and never mutates hit counters.
        """
        started = time.perf_counter()
        key = self.key_for(engine, params)
        max_age = freshness_max_age_seconds(freshness)

        state = await self._inspect_exact(key, freshness, max_age)
        if state.available:
            state.lookup_ms = (time.perf_counter() - started) * 1000.0
            return state

        if allow_semantic and not is_identifier_lookup(engine, params) and key.query_text:
            semantic = await self._inspect_semantic(key, freshness, max_age)
            if semantic.available:
                semantic.lookup_ms = (time.perf_counter() - started) * 1000.0
                return semantic
            state.guard_rejections = semantic.guard_rejections
            if semantic.reason:
                state.reason = semantic.reason

        if allow_archive:
            archive = await self._inspect_archive(key, freshness, max_age)
            if archive.available:
                archive.lookup_ms = (time.perf_counter() - started) * 1000.0
                archive.guard_rejections = state.guard_rejections
                return archive

        state.lookup_ms = (time.perf_counter() - started) * 1000.0
        state.freshness_requirement = freshness
        return state

    async def _inspect_exact(self, key: CacheKey, freshness: str, max_age: int) -> CacheState:
        started = time.perf_counter()
        hot = await hot_get(key.redis_key)
        if hot:
            age = int(time.time() - float(hot.get("stored_at", time.time())))
            ttl = await hot_ttl(key.redis_key)
            metrics.cache_lookup_seconds.labels(layer=LAYER_EXACT).observe(
                time.perf_counter() - started
            )
            return self._finish(
                layer=LAYER_EXACT,
                freshness=freshness,
                max_age=max_age,
                age=age,
                ttl_remaining=ttl,
                ttl_source=hot.get("ttl_source"),
                matched_query=hot.get("query_text"),
                cache_entry_id=hot.get("cache_entry_id"),
                payload_ref=hot.get("payload_ref"),
                detail="exact hit in the Redis hot layer",
            )

        # Redis miss is not a cache miss: the durable index survives restarts.
        row = await self.session.scalar(
            select(CacheEntry)
            .where(
                CacheEntry.partition_key == key.partition,
                CacheEntry.request_hash == key.request_hash,
                CacheEntry.invalidated_at.is_(None),
                CacheEntry.expires_at > datetime.now(UTC),
            )
            .limit(1)
        )
        metrics.cache_lookup_seconds.labels(layer=LAYER_EXACT).observe(
            time.perf_counter() - started
        )
        if row is None:
            return CacheState(
                layer=LAYER_MISS,
                freshness_requirement=freshness,
                reason="no exact entry in Redis or the durable index",
            )
        age = int((datetime.now(UTC) - row.created_at).total_seconds())
        ttl_remaining = int((row.expires_at - datetime.now(UTC)).total_seconds())
        return self._finish(
            layer=LAYER_EXACT,
            freshness=freshness,
            max_age=max_age,
            age=age,
            ttl_remaining=ttl_remaining,
            ttl_source=row.ttl_source,
            matched_query=row.query_text,
            cache_entry_id=row.id,
            payload_ref=row.payload_ref,
            detail="exact hit in the durable PostgreSQL index (Redis cold)",
        )

    async def _inspect_semantic(self, key: CacheKey, freshness: str, max_age: int) -> CacheState:
        started = time.perf_counter()
        vector = list(embed(key.query_text))
        candidates = await self._semantic_candidates(key, vector)
        metrics.cache_lookup_seconds.labels(layer=LAYER_SEMANTIC).observe(
            time.perf_counter() - started
        )

        rejections = 0
        for row, distance in candidates:
            similarity = 1.0 - float(distance)
            if similarity < self.threshold:
                break
            verdict = guard.check_against_stored(
                key.query_text, row.numerals, row.entities, row.versions, row.query_text
            )
            if not verdict.accepted:
                rejections += 1
                metrics.semantic_guard_rejections_total.labels(
                    engine=metrics.safe_label(key.engine), reason=verdict.reason
                ).inc()
                continue
            age = int((datetime.now(UTC) - row.created_at).total_seconds())
            ttl_remaining = int((row.expires_at - datetime.now(UTC)).total_seconds())
            state = self._finish(
                layer=LAYER_SEMANTIC,
                freshness=freshness,
                max_age=max_age,
                age=age,
                ttl_remaining=ttl_remaining,
                ttl_source=row.ttl_source,
                matched_query=row.query_text,
                cache_entry_id=row.id,
                payload_ref=row.payload_ref,
                similarity=round(similarity, 4),
                detail=(
                    "semantic hit at cosine "
                    + str(round(similarity, 4))
                    + " on an entity-identical query"
                ),
            )
            state.guard_rejections = rejections
            return state

        return CacheState(
            layer=LAYER_MISS,
            freshness_requirement=freshness,
            guard_rejections=rejections,
            reason=(
                str(rejections) + " near-match(es) rejected by the entity/numeral guard"
                if rejections
                else "no semantic neighbour above threshold " + str(self.threshold)
            ),
        )

    async def _semantic_candidates(
        self, key: CacheKey, vector: list[float]
    ) -> list[tuple[CacheEntry, float]]:
        """Partition-filtered vector search.

        The partition columns are in the WHERE clause so PostgreSQL restricts
        the row set *before* any distance is computed. Scanning the whole
        vector space and filtering afterwards would be both slower and would
        cross the project isolation boundary while doing it.
        """
        sql = text(
            """
            SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) AS similarity,
                   (embedding <=> CAST(:vec AS vector)) AS distance
            FROM cache_entries
            WHERE partition_key = :partition
              AND engine = :engine
              AND gl = :gl
              AND hl = :hl
              AND location = :location
              AND invalidated_at IS NULL
              AND expires_at > now()
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT 5
            """
        )
        try:
            result = await self.session.execute(
                sql,
                {
                    "vec": "[" + ",".join(str(v) for v in vector) + "]",
                    "partition": key.partition,
                    "engine": key.engine,
                    "gl": key.gl,
                    "hl": key.hl,
                    "location": key.location,
                },
            )
            rows = result.mappings().all()
        except Exception as exc:
            log.warning(
                "semantic lookup failed",
                extra={"event": "cache.semantic_error", "error": type(exc).__name__},
            )
            return []

        if not rows:
            return []
        ids = [r["id"] for r in rows]
        entries = (
            await self.session.scalars(select(CacheEntry).where(CacheEntry.id.in_(ids)))
        ).all()
        by_id = {e.id: e for e in entries}
        out: list[tuple[CacheEntry, float]] = []
        for row in rows:
            entry = by_id.get(row["id"])
            if entry is not None:
                out.append((entry, float(row["distance"])))
        return out

    async def _inspect_archive(self, key: CacheKey, freshness: str, max_age: int) -> CacheState:
        started = time.perf_counter()
        row = await self.session.scalar(
            select(ArchiveRef)
            .where(
                ArchiveRef.partition_key == key.partition,
                ArchiveRef.request_hash == key.request_hash,
            )
            .order_by(ArchiveRef.created_at.desc())
            .limit(1)
        )
        metrics.cache_lookup_seconds.labels(layer=LAYER_ARCHIVE).observe(
            time.perf_counter() - started
        )
        if row is None:
            return CacheState(
                layer=LAYER_MISS,
                freshness_requirement=freshness,
                reason="no archived search matches this request",
            )
        reference = row.serpapi_created_at or row.created_at
        age = int((datetime.now(UTC) - reference).total_seconds())
        return self._finish(
            layer=LAYER_ARCHIVE,
            freshness=freshness,
            max_age=max_age,
            age=age,
            ttl_remaining=None,
            ttl_source="archive",
            matched_query=row.query_text,
            cache_entry_id=None,
            payload_ref=row.payload_ref,
            archive_search_id=row.search_id,
            detail="reusable SerpApi Searches Archive entry (consumes no credit)",
        )

    def _finish(
        self,
        *,
        layer: str,
        freshness: str,
        max_age: int,
        age: int | None,
        ttl_remaining: int | None,
        ttl_source: str | None,
        matched_query: str | None,
        cache_entry_id: str | None,
        payload_ref: str | None,
        detail: str,
        similarity: float | None = None,
        archive_search_id: str | None = None,
    ) -> CacheState:
        acceptable = age is None or age <= max_age
        reason = detail
        if not acceptable:
            # The crux of section 14: the entry exists and is free, but serving
            # it would violate the freshness requirement inferred in stage C,
            # so it does not count toward marginal savings.
            reason = (
                detail
                + ", but it is "
                + _humanize(age or 0)
                + " old and the step requires "
                + freshness
                + " (max "
                + _humanize(max_age)
                + "). Not counted as warm."
            )
        return CacheState(
            layer=layer,
            available=True,
            acceptable=acceptable,
            freshness_requirement=freshness,
            age_seconds=age,
            ttl_remaining=ttl_remaining,
            ttl_source=ttl_source,
            similarity=similarity,
            matched_query=matched_query,
            cache_entry_id=cache_entry_id,
            archive_search_id=archive_search_id,
            payload_ref=payload_ref,
            reason=reason,
        )

    # ---------------------------------------------------------------- lookup
    async def lookup(
        self,
        engine: str,
        params: dict[str, Any],
        *,
        freshness: str = "stable",
        run_id: str | None = None,
        allow_semantic: bool = True,
        allow_archive: bool = True,
    ) -> CacheHit:
        """Executor path: resolve a hit and return its payload.

        Unlike ``inspect`` this records guard rejections durably and bumps hit
        counters, because it reflects a request that actually happened.
        """
        from app.integrations.storage import get_object_store

        key = self.key_for(engine, params)
        state = await self.inspect(
            engine,
            params,
            freshness=freshness,
            allow_semantic=allow_semantic,
            allow_archive=allow_archive,
        )

        if state.guard_rejections and allow_semantic:
            await self._record_guard_rejections(key, run_id)

        if not state.is_warm or not state.payload_ref:
            metrics.cache_hits_total.labels(
                layer=LAYER_MISS, project_id=metrics.safe_label(self.project_id)
            ).inc()
            return CacheHit(state=state if state.available else state, payload=None)

        payload = await get_object_store().get_json(state.payload_ref)
        if payload is None:
            # The index knows about an object the store no longer has. Treat it
            # as a miss rather than failing the run.
            state.available = False
            state.acceptable = False
            state.layer = LAYER_MISS
            state.reason = "cache index referenced a payload that is no longer in object storage"
            return CacheHit(state=state, payload=None)

        metrics.cache_hits_total.labels(
            layer=state.layer, project_id=metrics.safe_label(self.project_id)
        ).inc()

        entry: CacheEntry | None = None
        if state.cache_entry_id:
            entry = await self.session.get(CacheEntry, state.cache_entry_id)
            if entry is not None:
                entry.hit_count += 1
                entry.last_hit_at = datetime.now(UTC)
                await hot_set(
                    key.redis_key,
                    {
                        "stored_at": time.time() - (state.age_seconds or 0),
                        "payload_ref": entry.payload_ref,
                        "cache_entry_id": entry.id,
                        "query_text": entry.query_text,
                        "ttl_source": entry.ttl_source,
                    },
                    max(60, state.ttl_remaining or entry.ttl_seconds),
                )
        elif state.archive_search_id:
            archive = await self.session.scalar(
                select(ArchiveRef).where(ArchiveRef.search_id == state.archive_search_id)
            )
            if archive is not None:
                archive.reuse_count += 1

        return CacheHit(state=state, payload=payload, entry=entry)

    async def _record_guard_rejections(self, key: CacheKey, run_id: str | None) -> None:
        """Persist rejected near-matches so the threshold can be tuned with
        evidence rather than intuition (section 17)."""
        vector = list(embed(key.query_text))
        for row, distance in await self._semantic_candidates(key, vector):
            similarity = 1.0 - float(distance)
            if similarity < self.threshold:
                break
            verdict = guard.check_against_stored(
                key.query_text, row.numerals, row.entities, row.versions, row.query_text
            )
            if verdict.accepted:
                break
            self.session.add(
                SemanticGuardRejection(
                    org_id=self.org_id,
                    project_id=self.project_id,
                    engine=key.engine,
                    incoming_query=key.query_text[:1000],
                    candidate_query=row.query_text[:1000],
                    candidate_cache_entry_id=row.id,
                    similarity=round(similarity, 5),
                    reason=verdict.reason,
                    incoming_tokens=verdict.incoming_token_list,
                    candidate_tokens=verdict.candidate_token_list,
                    run_id=run_id,
                )
            )

    # ----------------------------------------------------------------- store
    async def store(
        self,
        engine: str,
        params: dict[str, Any],
        payload: dict[str, Any],
        *,
        ttl: TTLDecision,
        credits_cost: int,
        pii_risk: str = "low",
        serpapi_search_id: str | None = None,
        run_id: str | None = None,
        mode: str = "live",
    ) -> CacheEntry:
        """Write through to object storage, the durable index and Redis."""
        from app.integrations.storage import get_object_store

        key = self.key_for(engine, params)
        payload_ref, size = await get_object_store().put_json(payload)
        tokens = guard.tokens_for_storage(key.query_text)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl.ttl_seconds)

        existing = await self.session.scalar(
            select(CacheEntry).where(
                CacheEntry.partition_key == key.partition,
                CacheEntry.request_hash == key.request_hash,
            )
        )
        vector = list(embed(key.query_text)) if key.query_text else None

        if existing is not None:
            existing.payload_ref = payload_ref
            existing.payload_bytes = size
            existing.ttl_seconds = ttl.ttl_seconds
            existing.ttl_source = ttl.source
            existing.expires_at = expires_at
            existing.invalidated_at = None
            existing.refresh_count += 1
            existing.top_results_digest = top_results_digest(payload)
            existing.serpapi_search_id = serpapi_search_id
            existing.source_run_id = run_id
            existing.mode = mode
            existing.embedding = vector
            entry = existing
        else:
            entry = CacheEntry(
                org_id=self.org_id,
                project_id=self.project_id,
                partition_key=key.partition,
                engine=engine,
                gl=key.gl,
                hl=key.hl,
                location=key.location,
                request_hash=key.request_hash,
                normalized_request=key.normalized,
                query_text=key.query_text,
                embedding=vector,
                numerals=tokens["numerals"],
                entities=tokens["entities"],
                versions=tokens["versions"],
                payload_ref=payload_ref,
                payload_bytes=size,
                result_count=_count_results(payload),
                top_results_digest=top_results_digest(payload),
                credits_cost=credits_cost,
                ttl_seconds=ttl.ttl_seconds,
                ttl_source=ttl.source,
                expires_at=expires_at,
                serpapi_search_id=serpapi_search_id,
                pii_risk=pii_risk,
                source_run_id=run_id,
                mode=mode,
            )
            self.session.add(entry)
        await self.session.flush()

        await hot_set(
            key.redis_key,
            {
                "stored_at": time.time(),
                "payload_ref": payload_ref,
                "cache_entry_id": entry.id,
                "query_text": key.query_text,
                "ttl_source": ttl.source,
            },
            ttl.ttl_seconds,
        )
        return entry

    async def record_archive_ref(
        self,
        engine: str,
        params: dict[str, Any],
        *,
        search_id: str,
        payload_ref: str | None = None,
        credential_fingerprint: str | None = None,
        created_at: datetime | None = None,
    ) -> ArchiveRef:
        key = self.key_for(engine, params)
        existing = await self.session.scalar(
            select(ArchiveRef).where(ArchiveRef.search_id == search_id)
        )
        if existing is not None:
            return existing
        ref = ArchiveRef(
            org_id=self.org_id,
            project_id=self.project_id,
            partition_key=key.partition,
            search_id=search_id,
            engine=engine,
            request_hash=key.request_hash,
            normalized_request=key.normalized,
            query_text=key.query_text,
            credential_fingerprint=credential_fingerprint,
            payload_ref=payload_ref,
            serpapi_created_at=created_at,
        )
        self.session.add(ref)
        await self.session.flush()
        return ref

    # ------------------------------------------------------------ invalidate
    async def invalidate(
        self,
        *,
        engine: str | None = None,
        entry_id: str | None = None,
        partition_only: bool = False,
    ) -> int:
        """Manual invalidation from the Cache Dashboard (section 50)."""
        now = datetime.now(UTC)
        query = select(CacheEntry).where(
            CacheEntry.org_id == self.org_id, CacheEntry.invalidated_at.is_(None)
        )
        if entry_id:
            query = query.where(CacheEntry.id == entry_id)
        else:
            query = query.where(
                CacheEntry.partition_key
                == build_key(
                    "x", {}, project_id=self.project_id, org_id=self.org_id, scope=self.scope
                ).partition
            )
            if engine:
                query = query.where(CacheEntry.engine == engine)
        rows = (await self.session.scalars(query)).all()
        for row in rows:
            row.invalidated_at = now
        partition = build_key(
            "x", {}, project_id=self.project_id, org_id=self.org_id, scope=self.scope
        ).partition
        pattern = "sf:cache:" + partition + ":" + (engine or "*") + ":*"
        await hot_delete_pattern(pattern)
        _ = partition_only
        return len(rows)


def _count_results(payload: dict[str, Any]) -> int:
    for key in (
        "organic_results",
        "local_results",
        "news_results",
        "shopping_results",
        "reviews",
        "video_results",
        "images_results",
        "products",
        "jobs_results",
        "events_results",
        "properties",
        "best_flights",
        "suggestions",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _humanize(seconds: int) -> str:
    if seconds < 60:
        return str(seconds) + "s"
    if seconds < 3600:
        return str(seconds // 60) + "m"
    if seconds < 86400:
        return str(seconds // 3600) + "h"
    return str(seconds // 86400) + "d"


__all__ = [
    "LAYER_ARCHIVE",
    "LAYER_EXACT",
    "LAYER_LIVE",
    "LAYER_MISS",
    "LAYER_SEMANTIC",
    "CacheHit",
    "CacheService",
    "CacheState",
]
