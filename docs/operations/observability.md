# Observability

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="metrics: 22" src="https://img.shields.io/badge/metrics-22-E6522C">
  <img alt="OpenTelemetry: traces" src="https://img.shields.io/badge/OpenTelemetry-traces-425CC7?logo=opentelemetry&logoColor=white">
  <img alt="Prometheus: metrics" src="https://img.shields.io/badge/Prometheus-metrics-E6522C?logo=prometheus&logoColor=white">
  <img alt="Grafana: dashboards" src="https://img.shields.io/badge/Grafana-dashboards-F46800?logo=grafana&logoColor=white">
  <a href="../../backend/app/core/logging.py"><img alt="source: core/logging.py" src="https://img.shields.io/badge/source-core%2Flogging.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Observability** · page 32 of 50

**Structured logs, Prometheus metrics and OpenTelemetry traces**, correlated by a request id that appears in all three, and in the error response the caller sees.

Implementation: [`app/core/logging.py`](../../backend/app/core/logging.py) · [`app/core/metrics.py`](../../backend/app/core/metrics.py) · [`app/core/telemetry.py`](../../backend/app/core/telemetry.py)

## Logging

- **Logifyx:** JSON in production, coloured and human-readable locally

```bash
LOG_LEVEL=INFO
LOG_JSON=true
LOG_OUTPUT=both          # console | file | both | none
LOG_FILE=logs/serpflow.log
```

- **Every record carries the same six identifiers**, injected from context variables by `ContextInjectionFilter` instead of passed by hand at each call site:

```
request_id  trace_id  run_id  org_id  project_id  principal_id
```

```json
{
  "event": "cache.semantic_hit",
  "level": "info",
  "service": "serpflow",
  "request_id": "8a9e9172...",
  "trace_id": "4bf92f35...",
  "run_id": "run_01M3WT...",
  "org_id": "org_01M3WQ...",
  "project_id": "prj_01M3WQ...",
  "engine": "google_maps",
  "similarity": 0.973,
  "age_seconds": 412
}
```

- **Log lines are events with fields**, not sentences with values interpolated
  - `event` is a stable dotted name, so `event:"cache.semantic_hit"` is a **query**, not a substring search
- **The root logger carries `CredentialRedactionFilter`**, scrubbing the message, the args, `extra=` attributes and the exception path. See [secrets](../security/secrets.md)
- **Library loggers are pinned to WARNING** (httpx, aiokafka, botocore, SQLAlchemy, uvicorn.access), so the application's own events stay visible

### Known issue: SQLAlchemy INFO lines

- **Symptom:** the log fills with `sqlalchemy.engine.Engine` (DDL, statements) and `sqlalchemy.orm.mapper.Mapper` (mapper configuration) lines at INFO. A first container boot writes thousands of them, and `logs/serpflow.log` grows by megabytes
- **Cause:** those two **child** loggers end up with an explicit level of `INFO`. Pinning their parents (`sqlalchemy.engine`, `sqlalchemy.orm`) to WARNING cannot override a level set on the child itself
- **Check it:**

```bash
docker compose exec backend python -c "import logging; from app.core.logging import setup_logging; setup_logging(); print(logging.getLevelName(logging.getLogger('sqlalchemy.orm.mapper.Mapper').level))"   # INFO
```

- **Fix:** in `setup_logging`, also reset every existing child logger under the noisy prefixes (for example, set them to `NOTSET` so they inherit WARNING)

## Metrics

```bash
curl -s http://localhost:8000/metrics
```

- **22 series**, each with a real producer

### The thesis metric

```
serpflow_marginal_replan_changed_selection_total
```

- **Times cache-aware re-ranking selected a different plan than cold ranking would have**
- The one number the whole system exists to move above zero
- **The e2e suite asserts it**, rather than asserting a cache hit

```
serpflow_marginal_credits_avoided_total{project_id}
```

- `naive_cost - marginal_cost` on the selected plan

### Spend and savings

```
serpflow_credits_spent_total{org_id, project_id, engine}
serpflow_credits_saved_total{org_id, project_id, source}
    source = routing | exact | semantic | archive
```

- **Savings are broken down by mechanism:** "we saved credits" is not a claim until you can say which of four things did it
  - `routing` is savings from picking a cheaper engine at all
  - the other three are cache layers

### Cache

```
serpflow_cache_hits_total{layer, project_id}      exact | semantic | archive | miss
serpflow_cache_lookup_seconds{layer}
serpflow_semantic_guard_rejections_total{engine, reason}
serpflow_semantic_false_hit_reports_total{project_id, engine}
serpflow_adaptive_ttl_seconds{engine, direction}  extended | shortened | unchanged
```

- **`semantic_guard_rejections_total` dropping to zero is a warning sign, not a good one**
  - the guard exists because embeddings place "Nvidia Q3 2024 revenue" and "Nvidia Q4 2024 revenue" side by side
  - a corpus with real numerals in it should be rejecting some

### Planner

```
serpflow_plan_latency_seconds{stage}
serpflow_plan_confidence
serpflow_plan_candidates_count
serpflow_routing_accuracy{system, catalog_version}
```

- **`plan_candidates_count` collapsing to 1** means the catalog lost its substitute edges, or retrieval narrowed. The replanning thesis cannot hold with one candidate
- **`routing_accuracy` is labelled by `catalog_version`**, so a routing regression is attributable to a specific catalog change

### Execution and upstream

```
serpflow_run_duration_seconds{status}
serpflow_step_latency_seconds{engine, cache_layer}
serpflow_upstream_errors_total{engine, status}
serpflow_upstream_quota_remaining{credential_fingerprint}
serpflow_upstream_quota_divergence{credential_fingerprint}
serpflow_budget_utilization_ratio{scope, budget_id, project_id}
```

- **Quota metrics are labelled by `credential_fingerprint`**, never by the credential
- **`step_latency_seconds` is labelled by `cache_layer`**, so the latency gap between a hit and a live call is directly visible

### HTTP and Kafka

```
serpflow_api_requests_total{method, route, status}
serpflow_api_request_seconds{method, route}
serpflow_kafka_messages_total{topic, direction, status}
```

- **`route` is the template** (`/v1/runs/{run_id}`), not the resolved path, so cardinality stays bounded

## Dashboards

```bash
docker compose --profile observability up -d
```

```
Prometheus  http://localhost:9090
Grafana     http://localhost:3001   admin / GRAFANA_PASSWORD (default admin)
```

- **Prometheus scrapes `backend:8000/metrics` every 15 seconds**
- **Grafana is provisioned** with the Prometheus datasource, from [`docker/grafana/provisioning/`](../../docker/grafana/provisioning)
- **On a server**, keep both private and reach them over an SSH tunnel: [deployment guide, step 12](../deployment/deployment-guide.md#12-observability)

## Alerting

Rules worth running. **The first is the one specific to this system.**

```yaml
- alert: SemanticFalseHits
  expr: increase(serpflow_semantic_false_hit_reports_total[1h]) > 0
  labels: { severity: critical }
  annotations:
    summary: "The semantic cache served data an operator judged wrong"

- alert: GuardSilent
  expr: increase(serpflow_semantic_guard_rejections_total[24h]) == 0
          and increase(serpflow_cache_hits_total{layer="semantic"}[24h]) > 100
  labels: { severity: warning }
  annotations:
    summary: "The entity/numeral guard has stopped rejecting anything"

- alert: BudgetNearExhaustion
  expr: serpflow_budget_utilization_ratio > 0.9

- alert: UpstreamQuotaLow
  expr: serpflow_upstream_quota_remaining < 100

- alert: QuotaDivergence
  expr: abs(serpflow_upstream_quota_divergence) > 50
  annotations:
    summary: "Internal ledger and SerpApi disagree; the credential is in use elsewhere"

- alert: UpstreamErrors
  expr: rate(serpflow_upstream_errors_total[5m]) > 0.1

- alert: PlanCandidatesCollapsed
  expr: histogram_quantile(0.9, serpflow_plan_candidates_count) < 2
```

- **`SemanticFalseHits` is a correctness page**, not a performance one: it means the product returned wrong data. Everything else here is capacity or cost
- **In-application alerts** (budget thresholds, exhaustion, quota) are raised through `serpflow.alerts`, deduplicated by `dedupe_key`, and delivered to configured notification channels
  - `GET /v1/alerts` lists them; `PATCH /v1/alerts/{id}` acknowledges or resolves one

## Tracing

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
```

- **FastAPI is auto-instrumented**, with `healthz`, `readyz` and `metrics` excluded
  - `/healthz` producing a trace per second is noise that makes real traces harder to find
- **The planner, cache and executor open explicit spans**
- **`trace_id` is on every log record**, and `X-SerpFlow-Trace-Id` on every response: a user-reported problem goes from response header → trace → logs without a search
- **Best effort:** if an OpenTelemetry package is missing, setup logs and continues instead of failing to boot

## Health

```http
GET /healthz    liveness. Touches no dependency.
GET /readyz     readiness. Checks postgres, redis, kafka, storage, catalog.
```

- **`/readyz` returns 503 only when PostgreSQL is unreachable**
- **Redis and Kafka report as degraded**, not failed:
  - Redis is a hot cache, not a source of truth
  - Kafka carries only background work
  - a readiness probe that failed on a Redis blip would take the API out for a dependency it does not need to serve a search

```bash
make health
```

## Correlating one request

```
X-Request-Id             <- in the response and in every log record
X-SerpFlow-Trace-Id      <- the trace
X-SerpFlow-Run-Id        <- the run, which the Run Inspector will explain
```

- **The error body carries `request_id` too**, so a user can quote it from a failure message and it leads straight to the logs

## Related

- [Kafka](kafka.md)
- [Redis](redis.md)
- [Troubleshooting](troubleshooting.md)
- [Production](../deployment/production.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Email](../operations/email.md) | [Docs index](../README.md) | [Kafka](../operations/kafka.md) |
