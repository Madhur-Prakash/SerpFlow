"""The executor (sections 25, 44).

Per step::

    EXACT -> SEMANTIC -> SEARCHES ARCHIVE -> LIVE

This is the only component permitted to decrypt an upstream credential
(section 25). The plaintext lives in a local variable inside ``execute`` and is
never returned, logged or attached to a model.

A credential revoked mid-run fails the run loudly rather than returning partial
results (section 27), because a half-executed chain silently missing its last
hop looks exactly like a complete answer.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core import metrics, telemetry
from app.core.config import settings
from app.core.exceptions import (
    BudgetExhaustedError,
    CredentialRevokedError,
    EngineNotAllowedError,
    NoUpstreamCredentialError,
    UpstreamError,
)
from app.core.logging import get_logger
from app.core.security import decrypt_credential
from app.db.models.keys import UpstreamCredential
from app.db.models.planning import Plan, Run, Step
from app.integrations.serpapi import MODE_MOCK, ResolvedMode, SerpApiGateway
from app.integrations.storage import get_object_store
from app.services.budgets.service import BudgetService
from app.services.cache.service import (
    LAYER_ARCHIVE,
    LAYER_EXACT,
    LAYER_LIVE,
    LAYER_SEMANTIC,
    CacheService,
)
from app.services.cache.ttl import cap_for_freshness, initial_ttl
from app.services.catalog.loader import CatalogIndex, load_catalog
from app.services.executor.extract import extract, summarize_payload

log = get_logger("serpflow.executor")

ProgressFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class StepOutcome:
    index: int
    engine: str
    status: str
    cache_layer: str
    credits: int
    latency_ms: float
    payload: dict[str, Any] | None = None
    payload_ref: str | None = None
    extracted: dict[str, list[Any]] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    calls: int = 1
    live_calls: int = 0
    row: Any = None


@dataclass(slots=True)
class ExecutionResult:
    run: Run
    steps: list[StepOutcome]
    credits_spent: int
    credits_saved: int
    results: dict[str, Any]
    cache_summary: dict[str, int]


class ExecutorService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        org_id: str,
        project_id: str,
        mode: ResolvedMode,
        credential: UpstreamCredential | None = None,
        catalog: CatalogIndex | None = None,
        cache: CacheService | None = None,
        budgets: BudgetService | None = None,
        engine_allowlist: list[str] | None = None,
        engine_denylist: list[str] | None = None,
        ttl_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.session = session
        self.org_id = org_id
        self.project_id = project_id
        self.mode = mode
        self.credential = credential
        self.catalog = catalog or load_catalog()
        self.cache = cache or CacheService(session, org_id=org_id, project_id=project_id)
        self.budgets = budgets or BudgetService(session, org_id=org_id, project_id=project_id)
        self.engine_allowlist = set(engine_allowlist or [])
        self.engine_denylist = set(engine_denylist or [])
        self.ttl_overrides = ttl_overrides or {}

    # ------------------------------------------------------------ execution
    async def execute(
        self,
        run: Run,
        plan: Plan,
        *,
        progress: ProgressFn | None = None,
        api_key_id: str | None = None,
        session_id: str | None = None,
    ) -> ExecutionResult:
        started = time.perf_counter()
        run.status = "running"
        run.started_at = datetime.now(UTC)
        run.mode = self.mode.mode
        await self.session.flush()

        # The one and only decryption point in the whole system.
        upstream_key: str | None = None
        if self.mode.mode in ("live", "record"):
            upstream_key = self._decrypt_credential()

        gateway = SerpApiGateway(mode=self.mode, api_key=upstream_key)
        outcomes: list[StepOutcome] = []
        step_rows: list[Step] = []
        step_payloads: dict[int, dict[str, Any]] = {}
        credits_spent = 0
        credits_saved = 0
        layer_counts: dict[str, int] = {
            LAYER_EXACT: 0,
            LAYER_SEMANTIC: 0,
            LAYER_ARCHIVE: 0,
            LAYER_LIVE: 0,
        }

        try:
            with telemetry.span(
                telemetry.SPAN_EXECUTE,
                **{"serpflow.run_id": run.id, "serpflow.mode": self.mode.mode},
            ):
                for raw_step in plan.steps:
                    index = int(raw_step["index"])
                    engine = str(raw_step["engine"])
                    self._check_engine_policy(engine)

                    if progress is not None:
                        await progress(
                            "executing",
                            "running",
                            {
                                "step": index,
                                "engine": engine,
                                "fan_out": raw_step.get("fan_out", 1),
                            },
                        )

                    outcome = await self._execute_step(
                        run=run,
                        plan=plan,
                        raw_step=raw_step,
                        gateway=gateway,
                        step_payloads=step_payloads,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    outcomes.append(outcome)
                    if outcome.row is not None:
                        step_rows.append(outcome.row)
                    if outcome.payload is not None:
                        step_payloads[index] = outcome.payload

                    credits_spent += outcome.credits
                    naive = int(raw_step.get("cost", 1)) * max(1, int(raw_step.get("fan_out", 1)))
                    credits_saved += max(0, naive - outcome.credits)
                    layer_counts[outcome.cache_layer] = (
                        layer_counts.get(outcome.cache_layer, 0) + outcome.calls
                    )

                    if progress is not None:
                        await progress(
                            "executing",
                            "step_complete",
                            {
                                "step": index,
                                "engine": engine,
                                "cache_layer": outcome.cache_layer,
                                "credits": outcome.credits,
                                "latency_ms": round(outcome.latency_ms, 1),
                                "status": outcome.status,
                            },
                        )

                    if outcome.status == "failed":
                        raise UpstreamError(
                            outcome.error_message or "Step failed.",
                            code=outcome.error_code or "UPSTREAM_ERROR",
                            details={"step": index, "engine": engine},
                        )

            results = self._assemble_results(plan, outcomes, step_payloads)
            run.status = "succeeded"
        except Exception as exc:
            run.status = "failed"
            run.error_code = getattr(exc, "code", type(exc).__name__)
            run.error_message = str(exc)[:1000]
            results = {"error": run.error_code}
            raise
        finally:
            # Zero the local before it can be captured by a traceback frame.
            upstream_key = None
            # Mark the relationship loaded without a query: callers read
            # run.steps immediately and a lazy load would fire outside the
            # async context.
            set_committed_value(run, "steps", sorted(step_rows, key=lambda s: s.index))
            duration = (time.perf_counter() - started) * 1000.0
            run.finished_at = datetime.now(UTC)
            run.duration_ms = duration
            run.credits_spent = credits_spent
            run.credits_saved = credits_saved
            run.naive_cost = plan.naive_cost
            run.marginal_cost = plan.marginal_cost
            run.cache_summary = layer_counts
            run.max_pii_risk = self._max_pii_risk(plan)
            run.expires_at = self._retention_deadline(run.max_pii_risk)
            run.provenance = {
                "mode": self.mode.mode,
                "mode_reason": self.mode.reason,
                "catalog_version": plan.catalog_version,
                "credential_fingerprint": (
                    self.credential.fingerprint if self.credential else None
                ),
                "layers": layer_counts,
                "llm_provider": settings.llm_provider,
            }
            metrics.run_duration_seconds.labels(status=run.status).observe(duration / 1000.0)
            await self.session.flush()

        run.result_summary = results.get("summary", {})
        if results.get("payload_ref"):
            run.results_ref = results["payload_ref"]

        return ExecutionResult(
            run=run,
            steps=outcomes,
            credits_spent=credits_spent,
            credits_saved=credits_saved,
            results=results,
            cache_summary=layer_counts,
        )

    # ----------------------------------------------------------- one step
    async def _execute_step(
        self,
        *,
        run: Run,
        plan: Plan,
        raw_step: dict[str, Any],
        gateway: SerpApiGateway,
        step_payloads: dict[int, dict[str, Any]],
        api_key_id: str | None,
        session_id: str | None,
    ) -> StepOutcome:
        index = int(raw_step["index"])
        engine = str(raw_step["engine"])
        spec = self.catalog.get(engine)
        fan_out = max(1, int(raw_step.get("fan_out", 1)))
        freshness = str(raw_step.get("freshness_requirement", "stable"))
        started = time.perf_counter()

        row = Step(
            org_id=self.org_id,
            project_id=self.project_id,
            run_id=run.id,
            index=index,
            engine=engine,
            label=str(raw_step.get("label", ""))[:200],
            depends_on=list(raw_step.get("depends_on", [])),
            fan_out=fan_out,
            freshness_requirement=freshness,
            confidence=float(plan.confidence),
            mode=self.mode.mode,
            pii_risk=spec.pii_risk,
            status="running",
        )
        self.session.add(row)
        await self.session.flush()

        try:
            bindings = self._resolve_bindings(raw_step, step_payloads, fan_out)
        except ValueError as exc:
            row.status = "failed"
            row.error_code = "BINDING_FAILED"
            row.error_message = str(exc)
            return StepOutcome(
                index=index,
                engine=engine,
                status="failed",
                cache_layer="skipped",
                credits=0,
                latency_ms=0.0,
                error_code="BINDING_FAILED",
                error_message=str(exc),
                row=row,
            )

        base_params = {
            k: v for k, v in (raw_step.get("parameters") or {}).items() if not isinstance(v, dict)
        }

        payloads: list[dict[str, Any]] = []
        credits = 0
        live_calls = 0
        layer_used = LAYER_LIVE
        matched_query: str | None = None
        similarity: float | None = None
        age_seconds: int | None = None
        ttl_source: str | None = None
        search_id: str | None = None
        http_status: int | None = None

        with telemetry.span(
            telemetry.SPAN_EXECUTE_STEP,
            **{
                "serpflow.engine": engine,
                "serpflow.step": index,
                "serpflow.fan_out": fan_out,
                "serpflow.freshness_requirement": freshness,
            },
        ):
            for call_index, binding in enumerate(bindings or [{}]):
                params = {**base_params, **binding}
                hit = await self.cache.lookup(engine, params, freshness=freshness, run_id=run.id)

                if hit.payload is not None:
                    payloads.append(hit.payload)
                    layer_used = hit.state.layer
                    matched_query = matched_query or hit.state.matched_query
                    similarity = similarity if similarity is not None else hit.state.similarity
                    age_seconds = age_seconds if age_seconds is not None else hit.state.age_seconds
                    ttl_source = ttl_source or hit.state.ttl_source
                    await self.budgets.record_saving(
                        source=hit.state.layer,
                        engine=engine,
                        credits=spec.cost,
                        run_id=run.id,
                        step_id=row.id,
                        beneficiary_project_id=self.project_id,
                        fetching_project_id=self._fetching_project(hit),
                    )
                    metrics.credits_saved_total.labels(
                        org_id=metrics.safe_label(self.org_id),
                        project_id=metrics.safe_label(self.project_id),
                        source=hit.state.layer,
                    ).inc(spec.cost)
                    continue

                # Archive before live: an archived re-read costs no credit.
                archived = await self._try_archive(gateway, engine, params, run.id)
                if archived is not None:
                    payloads.append(archived)
                    layer_used = LAYER_ARCHIVE
                    await self.budgets.record_saving(
                        source=LAYER_ARCHIVE,
                        engine=engine,
                        credits=spec.cost,
                        run_id=run.id,
                        step_id=row.id,
                    )
                    continue

                await self._assert_budget(spec.cost, api_key_id=api_key_id, session_id=session_id)
                self._assert_credential_still_valid()

                with telemetry.span(
                    telemetry.SPAN_UPSTREAM_CALL,
                    **{"serpflow.engine": engine, "serpflow.mode": self.mode.mode},
                ):
                    response = await gateway.search(engine, params)

                http_status = response.http_status
                if response.is_error:
                    metrics.upstream_errors_total.labels(
                        engine=metrics.safe_label(engine),
                        status=metrics.safe_label(response.http_status),
                    ).inc()
                    row.status = "failed"
                    row.error_code = "UPSTREAM_ERROR"
                    row.error_message = (response.error_message or "upstream error")[:500]
                    row.latency_ms = (time.perf_counter() - started) * 1000.0
                    return StepOutcome(
                        index=index,
                        engine=engine,
                        status="failed",
                        cache_layer=LAYER_LIVE,
                        credits=credits,
                        latency_ms=row.latency_ms,
                        error_code="UPSTREAM_ERROR",
                        error_message=row.error_message,
                        calls=call_index + 1,
                        live_calls=live_calls,
                        row=row,
                    )

                payloads.append(response.payload)
                search_id = search_id or response.search_id
                layer_used = LAYER_LIVE if self.mode.mode != MODE_MOCK else self.mode.mode

                if response.credited:
                    credits += spec.cost
                    live_calls += 1
                    await self.budgets.record_spend(
                        engine=engine,
                        credits=spec.cost,
                        run_id=run.id,
                        step_id=row.id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    metrics.credits_spent_total.labels(
                        org_id=metrics.safe_label(self.org_id),
                        project_id=metrics.safe_label(self.project_id),
                        engine=metrics.safe_label(engine),
                    ).inc(spec.cost)

                decision = initial_ttl(
                    spec.volatility_prior,
                    freshness=freshness,
                    override_seconds=self._ttl_override(engine),
                )
                decision = cap_for_freshness(decision, freshness)
                await self.cache.store(
                    engine,
                    params,
                    response.payload,
                    ttl=decision,
                    credits_cost=spec.cost,
                    pii_risk=spec.pii_risk,
                    serpapi_search_id=response.search_id,
                    run_id=run.id,
                    mode=self.mode.mode,
                )
                ttl_source = decision.source
                if response.search_id and self.mode.mode in ("live", "record"):
                    await self.cache.record_archive_ref(
                        engine,
                        params,
                        search_id=response.search_id,
                        credential_fingerprint=(
                            self.credential.fingerprint if self.credential else None
                        ),
                    )

        latency = (time.perf_counter() - started) * 1000.0
        merged = _merge_payloads(payloads)
        payload_ref, payload_bytes = await get_object_store().put_json(merged)
        extracted = self._extract_for_downstream(engine, merged)

        row.status = "succeeded"
        row.cache_layer = layer_used
        row.matched_query = matched_query
        row.similarity = similarity
        row.age_seconds = age_seconds
        row.ttl_source = ttl_source
        row.credits = credits
        row.latency_ms = latency
        row.payload_ref = payload_ref
        row.payload_bytes = payload_bytes
        row.serpapi_search_id = search_id
        row.http_status = http_status
        row.parameters = _redact_params(base_params)
        row.extracted = {k: v[:20] for k, v in extracted.items()}

        metrics.step_latency_seconds.labels(
            engine=metrics.safe_label(engine), cache_layer=metrics.safe_label(layer_used)
        ).observe(latency / 1000.0)

        return StepOutcome(
            index=index,
            engine=engine,
            status="succeeded",
            cache_layer=layer_used,
            credits=credits,
            latency_ms=latency,
            payload=merged,
            payload_ref=payload_ref,
            extracted=extracted,
            calls=len(bindings or [{}]),
            live_calls=live_calls,
            row=row,
        )

    # ------------------------------------------------------------- helpers
    def _decrypt_credential(self) -> str:
        if self.credential is None:
            raise NoUpstreamCredentialError()
        if self.credential.revoked_at is not None:
            grace = self.credential.grace_until
            if grace is None or grace < datetime.now(UTC):
                raise CredentialRevokedError()
        return decrypt_credential(self.credential.ciphertext, self.credential.encrypted_dek)

    def _assert_credential_still_valid(self) -> None:
        """Re-checked before every upstream call.

        A credential revoked while a run is in flight fails the run loudly
        rather than returning the hops that happened to complete first.
        """
        if self.credential is None or self.mode.mode not in ("live", "record"):
            return
        if self.credential.revoked_at is None:
            return
        grace = self.credential.grace_until
        if grace is not None and grace >= datetime.now(UTC):
            return
        raise CredentialRevokedError(
            "The upstream credential was revoked while this run was in flight. "
            "The run has been failed rather than returning partial results."
        )

    def _check_engine_policy(self, engine: str) -> None:
        if self.engine_denylist and engine in self.engine_denylist:
            raise EngineNotAllowedError(
                engine + " is on this project's engine denylist.",
                details={"engine": engine},
            )
        if self.engine_allowlist and engine not in self.engine_allowlist:
            raise EngineNotAllowedError(
                engine + " is not on this project's engine allowlist.",
                details={"engine": engine},
            )

    async def _assert_budget(
        self, credits: int, *, api_key_id: str | None, session_id: str | None
    ) -> None:
        verdict = await self.budgets.check(credits, api_key_id=api_key_id, session_id=session_id)
        if not verdict.allowed:
            raise BudgetExhaustedError(verdict.message, details=verdict.as_dict())

    def _ttl_override(self, engine: str) -> int | None:
        value = self.ttl_overrides.get(engine)
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    def _resolve_bindings(
        self, raw_step: dict[str, Any], step_payloads: dict[int, dict[str, Any]], fan_out: int
    ) -> list[dict[str, Any]]:
        """Turn chained placeholders into concrete per-call parameter sets."""
        placeholders = {
            name: spec
            for name, spec in (raw_step.get("parameters") or {}).items()
            if isinstance(spec, dict) and "$from_step" in spec
        }
        if not placeholders:
            return [{}]

        per_param: dict[str, list[Any]] = {}
        for name, spec in placeholders.items():
            from_step = spec.get("$from_step")
            field_ref = spec.get("$field")
            if from_step is None or field_ref is None:
                raise ValueError("step " + str(raw_step.get("index")) + " has an unbound " + name)
            payload = step_payloads.get(int(from_step))
            if payload is None:
                raise ValueError(
                    "step "
                    + str(raw_step.get("index"))
                    + " depends on step "
                    + str(from_step)
                    + ", which produced no payload"
                )
            values = extract(payload, str(field_ref), limit=fan_out)
            if not values:
                raise ValueError(
                    "step "
                    + str(raw_step.get("index"))
                    + " needs "
                    + name
                    + " from "
                    + str(field_ref)
                    + ", but the upstream payload contained no such value"
                )
            per_param[name] = values

        width = min(fan_out, max(len(v) for v in per_param.values()))
        bindings: list[dict[str, Any]] = []
        for i in range(max(1, width)):
            binding = {}
            for name, values in per_param.items():
                binding[name] = values[i % len(values)]
            bindings.append(binding)
        return bindings

    async def _try_archive(
        self, gateway: SerpApiGateway, engine: str, params: dict[str, Any], run_id: str
    ) -> dict[str, Any] | None:
        """Reuse an archived search before paying for a live one."""
        if self.mode.mode not in ("live", "record"):
            return None
        from sqlalchemy import select

        from app.db.models.caching import ArchiveRef

        key = self.cache.key_for(engine, params)
        ref = await self.session.scalar(
            select(ArchiveRef)
            .where(
                ArchiveRef.partition_key == key.partition,
                ArchiveRef.request_hash == key.request_hash,
            )
            .order_by(ArchiveRef.created_at.desc())
            .limit(1)
        )
        if ref is None:
            return None
        try:
            response = await gateway.get_archived(ref.search_id)
        except Exception as exc:
            log.warning(
                "archive read failed, falling through to live",
                extra={"event": "archive.miss", "error": type(exc).__name__},
            )
            return None
        if response.is_error:
            return None
        ref.reuse_count += 1
        _ = run_id
        return response.payload

    def _extract_for_downstream(self, engine: str, payload: dict[str, Any]) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}
        for edge in self.catalog.edges_from(engine):
            values = extract(payload, edge.produces_field, limit=edge.fan_out_hint or 20)
            if values:
                out[edge.produces_field] = values
        return out

    def _assemble_results(
        self,
        plan: Plan,
        outcomes: list[StepOutcome],
        step_payloads: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        terminal = outcomes[-1] if outcomes else None
        payload = step_payloads.get(terminal.index) if terminal else None
        summary = summarize_payload(payload or {})
        # A billed search that found nothing carries SerpApi's own explanation
        # ("... hasn't returned any results for this query."). Pass it through so
        # an empty result reads as an answer, not as a broken run.
        notice = (payload or {}).get("error")
        if notice and not summary.get("count"):
            summary = {**summary, "notice": str(notice)[:300]}
        return {
            "summary": summary,
            "payload_ref": terminal.payload_ref if terminal else None,
            "terminal_engine": terminal.engine if terminal else None,
            "steps": [
                {
                    "index": o.index,
                    "engine": o.engine,
                    "cache_layer": o.cache_layer,
                    "credits": o.credits,
                    "calls": o.calls,
                    "latency_ms": round(o.latency_ms, 1),
                    "payload_ref": o.payload_ref,
                }
                for o in outcomes
            ],
            "catalog_version": plan.catalog_version,
        }

    def _max_pii_risk(self, plan: Plan) -> str:
        order = {"low": 0, "medium": 1, "high": 2}
        worst = "low"
        for step in plan.steps:
            engine = str(step.get("engine", ""))
            spec = self.catalog.engines.get(engine)
            if spec and order.get(spec.pii_risk, 0) > order.get(worst, 0):
                worst = spec.pii_risk
        return worst

    def _retention_deadline(self, pii_risk: str) -> datetime:
        """Section 55: PII-bearing runs expire sooner.

        Cached SERPs are not anonymous infrastructure data -
        google_maps_contributor_reviews caches named individuals' complete
        review histories.
        """
        days = (
            settings.retention_high_pii_days
            if pii_risk == "high"
            else settings.retention_standard_days
        )
        return datetime.now(UTC) + timedelta(days=days)

    def _fetching_project(self, hit: Any) -> str | None:
        entry = getattr(hit, "entry", None)
        if entry is not None and entry.project_id != self.project_id:
            return entry.project_id
        return None


def _merge_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse a fan-out step's responses into one document."""
    if not payloads:
        return {}
    if len(payloads) == 1:
        return payloads[0]
    merged: dict[str, Any] = {"serpflow_fan_out": len(payloads)}
    for payload in payloads:
        for key, value in payload.items():
            if isinstance(value, list):
                merged.setdefault(key, []).extend(value)
            elif key not in merged:
                merged[key] = value
    return merged


def _redact_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k not in {"api_key", "output", "no_cache"}}


__all__ = ["ExecutionResult", "ExecutorService", "StepOutcome"]
