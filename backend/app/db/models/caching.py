"""Durable cache index, archive references, TTL learning and guard telemetry.

Redis is the hot layer and is *not* the source of truth (section 18). This
table is: a Redis restart repopulates lazily from here, and no credits are
lost.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, TimestampMixin, new_id

EMBEDDING_DIM = settings.embedding_dim


class CacheEntry(Base, TimestampMixin):
    """Durable cache index plus the vector used for semantic lookup.

    The partition columns (``engine``, ``gl``, ``hl``, ``location``,
    ``partition_key``) are deliberately first-class: the semantic query filters
    on them *before* evaluating vector similarity (section 17). A full vector
    scan followed by filtering would be both slower and wrong at scale.
    """

    __tablename__ = "cache_entries"
    __table_args__ = (
        Index("ix_cache_entries_exact", "partition_key", "request_hash", unique=True),
        # Partition-first composite index: the WHERE clause uses this before
        # any vector distance is computed.
        Index("ix_cache_entries_partition", "partition_key", "engine", "gl", "hl", "location"),
        Index("ix_cache_entries_expiry", "expires_at"),
        Index("ix_cache_entries_project_engine", "project_id", "engine"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("cache"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Attribution: the project whose upstream spend produced this entry.
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # "project:<id>" by default, "org:<id>" when shared cache is enabled.
    partition_key: Mapped[str] = mapped_column(String(60), nullable=False)

    engine: Mapped[str] = mapped_column(String(80), nullable=False)
    gl: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    hl: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    location: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    request_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    # deterministic guard material, extracted once at write time (section 17)
    numerals: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    entities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    versions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    payload_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    top_results_digest: Mapped[str | None] = mapped_column(String(80), nullable=True)

    credits_cost: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    ttl_source: Mapped[str] = mapped_column(String(32), default="volatility_prior", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    serpapi_search_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pii_risk: Mapped[str] = mapped_column(String(12), default="low", nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mode: Mapped[str] = mapped_column(String(12), default="replay", nullable=False)

    @property
    def is_live(self) -> bool:
        return self.invalidated_at is None


class ArchiveRef(Base, TimestampMixin):
    """SerpApi Searches Archive pointer (section 19).

    Re-reading an archived search costs no credit, so the executor checks here
    before paying for a live call.
    """

    __tablename__ = "archive_refs"
    __table_args__ = (
        Index("ix_archive_refs_lookup", "partition_key", "request_hash"),
        Index("ix_archive_refs_search_id", "search_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("arch"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    partition_key: Mapped[str] = mapped_column(String(60), nullable=False)

    search_id: Mapped[str] = mapped_column(String(80), nullable=False)
    engine: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    request_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    credential_fingerprint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    payload_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reuse_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    serpapi_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TTLObservation(Base, TimestampMixin):
    """Adaptive TTL learning signal (section 20).

    TTL is learned per query class, not only per engine: a volatile query on a
    stable engine still needs a short TTL.
    """

    __tablename__ = "ttl_observations"
    __table_args__ = (Index("ix_ttl_obs_engine_class", "engine", "query_class"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("ttlo"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    engine: Mapped[str] = mapped_column(String(80), nullable=False)
    query_class: Mapped[str] = mapped_column(String(80), default="general", nullable=False)
    cache_entry_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    previous_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    new_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    top10_changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    churn_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    observed_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SemanticGuardRejection(Base, TimestampMixin):
    """Every near-match the entity/numeral guard rejected (section 17).

    Logged so the similarity threshold can be tuned with evidence instead of
    intuition.
    """

    __tablename__ = "semantic_guard_rejections"
    __table_args__ = (Index("ix_guard_rejections_engine", "engine", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("grd"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    engine: Mapped[str] = mapped_column(String(80), nullable=False)
    incoming_query: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_query: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_cache_entry_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    incoming_tokens: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    candidate_tokens: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class FalseHitReport(Base, TimestampMixin):
    """Operator report filed from the Run Inspector (section 47).

    This is the real producer behind
    ``serpflow_semantic_false_hit_reports_total``.
    """

    __tablename__ = "false_hit_reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("fhr"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cache_entry_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    engine: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    reported_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    requested_query: Mapped[str] = mapped_column(Text, default="", nullable=False)
    matched_query: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resolution: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    invalidated_entry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


__all__ = [
    "EMBEDDING_DIM",
    "ArchiveRef",
    "CacheEntry",
    "FalseHitReport",
    "SemanticGuardRejection",
    "TTLObservation",
]
