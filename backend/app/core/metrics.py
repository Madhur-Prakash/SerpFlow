"""Prometheus metrics (section 65).

Every metric here has a real producer. The one that matters most is
``serpflow_marginal_replan_changed_selection_total``: it counts how often
cache-aware replanning actually changed the chosen plan. That is the product
thesis, instrumented.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST as OPENMETRICS_CT

REGISTRY = CollectorRegistry(auto_describe=True)

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

credits_spent_total = Counter(
    "serpflow_credits_spent_total",
    "SerpApi credits actually consumed by live upstream calls.",
    ["org_id", "project_id", "engine"],
    registry=REGISTRY,
)

credits_saved_total = Counter(
    "serpflow_credits_saved_total",
    "Credits avoided, decomposed by the mechanism that avoided them.",
    ["org_id", "project_id", "source"],  # routing | exact | semantic | archive
    registry=REGISTRY,
)

cache_hits_total = Counter(
    "serpflow_cache_hits_total",
    "Cache lookups resolved, by layer.",
    ["layer", "project_id"],  # exact | semantic | archive | miss
    registry=REGISTRY,
)

cache_lookup_seconds = Histogram(
    "serpflow_cache_lookup_seconds",
    "Latency of a single cache-layer lookup.",
    ["layer"],
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    registry=REGISTRY,
)

plan_latency_seconds = Histogram(
    "serpflow_plan_latency_seconds",
    "End-to-end planner latency, stages A through D plus marginal costing.",
    ["stage"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

plan_confidence = Histogram(
    "serpflow_plan_confidence",
    "Selector confidence for the chosen plan.",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
    registry=REGISTRY,
)

plan_candidates_count = Histogram(
    "serpflow_plan_candidates_count",
    "How many candidate plans stage D emitted.",
    buckets=(1, 2, 3, 4, 5, 6, 8, 10, 15),
    registry=REGISTRY,
)

marginal_replan_changed_selection_total = Counter(
    "serpflow_marginal_replan_changed_selection_total",
    (
        "Times cache-aware marginal-cost re-ranking selected a different plan "
        "than the cold (naive-cost) ranking would have. This is the thesis."
    ),
    ["project_id"],
    registry=REGISTRY,
)

marginal_credits_avoided_total = Counter(
    "serpflow_marginal_credits_avoided_total",
    "naive_cost minus marginal_cost on the selected plan.",
    ["project_id"],
    registry=REGISTRY,
)

budget_utilization_ratio = Gauge(
    "serpflow_budget_utilization_ratio",
    "current_usage / limit for each active budget.",
    ["scope", "budget_id", "project_id"],
    registry=REGISTRY,
)

upstream_errors_total = Counter(
    "serpflow_upstream_errors_total",
    "Errors returned by SerpApi.",
    ["engine", "status"],
    registry=REGISTRY,
)

semantic_false_hit_reports_total = Counter(
    "serpflow_semantic_false_hit_reports_total",
    "Operator reports of a bad semantic cache hit, filed from the Run Inspector.",
    ["project_id", "engine"],
    registry=REGISTRY,
)

semantic_guard_rejections_total = Counter(
    "serpflow_semantic_guard_rejections_total",
    "Semantic candidates rejected by the deterministic entity/numeral guard.",
    ["engine", "reason"],  # numeral_mismatch | entity_mismatch | version_mismatch
    registry=REGISTRY,
)

upstream_quota_remaining = Gauge(
    "serpflow_upstream_quota_remaining",
    "Searches left on the SerpApi account, as reported by the account endpoint.",
    ["credential_fingerprint"],
    registry=REGISTRY,
)

upstream_quota_divergence = Gauge(
    "serpflow_upstream_quota_divergence",
    "Internal ledger spend minus upstream reported spend since last reconcile.",
    ["credential_fingerprint"],
    registry=REGISTRY,
)

run_duration_seconds = Histogram(
    "serpflow_run_duration_seconds",
    "Wall-clock duration of an executed run.",
    ["status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

step_latency_seconds = Histogram(
    "serpflow_step_latency_seconds",
    "Per-step execution latency, labelled by the cache layer that served it.",
    ["engine", "cache_layer"],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

routing_accuracy = Gauge(
    "serpflow_routing_accuracy",
    "Benchmark routing accuracy by system and catalog version.",
    ["system", "catalog_version"],
    registry=REGISTRY,
)

adaptive_ttl_seconds = Histogram(
    "serpflow_adaptive_ttl_seconds",
    "TTL values the adaptive controller settled on.",
    ["engine", "direction"],  # extended | shortened | unchanged
    buckets=(300, 3600, 21600, 86400, 604800, 2592000, 7776000),
    registry=REGISTRY,
)

api_requests_total = Counter(
    "serpflow_api_requests_total",
    "HTTP requests handled.",
    ["method", "route", "status"],
    registry=REGISTRY,
)

api_request_seconds = Histogram(
    "serpflow_api_request_seconds",
    "HTTP request latency.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

kafka_messages_total = Counter(
    "serpflow_kafka_messages_total",
    "Kafka messages produced or consumed.",
    ["topic", "direction", "status"],
    registry=REGISTRY,
)


def render() -> bytes:
    return generate_latest(REGISTRY)


def safe_label(value: object) -> str:
    """Prometheus labels must be bounded-cardinality strings."""
    if value is None:
        return "none"
    return str(value)[:64]


__all__ = [
    "CONTENT_TYPE",
    "OPENMETRICS_CT",
    "REGISTRY",
    "adaptive_ttl_seconds",
    "api_request_seconds",
    "api_requests_total",
    "budget_utilization_ratio",
    "cache_hits_total",
    "cache_lookup_seconds",
    "credits_saved_total",
    "credits_spent_total",
    "kafka_messages_total",
    "marginal_credits_avoided_total",
    "marginal_replan_changed_selection_total",
    "plan_candidates_count",
    "plan_confidence",
    "plan_latency_seconds",
    "render",
    "routing_accuracy",
    "run_duration_seconds",
    "safe_label",
    "semantic_false_hit_reports_total",
    "semantic_guard_rejections_total",
    "step_latency_seconds",
    "upstream_errors_total",
    "upstream_quota_divergence",
    "upstream_quota_remaining",
]
