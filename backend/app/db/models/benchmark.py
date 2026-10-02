"""Benchmark tasks and routing evaluations (section 53).

Tasks are authored by hand and committed as versioned fixtures under
``backend/fixtures/benchmark/``. These tables hold the loaded task set and the
per-run evaluations so the UI can show accuracy per ``catalog_version``.

The benchmark needs real LLM calls, so it runs on demand via ``make benchmark``
and is deliberately not part of CI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_id


class BenchmarkTask(Base, TimestampMixin):
    __tablename__ = "benchmark_tasks"
    __table_args__ = (
        UniqueConstraint("task_key", "suite_version", name="uq_benchmark_tasks_key_version"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("bmt"))
    task_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    suite_version: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)

    intent: Mapped[str] = mapped_column(Text, nullable=False)
    expected_engines: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    acceptable_alternatives: Mapped[list[list[str]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    expected_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expected_freshness: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # single_engine | multi_hop | locale | freshness | substitute
    category: Mapped[str] = mapped_column(String(32), default="single_engine", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(12), default="medium", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class BenchmarkRun(Base, TimestampMixin):
    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("bmr"))
    org_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    suite_version: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # serpflow | unaided_llm | embedding_only
    system: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    llm_model: Mapped[str] = mapped_column(String(80), default="", nullable=False)

    task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    engine_accuracy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    param_accuracy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    freshness_accuracy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mean_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mean_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    by_category: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    failure_modes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoutingEval(Base, TimestampMixin):
    __tablename__ = "routing_evals"
    __table_args__ = (Index("ix_routing_evals_run_task", "benchmark_run_id", "task_key"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("rev"))
    benchmark_run_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_key: Mapped[str] = mapped_column(String(40), nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    system: Mapped[str] = mapped_column(String(32), nullable=False)

    predicted_engines: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    predicted_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    predicted_freshness: Mapped[str | None] = mapped_column(String(16), nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    engines_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    params_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    freshness_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    matched_alternative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # wrong_engine | missing_hop | extra_hop | locale_miss | freshness_miss | no_plan
    failure_mode: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)


__all__ = ["BenchmarkRun", "BenchmarkTask", "RoutingEval"]
