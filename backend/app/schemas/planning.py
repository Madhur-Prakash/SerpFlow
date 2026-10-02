"""Plan, candidate, run, step, search and catalog schemas.

The Plan Inspector renders stored values (section 15): every counterfactual
figure below is read straight from the persisted Plan, never recomputed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import APIModel, ModeInfo

Freshness = Literal["realtime", "fresh", "recent", "stable"]
CacheLayer = Literal["exact", "semantic", "archive", "live", "mock", "replay", "miss", "skipped"]


# --------------------------------------------------------------------------
# requests
# --------------------------------------------------------------------------
class PlanRequest(APIModel):
    intent: str = Field(min_length=3, max_length=2000)
    project_id: str | None = None
    budget: int | None = Field(default=None, ge=1, le=100000)


class SearchRequest(APIModel):
    intent: str = Field(min_length=3, max_length=2000)
    project_id: str | None = None
    budget: int | None = Field(default=None, ge=1, le=100000)
    # When true the server allocates the run, returns 202 with its id, and
    # executes it in-process while the client tails GET /v1/runs/{id}/stream.
    # This is still interactive execution - it is deliberately NOT routed
    # through Kafka (section 42).
    stream: bool = False


class RunRequest(SearchRequest):
    plan_id: str | None = None


class FalseHitReportRequest(APIModel):
    step_id: str | None = None
    note: str = Field(default="", max_length=2000)
    invalidate_entry: bool = True


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------
class BindingView(APIModel):
    param: str
    source: str
    from_engine: str | None = None
    from_step: int | None = None
    from_field: str | None = None


class CacheStateView(APIModel):
    layer: str
    available: bool = False
    acceptable: bool = False
    warm: bool = False
    freshness_requirement: str = "stable"
    age_seconds: int | None = None
    ttl_remaining: int | None = None
    ttl_source: str | None = None
    similarity: float | None = None
    matched_query: str | None = None
    reason: str = ""
    guard_rejections: int = 0


class PlanStepView(APIModel):
    index: int
    engine: str
    label: str = ""
    depends_on: list[int] = Field(default_factory=list)
    fan_out: int = 1
    cost: int = 1
    pii_risk: str = "low"
    bindings: list[BindingView] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    freshness_requirement: str = "stable"
    warm: bool = False
    cache_state: dict[str, Any] = Field(default_factory=dict)


class WarmStepView(APIModel):
    index: int
    engine: str
    layer: str | None = None
    age_seconds: int | None = None
    credits_avoided: int = 0
    reason: str | None = None


class BudgetReductionItem(APIModel):
    type: Literal["sampling", "fan_out_cap", "omitted_step"]
    step: int
    engine: str = ""
    original: int
    reduced: int
    # Every reduction must carry this. A planner that silently truncates is
    # worse than one that refuses (section 16).
    impact_note: str


class BudgetReductionView(APIModel):
    applied: bool
    reductions: list[BudgetReductionItem] = Field(default_factory=list)
    full_plan_cost: int = 0
    selected_plan_cost: int = 0
    note: str = ""


class RejectedAlternativeView(APIModel):
    plan: str
    label: str = ""
    strategy: str = ""
    engines: list[str] = Field(default_factory=list)
    coverage: str = "full"
    naive_cost: int = 0
    marginal_cost: int = 0
    naive_rank: int = 0
    marginal_rank: int = 0
    warm_steps: list[int] = Field(default_factory=list)
    reason: str | None = None
    trade_off_note: str | None = None
    feasible_within_budget: bool = True


class RejectedEngineView(APIModel):
    engine: str
    reason: str = ""
    score: float | None = None
    hallucinated: bool = False


class PlanCandidateView(APIModel):
    id: str
    label: str
    strategy: str
    engines: list[str]
    hops: int
    naive_cost: int
    marginal_cost: int
    warm_step_indices: list[int] = Field(default_factory=list)
    cache_state: list[dict[str, Any]] = Field(default_factory=list)
    coverage: str
    confidence: float
    naive_rank: int
    marginal_rank: int
    selected: bool
    feasible_within_budget: bool
    rejection_reason: str | None = None
    trade_off_note: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)


class FreshnessRequirementView(APIModel):
    engine: str
    step: int
    requirement: str
    signals: list[str] = Field(default_factory=list)


class StageTraceEvent(APIModel):
    stage: str
    status: str
    elapsed_ms: float
    detail: dict[str, Any] = Field(default_factory=dict)


class PlanResponse(APIModel):
    id: str
    org_id: str
    project_id: str
    intent: str
    normalized_intent: str = ""
    steps: list[PlanStepView] = Field(default_factory=list)
    parameter_bindings: dict[str, Any] = Field(default_factory=dict)

    naive_cost: int
    marginal_cost: int
    projected_full_scale_cost: int | None = None
    savings: int = 0

    warm_steps: list[WarmStepView] = Field(default_factory=list)
    freshness_requirements: list[FreshnessRequirementView] = Field(default_factory=list)
    budget_reduction: BudgetReductionView | None = None

    confidence: float
    catalog_version: str
    candidate_count: int
    single_candidate_reason: str | None = None

    rejected_alternatives: list[RejectedAlternativeView] = Field(default_factory=list)
    rejected_engines: list[RejectedEngineView] = Field(default_factory=list)
    candidates: list[PlanCandidateView] = Field(default_factory=list)

    cold_winner_candidate_id: str | None = None
    marginal_replan_changed_selection: bool = False
    replan_explanation: str | None = None

    budget_limit: int | None = None
    planner_latency_ms: float = 0.0
    mode: str = "replay"
    stage_trace: list[StageTraceEvent] = Field(default_factory=list)
    created_at: datetime


# --------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------
class StepResponse(APIModel):
    id: str
    index: int
    engine: str
    label: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)
    fan_out: int = 1
    status: str
    cache_layer: str | None = None
    matched_query: str | None = None
    similarity: float | None = None
    age_seconds: int | None = None
    ttl_source: str | None = None
    freshness_requirement: str = "stable"
    credits: int = 0
    latency_ms: float = 0.0
    confidence: float = 0.0
    payload_ref: str | None = None
    payload_bytes: int | None = None
    serpapi_search_id: str | None = None
    http_status: int | None = None
    mode: str = "replay"
    pii_risk: str = "low"
    error_code: str | None = None
    error_message: str | None = None
    extracted: dict[str, Any] = Field(default_factory=dict)


class RunSummary(APIModel):
    id: str
    project_id: str
    plan_id: str | None = None
    intent: str
    status: str
    trigger: str
    credits_spent: int
    credits_saved: int
    naive_cost: int
    marginal_cost: int
    mode: str
    duration_ms: float
    error_code: str | None = None
    created_at: datetime


class RunResponse(RunSummary):
    principal_id: str | None = None
    principal_type: str = "user"
    cache_summary: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    results_ref: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    replay_of_run_id: str | None = None
    expires_at: datetime | None = None
    max_pii_risk: str = "low"
    steps: list[StepResponse] = Field(default_factory=list)
    plan: PlanResponse | None = None


class SearchResponse(APIModel):
    run: RunResponse
    plan: PlanResponse
    results: dict[str, Any] = Field(default_factory=dict)
    mode: ModeInfo
    provenance: dict[str, Any] = Field(default_factory=dict)


class SearchAccepted(APIModel):
    """202 for the streaming variant: the run exists, execution is in flight."""

    run_id: str
    stream_url: str
    mode: ModeInfo
    status: str = "running"


class PayloadResponse(APIModel):
    """Raw SERP payload. Permission-gated separately from run visibility."""

    step_id: str
    engine: str
    payload_ref: str
    payload: dict[str, Any]
    pii_risk: str
    mode: str


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------
class SubstituteView(APIModel):
    engine: str
    coverage: Literal["full", "partial", "narrow"]
    note: str = ""
    shared_tags: list[str] = Field(default_factory=list)


class CatalogEngineView(APIModel):
    engine: str
    purpose: str
    capability_tags: list[str] = Field(default_factory=list)
    substitutes: list[SubstituteView] = Field(default_factory=list)
    single_source_note: str = ""
    requires: dict[str, Any] = Field(default_factory=dict)
    optional: list[str] = Field(default_factory=list)
    produces: dict[str, Any] = Field(default_factory=dict)
    cost: int = 1
    latency_class: str = "medium"
    volatility_prior: str = "7d"
    locale_sensitive: list[str] = Field(default_factory=list)
    pii_risk: str = "low"
    docs_url: str = ""
    depends_on: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)


class CatalogEdgeView(APIModel):
    from_engine: str
    to_engine: str
    produces_field: str
    satisfies_param: str
    param_type: str = "string"
    fan_out_hint: int = 1


class CatalogResponse(APIModel):
    version: str
    released: str = ""
    source: str = ""
    notes: str = ""
    engine_count: int
    edge_count: int
    substitute_count: int
    capability_tags: dict[str, str] = Field(default_factory=dict)
    engines: list[CatalogEngineView] = Field(default_factory=list)
    edges: list[CatalogEdgeView] = Field(default_factory=list)
    substitute_edges: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "BindingView",
    "BudgetReductionItem",
    "BudgetReductionView",
    "CacheLayer",
    "CacheStateView",
    "CatalogEdgeView",
    "CatalogEngineView",
    "CatalogResponse",
    "FalseHitReportRequest",
    "Freshness",
    "FreshnessRequirementView",
    "PayloadResponse",
    "PlanCandidateView",
    "PlanRequest",
    "PlanResponse",
    "PlanStepView",
    "RejectedAlternativeView",
    "RejectedEngineView",
    "RunRequest",
    "RunResponse",
    "RunSummary",
    "SearchAccepted",
    "SearchRequest",
    "SearchResponse",
    "StageTraceEvent",
    "StepResponse",
    "SubstituteView",
    "WarmStepView",
]
