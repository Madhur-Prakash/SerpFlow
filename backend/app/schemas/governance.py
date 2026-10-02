"""Budgets, cache, analytics, benchmarks, audit and alert schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import APIModel

BudgetScope = Literal["organization", "project", "api_key", "session"]
BudgetPeriod = Literal["daily", "weekly", "monthly", "total"]
ExhaustionMode = Literal["stale", "error", "queue"]


# --------------------------------------------------------------------------
# budgets
# --------------------------------------------------------------------------
class BudgetCreate(APIModel):
    scope: BudgetScope
    scope_id: str
    name: str = Field(default="", max_length=160)
    limit_credits: int = Field(ge=1, le=10_000_000)
    period: BudgetPeriod = "monthly"
    alert_at: float = Field(default=0.8, ge=0.1, le=1.0)
    on_exhausted: ExhaustionMode = "error"


class BudgetUpdate(APIModel):
    name: str | None = Field(default=None, max_length=160)
    limit_credits: int | None = Field(default=None, ge=1, le=10_000_000)
    alert_at: float | None = Field(default=None, ge=0.1, le=1.0)
    on_exhausted: ExhaustionMode | None = None
    enabled: bool | None = None


class BudgetResponse(APIModel):
    id: str
    org_id: str
    scope: BudgetScope
    scope_id: str
    name: str
    limit_credits: int
    current_usage: int
    remaining: int
    utilization: float
    period: BudgetPeriod
    period_started_at: datetime | None = None
    period_ends_at: datetime | None = None
    alert_at: float
    on_exhausted: ExhaustionMode
    enabled: bool
    created_at: datetime


class BudgetOverview(APIModel):
    budgets: list[BudgetResponse] = Field(default_factory=list)
    credits_spent_total: int = 0
    credits_saved_total: int = 0
    projected_exhaustion: dict[str, Any] | None = None
    # Internal SerpFlow ledger and upstream SerpApi quota are reported side by
    # side and never merged (section 40).
    upstream_quota: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------
class CacheEntryResponse(APIModel):
    id: str
    project_id: str
    partition_key: str
    engine: str
    gl: str
    hl: str
    location: str
    query_text: str
    request_hash: str
    numerals: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)
    result_count: int
    payload_bytes: int
    credits_cost: int
    ttl_seconds: int
    ttl_source: str
    expires_at: datetime
    hit_count: int
    refresh_count: int
    last_hit_at: datetime | None = None
    pii_risk: str
    mode: str
    invalidated_at: datetime | None = None
    created_at: datetime


class GuardRejectionResponse(APIModel):
    id: str
    engine: str
    incoming_query: str
    candidate_query: str
    similarity: float
    reason: str
    incoming_tokens: list[str] = Field(default_factory=list)
    candidate_tokens: list[str] = Field(default_factory=list)
    created_at: datetime


class CacheInvalidateRequest(APIModel):
    engine: str | None = None
    entry_id: str | None = None


class CacheDashboardResponse(APIModel):
    window_days: int
    layers: dict[str, int]
    hit_rate: float
    entries: int
    bytes_stored: int
    partitions: list[dict[str, Any]] = Field(default_factory=list)
    guard_rejections: dict[str, Any] = Field(default_factory=dict)
    false_hit_reports: int = 0
    by_engine: list[dict[str, Any]] = Field(default_factory=list)
    redis: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# analytics
# --------------------------------------------------------------------------
class DashboardResponse(APIModel):
    window_days: int
    credits_spent: int
    credits_saved: int
    savings_ratio: float
    cache_hit_rate: float
    cache_layers: dict[str, int]
    runs: dict[str, int]
    spend_by_project: list[dict[str, Any]]
    recent_runs: list[dict[str, Any]]
    active_alerts: list[dict[str, Any]]
    upstream_quota: list[dict[str, Any]]
    projected_exhaustion: dict[str, Any] | None = None
    cross_project_benefit: dict[str, Any] = Field(default_factory=dict)
    marginal_replanning: dict[str, Any] = Field(default_factory=dict)


class SavingsDecompositionResponse(APIModel):
    window_days: int
    naive_execution: int
    actual_spend: int
    total_saved: int
    by_source: dict[str, int]
    waterfall: list[dict[str, Any]]


# --------------------------------------------------------------------------
# benchmarks
# --------------------------------------------------------------------------
class BenchmarkRunResponse(APIModel):
    id: str
    suite_version: str
    catalog_version: str
    system: str
    llm_model: str
    task_count: int
    correct_count: int
    accuracy: float
    engine_accuracy: float
    param_accuracy: float
    freshness_accuracy: float
    mean_confidence: float
    mean_latency_ms: float
    by_category: dict[str, Any]
    failure_modes: dict[str, Any]
    notes: str
    created_at: datetime
    finished_at: datetime | None = None


class BenchmarkTaskResponse(APIModel):
    id: str
    task_key: str
    suite_version: str
    intent: str
    expected_engines: list[str]
    acceptable_alternatives: list[list[str]] = Field(default_factory=list)
    expected_params: dict[str, Any] = Field(default_factory=dict)
    expected_freshness: str | None = None
    category: str
    difficulty: str
    notes: str


class RoutingEvalResponse(APIModel):
    id: str
    task_key: str
    system: str
    catalog_version: str
    predicted_engines: list[str]
    predicted_params: dict[str, Any]
    predicted_freshness: str | None = None
    candidate_count: int
    correct: bool
    engines_correct: bool
    params_correct: bool
    freshness_correct: bool
    matched_alternative: bool
    confidence: float
    latency_ms: float
    failure_mode: str | None = None
    detail: str


class BenchmarkRunRequest(APIModel):
    system: Literal["serpflow", "unaided_llm", "embedding_only"] = "serpflow"
    suite_version: str = "v1"
    limit: int | None = Field(default=None, ge=1, le=500)


# --------------------------------------------------------------------------
# audit and alerts
# --------------------------------------------------------------------------
class AuditEntryResponse(APIModel):
    id: str
    sequence: int
    actor_id: str | None = None
    actor_type: str
    actor_label: str
    action: str
    resource_type: str
    resource_id: str | None = None
    project_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    ip: str
    request_id: str | None = None
    prev_hash: str
    entry_hash: str
    created_at: datetime


class AuditVerifyResponse(APIModel):
    valid: bool
    entries_checked: int
    break_at_sequence: int | None = None
    reason: str | None = None
    head: str | None = None


class AlertResponse(APIModel):
    id: str
    project_id: str | None = None
    kind: str
    severity: str
    title: str
    message: str
    status: str
    context: dict[str, Any] = Field(default_factory=dict)
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class AlertUpdate(APIModel):
    status: Literal["open", "acknowledged", "resolved"]


class NotificationChannelCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    kind: Literal["email", "webhook", "slack"]
    target: str = Field(min_length=3, max_length=500)
    events: list[str] = Field(default_factory=list)
    secret: str | None = Field(default=None, max_length=200)


class NotificationChannelResponse(APIModel):
    id: str
    name: str
    kind: str
    target: str
    events: list[str] = Field(default_factory=list)
    enabled: bool
    last_delivery_at: datetime | None = None
    last_delivery_status: str | None = None
    failure_count: int
    created_at: datetime


__all__ = [
    "AlertResponse",
    "AlertUpdate",
    "AuditEntryResponse",
    "AuditVerifyResponse",
    "BenchmarkRunRequest",
    "BenchmarkRunResponse",
    "BenchmarkTaskResponse",
    "BudgetCreate",
    "BudgetOverview",
    "BudgetPeriod",
    "BudgetResponse",
    "BudgetScope",
    "BudgetUpdate",
    "CacheDashboardResponse",
    "CacheEntryResponse",
    "CacheInvalidateRequest",
    "DashboardResponse",
    "ExhaustionMode",
    "GuardRejectionResponse",
    "NotificationChannelCreate",
    "NotificationChannelResponse",
    "RoutingEvalResponse",
    "SavingsDecompositionResponse",
]
