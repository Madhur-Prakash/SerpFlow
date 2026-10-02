"""Plans, candidate plans, runs and steps (sections 15, 47, 48, 81).

``plan_candidates`` persists *every* candidate the planner generated, not only
the winner. The Plan Inspector renders stored values straight out of this
table - the counterfactual is never recomputed in the frontend.
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_id


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"
    __table_args__ = (
        Index("ix_plans_project_created", "project_id", "created_at"),
        Index("ix_plans_replan_changed", "marginal_replan_changed_selection"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("plan"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    principal_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    intent: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_intent: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # The selected plan's steps, fully bound and ready to execute.
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    parameter_bindings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # --- the cost model (sections 14, 15) ---------------------------------
    naive_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    marginal_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    projected_full_scale_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Steps satisfiable with no live upstream call, with the layer that serves them.
    warm_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    freshness_requirements: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )

    budget_reduction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)

    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Required when candidate_count == 1 (section 15).
    single_candidate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    rejected_alternatives: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    rejected_engines: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )

    selected_candidate_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The candidate that *would* have won on cold cost alone.
    cold_winner_candidate_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The thesis, persisted: did marginal re-ranking change the answer?
    marginal_replan_changed_selection: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    replan_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    budget_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planner_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mode: Mapped[str] = mapped_column(String(12), default="replay", nullable=False)
    stage_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    candidates: Mapped[list[PlanCandidate]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", lazy="selectin"
    )
    runs: Mapped[list[Run]] = relationship(back_populates="plan")

    @property
    def savings(self) -> int:
        return max(0, self.naive_cost - self.marginal_cost)


class PlanCandidate(Base, TimestampMixin):
    """One candidate execution path. Persisted whether it won or lost."""

    __tablename__ = "plan_candidates"
    __table_args__ = (Index("ix_plan_candidates_plan_rank", "plan_id", "marginal_rank"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("cand"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    label: Mapped[str] = mapped_column(String(120), nullable=False)
    strategy: Mapped[str] = mapped_column(String(60), default="primary", nullable=False)
    engines: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    hops: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    naive_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    marginal_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warm_step_indices: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    cache_state: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    coverage: Mapped[str] = mapped_column(String(20), default="full", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    naive_rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    marginal_rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    feasible_within_budget: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trade_off_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[Plan] = relationship(back_populates="candidates")


class Run(Base, TimestampMixin):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_project_created", "project_id", "created_at"),
        Index("ix_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("run"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    principal_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    principal_type: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    api_key_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    service_session_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    intent: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    trigger: Mapped[str] = mapped_column(String(24), default="interactive", nullable=False)

    credits_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_saved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    naive_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    marginal_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cache_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    mode: Mapped[str] = mapped_column(String(12), default="replay", nullable=False)

    results_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    trace_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    replay_of_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    # section 55: PII-bearing runs expire sooner
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    max_pii_risk: Mapped[str] = mapped_column(String(12), default="low", nullable=False)

    plan: Mapped[Plan | None] = relationship(back_populates="runs")
    steps: Mapped[list[Step]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="Step.index",
        lazy="selectin",
    )


class Step(Base, TimestampMixin):
    __tablename__ = "steps"
    __table_args__ = (Index("ix_steps_run_index", "run_id", "index"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("step"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    index: Mapped[int] = mapped_column(Integer, nullable=False)
    engine: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    depends_on: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    fan_out: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # exact | semantic | archive | live | skipped
    cache_layer: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    matched_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    age_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttl_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    freshness_requirement: Mapped[str] = mapped_column(String(16), default="stable", nullable=False)

    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    payload_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    serpapi_search_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(12), default="replay", nullable=False)
    pii_risk: Mapped[str] = mapped_column(String(12), default="low", nullable=False)

    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    run: Mapped[Run] = relationship(back_populates="steps")


__all__ = ["Plan", "PlanCandidate", "Run", "Step"]
