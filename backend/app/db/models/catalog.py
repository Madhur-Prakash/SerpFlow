"""Catalog projection tables (sections 11, 12, 49).

The committed YAML under ``app/services/catalog/data/`` is the source of
truth. These tables are a queryable projection of it, loaded by
``make catalog-build`` / ``make seed``, so the Catalog Explorer and the
retrieval stage can index it without re-parsing YAML on every request.

Two relationship kinds, both mandatory:

* ``catalog_edges``       - how engines CHAIN (satisfied_by / feeds)
* ``catalog_substitutes`` - how engines COMPETE (capability_tags / substitutes)

Without the second, the planner cannot generate alternative candidate plans and
marginal replanning has nothing to re-rank.
"""

from __future__ import annotations

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, TimestampMixin, new_id


class CatalogVersion(Base, TimestampMixin):
    __tablename__ = "catalog_versions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("cver"))
    version: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    engine_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    substitute_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    capability_tag_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CatalogEngine(Base, TimestampMixin):
    __tablename__ = "catalog_engines"
    __table_args__ = (
        UniqueConstraint("catalog_version", "engine", name="uq_catalog_engines_version_engine"),
        Index("ix_catalog_engines_version", "catalog_version"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("ceng"))
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    engine: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(Text, default="", nullable=False)
    capability_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    requires: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    optional_params: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    produces: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    cost: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    latency_class: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    volatility_prior: Mapped[str] = mapped_column(String(16), default="7d", nullable=False)
    locale_sensitive: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    pii_risk: Mapped[str] = mapped_column(String(12), default="low", nullable=False)
    docs_url: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    search_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(settings.embedding_dim), nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class CatalogEdge(Base, TimestampMixin):
    """A typed dependency edge: ``from_engine`` produces a field that satisfies a
    required input of ``to_engine``. This is what makes multi-hop chains
    computable instead of invented."""

    __tablename__ = "catalog_edges"
    __table_args__ = (
        Index("ix_catalog_edges_from", "catalog_version", "from_engine"),
        Index("ix_catalog_edges_to", "catalog_version", "to_engine"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("cedge"))
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    from_engine: Mapped[str] = mapped_column(String(80), nullable=False)
    to_engine: Mapped[str] = mapped_column(String(80), nullable=False)
    # e.g. google_maps.local_results[].data_id
    produces_field: Mapped[str] = mapped_column(String(200), nullable=False)
    # e.g. data_id
    satisfies_param: Mapped[str] = mapped_column(String(80), nullable=False)
    param_type: Mapped[str] = mapped_column(String(40), default="string", nullable=False)
    fan_out_hint: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class CatalogSubstitute(Base, TimestampMixin):
    """A competing engine for the same capability.

    ``coverage`` is one of full | partial | narrow, and ``note`` states the real
    trade-off. The note surfaces verbatim in Plan Inspector rejection reasons -
    it is user-facing copy, not an internal comment.
    """

    __tablename__ = "catalog_substitutes"
    __table_args__ = (
        Index("ix_catalog_subs_engine", "catalog_version", "engine"),
        Index("ix_catalog_subs_sub", "catalog_version", "substitute_engine"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("csub"))
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    engine: Mapped[str] = mapped_column(String(80), nullable=False)
    substitute_engine: Mapped[str] = mapped_column(String(80), nullable=False)
    coverage: Mapped[str] = mapped_column(String(12), default="partial", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    shared_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence_penalty: Mapped[float] = mapped_column(Float, default=0.1, nullable=False)


__all__ = ["CatalogEdge", "CatalogEngine", "CatalogSubstitute", "CatalogVersion"]
