# Observability

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="metrics: 22" src="https://img.shields.io/badge/metrics-22-E6522C">
  <img alt="OpenTelemetry: traces" src="https://img.shields.io/badge/OpenTelemetry-traces-425CC7?logo=opentelemetry&logoColor=white">
  <img alt="Prometheus: metrics" src="https://img.shields.io/badge/Prometheus-metrics-E6522C?logo=prometheus&logoColor=white">
  <img alt="Grafana: dashboards" src="https://img.shields.io/badge/Grafana-dashboards-F46800?logo=grafana&logoColor=white">
  <a href="../../backend/app/core/logging.py"><img alt="source: core/logging.py" src="https://img.shields.io/badge/source-core%2Flogging.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 13 min" src="https://img.shields.io/badge/read-13%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Observability** · page 39 of 57

**Structured logs, Prometheus metrics and OpenTelemetry traces.** A request id ties the logs to the response and the error body the caller sees, and with tracing on a trace id ties both to the trace ([correlating one request](#correlating-one-request)).

Implementation: [`app/core/logging.py`](../../backend/app/core/logging.py) · [`app/core/metrics.py`](../../backend/app/core/metrics.py) · [`app/core/telemetry.py`](../../backend/app/core/telemetry.py)

## Logging

- **Logifyx:** JSON by default, coloured and human-readable with `LOG_JSON=false`
  - the code default and the shipped `.env.example` both say `LOG_JSON=true`, so a laptop logs JSON too until you change it

```bash
LOG_LEVEL=INFO
LOG_JSON=true
LOG_OUTPUT=both          # console | file | both | none
LOG_FILE=logs/serpflow.log
```

- These are listed with every other variable in [secrets](../security/secrets.md#inventory)
- **Every record carries `service` and the same six identifiers**, injected from context variables by `ContextInjectionFilter` instead of passed by hand at each call site:

```
request_id  trace_id  run_id  org_id  project_id  principal_id
```

- `request_id` and `trace_id` are bound by the request middleware; `org_id`, `project_id` and `principal_id` once the caller is authenticated; `run_id` once a run exists. A value not bound yet is `null`

```json
{
  "timestamp": "2026-10-11 23:22:10",
  "level": "INFO",
  "logger": "serpflow.planner.cost",
  "function": "_log",
  "line": 802,
  "message": "marginal replan changed selection",
  "event": "planner.replan_changed_selection",
  "cold_winner": "...",
  "selected": "...",
  "cold_winner_cost": 4,
  "selected_naive": 5,
  "selected_marginal": 1,
  "service": "serpflow",
  "request_id": "8a9e9172...",
  "trace_id": null,
  "run_id": null,
  "org_id": "org_01M3WQ...",
  "project_id": "prj_01M3WQ...",
  "principal_id": "key_01M3WR..."
}
```

- **The shape is Logifyx's:** `timestamp`, `level`, `logger`, `function`, `line` and `message` first, then the `extra=` fields, then the identifiers. JSON keys are written with a space after the colon, which matters when you grep

- **Log lines are events with fields**, not sentences with values interpolated
  - `event` is a stable dotted name (`bootstrap.seed_done`, `kafka.degraded`, `email.failed`, `http.request`), so `event:"planner.replan_changed_selection"` is a **query**, not a substring search
  - every request except `/healthz`, `/readyz` and `/metrics` logs one `http.request` with method, path, status and duration in milliseconds
- **The root logger and each handler carry `CredentialRedactionFilter`**, scrubbing the message, the args, `extra=` attributes and the exception path ([credentials: never in a log](../security/credentials.md#never-in-a-log), [threat model](../security/threat-model.md#credential-leakage-through-logs))
  - it recognises SerpFlow keys (`sf_live_`, `sf_test_`), 64-hex SerpApi keys, Groq and OpenAI-style tokens, JWTs, and `key=value` pairs whose name looks sensitive
  - attributes named `api_key`, `password`, `token`, `ciphertext`, `payload` and the like are replaced outright with `[REDACTED]`
  - `tests/unit/test_security.py` asserts it
- **Library loggers are pinned to WARNING** (httpx, httpcore, aiokafka, botocore, boto3, urllib3, asyncio, SQLAlchemy, uvicorn.access, multipart), so the application's own events stay visible

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

- **22 series, in one registry**, each with a real producer: [`app/core/metrics.py`](../../backend/app/core/metrics.py). The tables below give each one's type, labels, where it is set and the page that explains what it measures
- **`METRICS_ENABLED=false`** turns `/metrics` into a 404 and stops the HTTP series being recorded
- **Every id-like label goes through `safe_label`**, which truncates to 64 characters and turns `None` into `"none"`. Labels carry ids and engine names, never credentials
- **Metrics are per process.** Prometheus scrapes the API, so a series set in a standalone [`make worker`](kafka.md#running-consumers) process (the quota gauges, `serpflow_adaptive_ttl_seconds`, consume-side Kafka counts) is only visible when the API ran that consumer in-process. The worker serves no `/metrics`

### The thesis metric

| Metric | Type | Labels | Set by | Measures |
| --- | --- | --- | --- | --- |
| `serpflow_marginal_replan_changed_selection_total` | counter | `project_id` | [`planner/cost.py`](../../backend/app/services/planner/cost.py) | [selection changed by marginal ranking](../architecture/marginal-replanning.md#what-changed_selection-means) |
| `serpflow_marginal_credits_avoided_total` | counter | `project_id` | [`planner/cost.py`](../../backend/app/services/planner/cost.py) | [`naive_cost - marginal_cost`](../architecture/marginal-replanning.md#costing-a-step) on the selected plan |

- **Times cache-aware re-ranking selected a different plan than cold ranking would have**
- The one number the whole system exists to move above zero
- **The e2e suite asserts it**, rather than asserting a cache hit ([`tests/e2e/test_marginal_replanning.py`](../../backend/tests/e2e/test_marginal_replanning.py))
- **Both are counted at planning time**, so a dry-run [`POST /v1/plan`](../api/overview.md#plan-without-executing) counts as well as an executed search

### Spend and savings

| Metric | Type | Labels | Set by | Measures |
| --- | --- | --- | --- | --- |
| `serpflow_credits_spent_total` | counter | `org_id`, `project_id`, `engine` | [`executor/service.py`](../../backend/app/services/executor/service.py) | credits for a credited call: `live` or `record`, never mock or replay ([execution modes](../product/execution-modes.md#the-four-modes)) |
| `serpflow_credits_saved_total` | counter | `org_id`, `project_id`, `source` | [`executor/service.py`](../../backend/app/services/executor/service.py) | credits a cache hit avoided, by layer ([savings by mechanism](../architecture/marginal-replanning.md#instrumentation)) |
| `serpflow_budget_utilization_ratio` | gauge | `scope`, `budget_id`, `project_id` | [`budgets/service.py`](../../backend/app/services/budgets/service.py) | `current_usage / limit` for each budget, at each [budget check](../architecture/executor.md#budget-enforcement) |

```
source = exact | semantic | archive        (routing is declared, but nothing increments it)
scope  = session | api_key | project | organization
```

- **Savings are broken down by mechanism:** "we saved credits" is not a claim until you can say which thing did it
  - `exact`, `semantic` and `archive` are cache layers, counted whenever `lookup()` returns a payload
  - **`routing`**, savings from picking a cheaper engine at all, is written to the [`budget_ledger`](../database/schema.md#governance) by `record_routing_saving` but **not** to this counter. Read it from `GET /v1/analytics/savings`, which reads the ledger
- **An empty SerpApi answer is still spend:** a "no results" response is billed and counted here ([an empty answer is still a billed answer](../architecture/executor.md#an-empty-answer-is-still-a-billed-answer))
- **The utilization gauge is set during the budget check**, so it moves when a call is about to spend, not when a budget is edited. It feeds [budget-aware reduction](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking) indirectly, through the same check

### Cache

| Metric | Type | Labels | Set by | Measures |
| --- | --- | --- | --- | --- |
| `serpflow_cache_hits_total` | counter | `layer`, `project_id` | [`cache/service.py`](../../backend/app/services/cache/service.py) | executor lookups, by [the layer that answered](../architecture/caching.md#two-entry-points) |
| `serpflow_cache_lookup_seconds` | histogram | `layer` | [`cache/service.py`](../../backend/app/services/cache/service.py) | one layer's lookup latency, planner `inspect()` included ([the Redis boundary](../architecture/caching.md#the-redis-boundary)) |
| `serpflow_semantic_guard_rejections_total` | counter | `engine`, `reason` | [`cache/service.py`](../../backend/app/services/cache/service.py) | near neighbours the [entity and numeral guard](../architecture/caching.md#the-entity-and-numeral-guard) refused |
| `serpflow_semantic_false_hit_reports_total` | counter | `project_id`, `engine` | [`api/v1/runs.py`](../../backend/app/api/v1/runs.py) | operator reports of a wrong semantic hit ([report a bad semantic hit](../api/examples.md#report-a-bad-semantic-hit)) |
| `serpflow_adaptive_ttl_seconds` | histogram | `engine`, `direction` | [`consumers/handlers.py`](../../backend/app/workers/consumers/handlers.py) | TTLs the [adaptive controller](../architecture/caching.md#adaptive-ttl) settled on |

```
layer     = exact | semantic | archive | miss        (cache_lookup_seconds: exact | semantic | archive)
reason    = numeral_mismatch | entity_mismatch | version_mismatch
direction = extended | shortened | unchanged
```

- **Redis hits and durable-index hits are both `layer="exact"`.** See [Redis: metrics](redis.md#metrics)
- **`semantic_guard_rejections_total` dropping to zero is a warning sign, not a good one**
  - the guard exists because embeddings place "Nvidia Q3 2024 revenue" and "Nvidia Q4 2024 revenue" side by side
  - a corpus with real numerals in it should be rejecting some ([rejections are evidence](../architecture/caching.md#rejections-are-evidence))
- **`adaptive_ttl_seconds` is only observed by the `serpflow.cache.refresh` consumer**, and nothing publishes to that topic at HEAD ([Kafka: what goes through it](kafka.md#what-goes-through-it-and-what-does-not)), so expect it to be empty

### Planner

| Metric | Type | Labels | Set by | Measures |
| --- | --- | --- | --- | --- |
| `serpflow_plan_latency_seconds` | histogram | `stage` | [`planner/service.py`](../../backend/app/services/planner/service.py) | time per [planner stage](../architecture/planner.md#observability) |
| `serpflow_plan_confidence` | histogram | none | [`planner/service.py`](../../backend/app/services/planner/service.py) | the selected plan's confidence ([stage B](../architecture/planner.md#stage-b-select)) |
| `serpflow_plan_candidates_count` | histogram | none | [`planner/service.py`](../../backend/app/services/planner/service.py) | candidates stage D emitted ([candidate plurality](../architecture/planner.md#candidate-plurality-is-a-hard-requirement)) |
| `serpflow_routing_accuracy` | gauge | `system`, `catalog_version` | [`benchmark/service.py`](../../backend/app/services/benchmark/service.py) | the last benchmark run's accuracy ([scoring](../product/benchmark.md#scoring)) |

```
stage  = retrieve | select | synthesize | pathfind | marginal_cost | total
system = serpflow | unaided_llm | embedding_only
```

- **`plan_candidates_count` collapsing to 1** means the catalog lost its substitute edges, or retrieval narrowed. The replanning thesis cannot hold with one candidate
- **`routing_accuracy` is labelled by `catalog_version`**, so a routing regression is attributable to a specific catalog change
- **It is set in the process that ran the benchmark:** `POST /v1/benchmarks/run` sets it on the API; [`make benchmark`](../product/benchmark.md#running-it) runs in a CLI process that nothing scrapes

### Execution and upstream

| Metric | Type | Labels | Set by | Measures |
| --- | --- | --- | --- | --- |
| `serpflow_run_duration_seconds` | histogram | `status` | [`executor/service.py`](../../backend/app/services/executor/service.py) | wall-clock time of an executed run ([the executor](../architecture/executor.md)) |
| `serpflow_step_latency_seconds` | histogram | `engine`, `cache_layer` | [`executor/service.py`](../../backend/app/services/executor/service.py) | one step's latency, by the layer that served it ([per-step record](../architecture/executor.md#per-step-record)) |
| `serpflow_upstream_errors_total` | counter | `engine`, `status` | [`executor/service.py`](../../backend/app/services/executor/service.py) | SerpApi answers that are errors ([upstream failures](../architecture/executor.md#upstream-failures)) |
| `serpflow_upstream_quota_remaining` | gauge | `credential_fingerprint` | [`consumers/handlers.py`](../../backend/app/workers/consumers/handlers.py) | searches left on the SerpApi account ([validation and revocation](../security/credentials.md#validation-and-revocation)) |
| `serpflow_upstream_quota_divergence` | gauge | `credential_fingerprint` | [`consumers/handlers.py`](../../backend/app/workers/consumers/handlers.py) | ledger spend minus SerpApi's spend since the last reconcile |

```
status (run)       = succeeded | failed
cache_layer        = exact | semantic | archive | live | mock
status (upstream)  = the HTTP status SerpApi returned
```

- **Quota metrics are labelled by `credential_fingerprint`**, never by the credential ([the fingerprint](../security/credentials.md#the-fingerprint))
- **Both quota gauges are set by the `serpflow.quota.reconcile` consumer**, which runs when `POST /v1/credentials/reconcile-quota` queues it
- **`step_latency_seconds` is labelled by `cache_layer`**, so the latency gap between a hit and a live call is directly visible. A replayed step is labelled `live`
- **`upstream_errors_total` does not count** an empty "no results" answer (billed, not an error), a 401 (`CREDENTIAL_REJECTED`) or quota exhaustion (`UPSTREAM_QUOTA_EXHAUSTED`): those raise before the counter

### HTTP and Kafka

| Metric | Type | Labels | Set by | Measures |
| --- | --- | --- | --- | --- |
| `serpflow_api_requests_total` | counter | `method`, `route`, `status` | [`api/middleware.py`](../../backend/app/api/middleware.py) | requests handled ([API overview](../api/overview.md)) |
| `serpflow_api_request_seconds` | histogram | `method`, `route` | [`api/middleware.py`](../../backend/app/api/middleware.py) | request latency |
| `serpflow_kafka_messages_total` | counter | `topic`, `direction`, `status` | [`workers/kafka.py`](../../backend/app/workers/kafka.py) | messages produced and consumed ([Kafka: metrics](kafka.md#metrics)) |

```
direction = produce | consume
status    = ok | error | skipped        (skipped: produce with no broker, message dropped)
```

- **`route` is the template** (`/v1/runs/{run_id}`), not the resolved path, so cardinality stays bounded. A path that matches no route falls back to the raw path
- **The HTTP series include `/healthz`, `/readyz` and `/metrics`** themselves; only the request log line skips them

## Dashboards

```bash
docker compose --profile observability up -d
```

```
Prometheus  http://localhost:9090
Grafana     http://localhost:3001   GRAFANA_USER / GRAFANA_PASSWORD (both default admin)
```

- **Prometheus scrapes `backend:8000/metrics` every 15 seconds** ([`docker/prometheus/prometheus.yml`](../../docker/prometheus/prometheus.yml)), job `serpflow-backend`
  - `backend` is the compose service, so the target is reachable only when the API runs in a container. Against `make backend` on the host, point the target at the host instead
- **Grafana is provisioned** with the Prometheus datasource, from [`docker/grafana/provisioning/`](../../docker/grafana/provisioning). **No dashboards ship**: build them on the [metrics](#metrics) above
- Both sit behind the `observability` (and `full`) compose profile: [Docker](../deployment/docker.md#running)
- **On a server**, keep both private and reach them over an SSH tunnel: [deployment guide, step 12](../deployment/deployment-guide.md#12-observability)

## Alerting

Rules worth running. **The first is the one specific to this system.** None of them ship: `prometheus.yml` has no `rule_files` and there is no Alertmanager in the compose file.

```yaml
- alert: SemanticFalseHits
  expr: sum(increase(serpflow_semantic_false_hit_reports_total[1h])) > 0
  labels: { severity: critical }
  annotations:
    summary: "The semantic cache served data an operator judged wrong"

- alert: GuardSilent
  expr: sum(increase(serpflow_semantic_guard_rejections_total[24h])) == 0
          and sum(increase(serpflow_cache_hits_total{layer="semantic"}[24h])) > 100
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
  expr: sum(rate(serpflow_upstream_errors_total[5m])) > 0.1

- alert: PlanCandidatesCollapsed
  expr: histogram_quantile(0.9, sum by (le) (rate(serpflow_plan_candidates_count_bucket[1h]))) < 2
```

- **`SemanticFalseHits` is a correctness page**, not a performance one: it means the product returned wrong data. Everything else here is capacity or cost
- **`sum(...)` on both sides of `GuardSilent`'s `and`** matters: the two counters carry different labels, so without it the `and` matches nothing and the alert never fires
- **`QuotaDivergence` and `UpstreamQuotaLow`** only move after a reconciliation: [`BUDGET_EXHAUSTED` against `UPSTREAM_QUOTA_EXHAUSTED`](troubleshooting.md#budget_exhausted-against-upstream_quota_exhausted)
- **In-application alerts** are rows in the [`alerts` table](../database/schema.md#governance), separate from Prometheus:
  - budget threshold (`budget.threshold_reached`, at the budget's `alert_at` or `DEFAULT_BUDGET_ALERT_RATIO`) and exhaustion (`budget.exhausted`), written by the budget service as the call is checked, once per budget per period
  - `credential.validation_failed` and `upstream.quota_divergence` (past 5 credits), written by the [Kafka consumers](kafka.md#topics)
  - `GET /v1/alerts` lists them; `PATCH /v1/alerts/{id}` acknowledges or resolves one ([governance endpoints](../api/overview.md#governance))
  - **none of these reach a notification channel at HEAD.** Channel delivery runs only in the `serpflow.webhooks` consumer, which is fed only by `serpflow.alerts`, which nothing publishes to yet. See [Kafka: what goes through it](kafka.md#what-goes-through-it-and-what-does-not) and [email](email.md#what-gets-sent)

## Tracing

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318
```

- **The exporter is OTLP over HTTP** (`opentelemetry-exporter-otlp-proto-http`), and `/v1/traces` is appended to the endpoint. Point it at a collector's HTTP port (4318 by default), not the gRPC one (4317)
- **`OTEL_ENABLED=true` with no endpoint** exports to the console when `DEBUG` is true, and nowhere otherwise
- **With `OTEL_ENABLED=false`, the default,** every span is a no-op and no trace ids exist
- **FastAPI is auto-instrumented**, with `healthz`, `readyz` and `metrics` excluded
  - `/healthz` producing a trace per second is noise that makes real traces harder to find
- **The planner and executor open explicit spans** ([`app/core/telemetry.py`](../../backend/app/core/telemetry.py)):

```
serpflow.plan
|- serpflow.catalog.retrieve
|- serpflow.plan.select
|- serpflow.plan.synthesize
|- serpflow.plan.pathfind
|- serpflow.plan.candidates
`- serpflow.plan.marginal_cost
serpflow.execute
`- serpflow.execute.step
   `- serpflow.upstream.call
```

- `serpflow.cache.lookup` is defined in `telemetry.py` but no code opens it, so cache lookups appear inside the step span rather than as their own
- **With tracing on, `trace_id` is on every log record and `X-SerpFlow-Trace-Id` on every response:** a user-reported problem goes from response header → trace → logs without a search. With it off, neither is set
- **Best effort:** the FastAPI instrumentation is wrapped so a failure there cannot stop the service from booting. The OpenTelemetry packages themselves are hard dependencies in `pyproject.toml`

## Health

```http
GET /healthz    liveness. Touches no dependency.
GET /readyz     readiness. Checks postgres, redis, kafka, object storage; reports catalog and LLM provider.
```

- **`/readyz` returns 503 only when PostgreSQL is unreachable**
- **Redis and Kafka report as degraded**, not failed:
  - Redis is a hot cache, not a source of truth ([Redis: degradation](redis.md#degradation))
  - Kafka carries only background work ([Kafka: degradation](kafka.md#degradation))
  - a readiness probe that failed on a Redis blip would take the API out for a dependency it does not need to serve a search
- **Object storage is reported but does not change the overall status**
- Both endpoints are in the [infrastructure endpoints](../api/overview.md#infrastructure); the compose healthcheck polls `/healthz`

```bash
make health          # GET /readyz, printed with colour by the CLI
```

## Correlating one request

```
X-Request-Id             <- in the response and in every log record
X-SerpFlow-Trace-Id      <- the trace, when tracing is on
X-SerpFlow-Run-Id        <- the run, which the Run Inspector will explain
```

- **An incoming `X-Request-Id` is kept**, so a proxy or client can choose the id; otherwise the middleware generates one ([`app/api/middleware.py`](../../backend/app/api/middleware.py))
- **The error body carries `request_id` too**, so a user can quote it from a failure message and it leads straight to the logs ([errors](../api/overview.md#errors), [provenance headers](../api/overview.md#provenance-headers))
- **The run id opens the [Run Inspector](../architecture/frontend.md#routes)**, which shows the plan, every step and its cache layer

## Related

- [Caching](../architecture/caching.md#metrics): the cache metrics in the context of the four layers
- [Marginal-cost replanning](../architecture/marginal-replanning.md#instrumentation): what the thesis metric and the savings counters mean
- [Executor](../architecture/executor.md#upstream-failures): when `serpflow_upstream_errors_total` moves and when it does not
- [Kafka](kafka.md#metrics): `serpflow_kafka_messages_total` and the consumers that set the quota gauges
- [Redis](redis.md#metrics): why Redis hits and durable-index hits share one label
- [Credentials](../security/credentials.md#never-in-a-log): the redaction rules behind the log filter
- [Deployment guide](../deployment/deployment-guide.md#12-observability): Prometheus and Grafana on a server
- [Troubleshooting](troubleshooting.md#logs-and-resources): the SQLAlchemy INFO lines and finding a request in the log
- [Production](../deployment/production.md): what to watch and alert on in a real deployment

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Email](../operations/email.md) | [Docs index](../README.md) | [Kafka](../operations/kafka.md) |
