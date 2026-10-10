# API overview

<p>
  <a href="../README.md#api"><img alt="docs: API" src="https://img.shields.io/badge/docs-API-009688?logo=readthedocs&logoColor=white"></a>
  <img alt="operations: 85" src="https://img.shields.io/badge/operations-85-009688">
  <img alt="paths: 74" src="https://img.shields.io/badge/paths-74-009688">
  <img alt="FastAPI: 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="OpenAPI: 3.1" src="https://img.shields.io/badge/OpenAPI-3.1-6BA539?logo=openapiinitiative&logoColor=white">
  <img alt="JWT: HS256" src="https://img.shields.io/badge/JWT-HS256-000000?logo=jsonwebtokens&logoColor=white">
  <a href="../../scripts/check_api.py"><img alt="source: scripts/check_api.py" src="https://img.shields.io/badge/source-scripts%2Fcheck__api.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [API](../README.md#api) › **API overview** · page 19 of 50

- **Base URL:** `http://localhost:8000`
- **Interactive OpenAPI:** `/docs` · **schema:** `/openapi.json` (OpenAPI 3.1)
- **Size:** 85 operations across 74 paths. The in-app reference at `/api` is generated from the same schema

## Authentication

Two credential shapes:

```http
X-API-Key: sf_test_pm8kd3_v1a7Qx9mNc2PfLz4Rt6WbYs8KdJh3Gn5
```

```http
Authorization: Bearer <access token from /v1/auth/login>
```

- **A third form, for one endpoint only:** the SSE stream accepts `?access_token=`
  - because the browser `EventSource` API cannot set headers
  - it **never** accepts an API key or a refresh token that way
- **Choosing a project:** send `X-SerpFlow-Project: prj_...`, or `project_id` in the body
  - without it, the API key's own project is used

### Key format

```
sf_<env>_<project_prefix>_<secret>
sf_live_pm8kd3_v1a7Qx9mNc2PfLz4Rt6WbYs8KdJh3Gn5
```

- **A `test` key always routes to the deterministic mock** and spends zero SerpApi credits, whatever `SERPFLOW_MODE` says
- That precedence is **absolute**. See [execution modes](../product/execution-modes.md)

## Core endpoints

### Plan without executing

```http
POST /v1/plan
{ "intent": "find coordinated review rings among Koramangala cafes", "budget": 20 }
```

- **Returns the full Plan:** selected steps, every candidate, cold and marginal costs, warm steps, freshness requirements, budget reductions, and whether marginal cost changed the selection
- **Spends zero credits:** planning calls a language model, not SerpApi
  - that is why the `analyst` role may call this, but not `/v1/search`

### Plan and execute

```http
POST /v1/search
{ "intent": "...", "budget": 20 }
```

- **Synchronous:** returns `{ run, plan, results, mode, provenance }`
- **With `"stream": true`:** returns `202` and `{ run_id, stream_url, mode }`, executes in-process, and the client tails `GET /v1/runs/{id}/stream`
- **Either way, interactive search never goes through Kafka.** That topic is for scheduled, bulk, retried and webhook-triggered runs
- **Optional `"mode"`** overrides the project's execution mode for this one request (needs `run:mode_override` for `live` or `record`)
- **`POST /v1/run`** is an alias, for symmetry with `/v1/plan`

### Runs

```http
GET  /v1/runs?limit=25&engine=google_maps&changed_selection=true
GET  /v1/runs/{id}                                 Run Inspector payload
GET  /v1/runs/{id}/plan
GET  /v1/runs/{id}/stream                          SSE
GET  /v1/runs/{id}/steps/{step_id}/payload         needs payload:read
POST /v1/runs/{id}/replay
POST /v1/runs/{id}/report-false-hit
```

- **`changed_selection=true`** filters to the runs where cache-aware replanning changed the plan
- **Raw payloads sit behind their own permission**, separate from run visibility
  - a `google_maps_contributor_reviews` payload is one named person's review history, not anonymous infrastructure data

### Catalog

```http
GET /v1/catalog?tag=place_reviews&search=maps
GET /v1/catalog/versions
GET /v1/catalog/engines/{engine}
GET /v1/catalog/engines/{engine}/paths?params=q,location
GET /v1/catalog/tags
GET /v1/catalog/graph
```

- **`/graph` returns `dependency_edges` and `substitute_edges` as separate arrays**: one is how engines chain, the other how they compete
- **`/paths` answers** "what valid chains reach this engine from an ordinary query?", the question the planner asks internally

### Governance

```http
GET    /v1/budgets                       budgets plus upstream quota, side by side
POST   /v1/budgets
PATCH  /v1/budgets/{id}                  DELETE /v1/budgets/{id}
GET    /v1/cache                         layers, hit rate, guard rejections
GET    /v1/cache/entries
GET    /v1/cache/guard-rejections
POST   /v1/cache/invalidate
GET    /v1/analytics/dashboard
GET    /v1/analytics/savings             the decomposition waterfall
GET    /v1/analytics/attribution         org -> project -> principal -> run -> step -> engine
GET    /v1/analytics/routing
GET    /v1/analytics/volatility
GET    /v1/analytics/engine-reach
GET    /v1/analytics/cross-project
GET    /v1/benchmarks                    GET /v1/benchmarks/tasks
POST   /v1/benchmarks/run                GET /v1/benchmarks/{run_id}/evals
GET    /v1/audit                         append-only, hash chained
GET    /v1/audit/verify
GET    /v1/audit/export
GET    /v1/alerts                        PATCH /v1/alerts/{id}
GET    /v1/notification-channels         POST, DELETE /v1/notification-channels/{id}
GET    /v1/notification-channels/labels
```

### Identity and access

```http
POST   /v1/auth/register  /login  /refresh  /logout
GET    /v1/auth/me  /sessions             DELETE /v1/auth/sessions/{id}
POST   /v1/auth/forgot-password  /reset-password  /verify-email

GET    /v1/organizations/current      PATCH
GET    /v1/projects                   POST      GET/PATCH /v1/projects/{id}
GET    /v1/members                    POST      PATCH/DELETE /v1/members/{id}
GET    /v1/roles                      POST      PATCH/DELETE /v1/roles/{id}
GET    /v1/roles/permissions          every permission a custom role can hold
GET    /v1/keys                       POST /v1/projects/{id}/keys
POST   /v1/keys/{id}/rotate           DELETE /v1/keys/{id}
GET    /v1/credentials                POST
GET    /v1/credentials/providers      serpapi, groq
POST   /v1/credentials/{id}/validate  /rotate      DELETE /v1/credentials/{id}
POST   /v1/credentials/revalidate     POST /v1/credentials/reconcile-quota
```

### Infrastructure

```http
GET /healthz    liveness, touches no dependency
GET /readyz     readiness: postgres, redis, kafka, object storage, catalog
GET /metrics    Prometheus
```

- **`/readyz` returns 503 only when PostgreSQL is unreachable**
- **Redis and Kafka degrade rather than fail:**
  - Redis is a hot cache, not the source of truth
  - Kafka carries only background work

## Provenance headers

On every response:

```
X-SerpFlow-Cache            which layer served the dominant step
X-SerpFlow-Matched-Query    the cached query a semantic hit matched
X-SerpFlow-Age              age of the served entry, in seconds
X-SerpFlow-TTL-Source       volatility_prior | learned | project_override |
                            freshness_capped
X-SerpFlow-Budget-Remaining credits left on the tightest applicable budget
X-SerpFlow-Run-Id
X-SerpFlow-Trace-Id
X-SerpFlow-Mode             LIVE | MOCK | REPLAY | RECORD
X-SerpFlow-Catalog-Version
X-Request-Id
```

- **`X-SerpFlow-Mode` is always present**
- Replayed or mocked data is **never** presented as live

## Errors

```json
{
  "error": {
    "code": "BUDGET_EXHAUSTED",
    "message": "The configured SerpFlow budget has been exhausted. Raise the configured budget to continue.",
    "request_id": "8a9e917259104679a693370622a23f64"
  }
}
```

- **Never a stack trace.** Codes are stable

| Code | Status | What to do |
| --- | ---: | --- |
| `UNAUTHENTICATED` | 401 | Supply a key or token |
| `INVALID_API_KEY` | 401 | The key is malformed, revoked or expired |
| `PERMISSION_DENIED` | 403 | Your role lacks the permission |
| `NOT_FOUND` | 404 | Also returned for cross-tenant ids, deliberately |
| `BUDGET_EXHAUSTED` | 402 | Raise your SerpFlow cap |
| `UPSTREAM_QUOTA_EXHAUSTED` | 402 | Add SerpApi account capacity |
| `BUDGET_INFEASIBLE` | 422 | No plan fits even after reduction |
| `NO_UPSTREAM_CREDENTIAL` | 412 | Attach a credential, or use a test key |
| `CREDENTIAL_REVOKED` | 409 | Revoked mid-run; the run failed rather than returning partial results |
| `NO_VIABLE_PLAN` | 422 | No valid path from the parameters this intent supplies |
| `ENGINE_NOT_ALLOWED` | 403 | Excluded by project policy |
| `REPLAY_CASSETTE_MISS` | 503 | Record the cassette, or switch to a test key |
| `SESSION_CAP_EXCEEDED` | 429 | The service principal's session cap is reached |
| `RATE_LIMITED` | 429 | Back off |
| `VALIDATION_ERROR` | 422 | `details.fields` names each one |

- **`BUDGET_EXHAUSTED` and `UPSTREAM_QUOTA_EXHAUSTED` are never conflated:** different causes, different fixes

## Pagination

```http
GET /v1/runs?limit=25&offset=50
```

```json
{ "items": [], "total": 412, "limit": 25, "offset": 50 }
```

## Rate limiting

- **Per principal and path:** 240 requests a minute by default (`RATE_LIMIT_PER_MINUTE`)
- **Backed by Redis**, and **fails open** if Redis is unavailable: a cache outage should not take the API down

## Checking every operation

```bash
make api-check                 # against http://localhost:8000
make api-check ARGS=--verbose  # print every call
```

- [`scripts/check_api.py`](../../scripts/check_api.py) reads the OpenAPI schema and calls **every** operation, filling path parameters from real records
- Destructive, long-running or upstream-billing calls are skipped **with the reason printed**, so the summary says what was not covered

## Next

- [Streaming](streaming.md): the SSE contract
- [Examples](examples.md): worked requests, SDKs, the SerpApi drop-in

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The public web surface](../architecture/web.md) | [Docs index](../README.md) | [Streaming](../api/streaming.md) |
