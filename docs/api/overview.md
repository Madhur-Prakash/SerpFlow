# API overview

<p>
  <a href="../README.md#api"><img alt="docs: API" src="https://img.shields.io/badge/docs-API-009688?logo=readthedocs&logoColor=white"></a>
  <img alt="operations: 85" src="https://img.shields.io/badge/operations-85-009688">
  <img alt="paths: 74" src="https://img.shields.io/badge/paths-74-009688">
  <img alt="FastAPI: 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="OpenAPI: 3.1" src="https://img.shields.io/badge/OpenAPI-3.1-6BA539?logo=openapiinitiative&logoColor=white">
  <img alt="JWT: HS256" src="https://img.shields.io/badge/JWT-HS256-000000?logo=jsonwebtokens&logoColor=white">
  <a href="../../backend/app/api/v1/__init__.py"><img alt="source: v1/__init__.py" src="https://img.shields.io/badge/source-v1%2F____init____.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 14 min" src="https://img.shields.io/badge/read-14%20min-555555">
</p>

[Docs](../README.md) › [API](../README.md#api) › **API overview** · page 20 of 57

- **Base URL:** `http://localhost:8000`; every product route sits under `/v1` ([`app/api/v1/__init__.py`](../../backend/app/api/v1/__init__.py))
- **Interactive OpenAPI:** `/docs` (Swagger UI) and `/redoc` · **schema:** `/openapi.json` (OpenAPI 3.1)
- **Size:** 85 operations across 74 paths, every one listed below
- **In-app reference:** the console's `/api` page ([`ApiReferencePage.tsx`](../../frontend/src/pages/ApiReferencePage.tsx)) is generated from the same schema by [`scripts/generate_api_reference.py`](../../scripts/generate_api_reference.py) (`make api-reference`). See [the API reference](../architecture/web.md#the-api-reference)
- **Client libraries:** a Python SDK, a TypeScript SDK, a CLI and an MCP server wrap these routes. See [SDKs and tools](../sdks/overview.md)

## Authentication

Two credential shapes:

```http
X-API-Key: sf_test_pm8kd3_v1a7Qx9mNc2PfLz4Rt6WbYs8KdJh3Gn5
```

```http
Authorization: Bearer <access token from /v1/auth/login>
```

- **An API key may also travel as `Authorization: Bearer sf_...`.** `X-API-Key` wins when both are sent ([`app/api/deps.py`](../../backend/app/api/deps.py))
- **Access tokens are HS256 JWTs that live 15 minutes.** The refresh token lives 14 days and works once: `POST /v1/auth/refresh` revokes it as it issues the next, and a reused one is `INVALID_CREDENTIALS` ([`app/core/config.py`](../../backend/app/core/config.py), [`app/services/auth/service.py`](../../backend/app/services/auth/service.py))
- **A third form, for one endpoint only:** the [SSE stream](streaming.md#authentication) accepts `?access_token=`
  - because the browser `EventSource` API cannot set headers
  - it **never** accepts an API key or a refresh token that way
- **Choosing a project:**
  - `/v1/plan`, `/v1/search` and `/v1/run` take `project_id` in the body; list routes such as `/v1/runs` take `?project_id=` as a filter
  - otherwise an API key acts in **its own project**
  - a user session takes its project from `X-SerpFlow-Project: prj_...`, which also applies any per-project role override for that user
  - with no project at all, the organization's oldest project is used

### Key format

```
sf_<env>_<project_prefix>_<secret>
sf_live_pm8kd3_v1a7Qx9mNc2PfLz4Rt6WbYs8KdJh3Gn5
```

- **`env` is `live` or `test`**, the prefix is six lowercase letters or digits, the secret 32 letters or digits ([`app/core/security.py`](../../backend/app/core/security.py))
- **Stored as HMAC-SHA256 under a server-side pepper**, shown in plaintext exactly once. See [API keys](../security/api-keys.md#format) and [ADR 0004](../adr/0004-hmac-for-api-keys.md)
- **A `test` key always routes to the deterministic mock** and spends zero SerpApi credits, whatever [`SERPFLOW_MODE`](../security/secrets.md#inventory) says
- That precedence is **absolute**. See [execution modes](../product/execution-modes.md#who-chooses-and-precedence) and [ADR 0010](../adr/0010-test-key-mode-precedence.md)

### Who can call what

- **Public, no credential:** `register`, `login`, `refresh`, `verify-email`, `forgot-password` and `reset-password` under `/v1/auth`, and the four [infrastructure](#infrastructure) routes
- **Signed in, no permission check:** `logout`, `me` and the two `sessions` routes
- **Everything else asserts one permission** through `require(Permission.X)`, deny by default ([`app/core/permissions.py`](../../backend/app/core/permissions.py), [checks are centralised](../security/api-keys.md#checks-are-centralised)). The permission is printed next to each operation below
- **A refusal is `PERMISSION_DENIED`**, with `details.required_permission` and `details.role`

The built-in [roles](../security/api-keys.md#roles), and the permissions each adds to the one before it:

| Role | Adds |
| --- | --- |
| `analyst` | `org:read` `project:read` `key:read` `plan:create` `run:read` `budget:read` `cache:read` `catalog:read` `analytics:read` `benchmark:read` `alert:read` |
| `developer` | `run:execute` `run:replay` `run:mode_override` `payload:read` `key:project_write` `cache:invalidate` `credential:read` `benchmark:run` |
| `admin` | `org:update` `project:write` `member:read` `member:write` `role:read` `key:write` `credential:write` `budget:write` `policy:write` `audit:read` `audit:export` `alert:write` |
| `owner` | `credential:rotate` `role:write` `org:billing` `org:delete` |
| `service` | its own set, not cumulative: `plan:create` `run:execute` `run:read` `payload:read` `catalog:read` `budget:read` `cache:read` |

- **A [custom role](../security/api-keys.md#custom-roles)** holds any subset
- **Assignable, but no route checks them at HEAD:** `policy:write`, `org:billing`, `org:delete`. Engine policy and cache settings change through `PATCH /v1/projects/{id}`, under `project:write`

## Core endpoints

### Plan without executing

```http
POST /v1/plan                                      plan:create
{ "intent": "find coordinated review rings among Koramangala cafes", "budget": 20 }
```

- **Returns the full Plan:** selected steps, every candidate, cold and marginal costs, warm steps, freshness requirements, budget reductions, and whether marginal cost changed the selection
  - field by field: [what the Plan stores](../architecture/planner.md#what-the-plan-stores). Every candidate is persisted, not just the winner ([ADR 0014](../adr/0014-persist-every-candidate.md))
- **Spends zero credits:** planning calls a language model, not SerpApi
  - that is why the `analyst` role may call this, but not `/v1/search`
- **Body:** `intent` (3 to 2,000 characters), optional `budget` (1 to 100,000), `project_id` and `mode` ([`app/schemas/planning.py`](../../backend/app/schemas/planning.py))
- **[Rate limited](#rate-limiting)**

### Plan and execute

```http
POST /v1/search                                    run:execute
{ "intent": "...", "budget": 20 }
```

- **Synchronous:** returns `{ run, plan, results, mode, provenance }`
  - `results.summary` is `{ result_key, count, items, notice? }`: up to five items from the terminal step's payload ([`app/services/executor/extract.py`](../../backend/app/services/executor/extract.py))
  - **`notice`** carries SerpApi's own message, at most 300 characters, when a billed search found nothing: the run **succeeded**, the credit is recorded and the empty answer is cached ([`app/services/executor/service.py`](../../backend/app/services/executor/service.py)). Example: [a search that found nothing](examples.md#a-search-that-found-nothing)
  - `results` also carries `payload_ref`, `terminal_engine`, `steps` (layer, credits, calls and latency per step) and `catalog_version`
- **With `"stream": true`:** returns `202` and `{ run_id, stream_url, mode, status: "running" }`, executes in-process, and the client tails `GET /v1/runs/{id}/stream` ([streaming](streaming.md#starting-a-run-you-can-stream))
- **Either way, interactive search never goes through Kafka.** That topic is for scheduled, bulk, retried and webhook-triggered runs ([ADR 0007](../adr/0007-interactive-search-bypasses-kafka.md), [Kafka](../operations/kafka.md#what-goes-through-it-and-what-does-not))
- **Optional `"mode"`** overrides the project's execution mode for this one request (needs `run:mode_override` for `live` or `record`; `replay` needs nothing; `mock` is not selectable and fails validation). See [execution modes](../product/execution-modes.md#permission)
- **[Rate limited](#rate-limiting)**, the same as `/v1/plan`
- **`POST /v1/run`** is an alias, for symmetry with `/v1/plan`

### Runs

```http
GET  /v1/runs?limit=25&engine=google_maps&changed_selection=true    run:read
GET  /v1/runs/{id}                                 run:read       Run Inspector payload
GET  /v1/runs/{id}/plan                            run:read
GET  /v1/runs/{id}/stream                          run:read       SSE
GET  /v1/runs/{id}/steps/{step_id}/payload         payload:read
POST /v1/runs/{id}/replay                          run:replay
POST /v1/runs/{id}/report-false-hit                run:read
```

- **`GET /v1/runs` filters** on `status`, `engine`, `project_id` and `changed_selection`, newest first ([`app/api/v1/runs.py`](../../backend/app/api/v1/runs.py))
- **`changed_selection=true`** filters to the runs where cache-aware replanning changed the plan. See [what `changed_selection` means](../architecture/marginal-replanning.md#what-changed_selection-means)
- **Raw payloads sit behind their own permission**, separate from run visibility
  - a `google_maps_contributor_reviews` payload is one named person's review history, not anonymous infrastructure data
  - the Run Inspector payload includes each step's `payload_ref` only for a caller with `payload:read` ([personal data in cached payloads](../security/threat-model.md#personal-data-in-cached-payloads))
- **`replay`** re-plans the original intent against the cache as it is now, records `replay_of_run_id`, and returns the same shape as `/v1/search`. The selected plan can legitimately differ from the original's: [the reference demo](../product/demo.md#the-three-phases) shows why
- **`report-false-hit`** takes `{ step_id?, note, invalidate_entry }` (`invalidate_entry` defaults to `true`), needs only `run:read`, and increments [`serpflow_semantic_false_hit_reports_total`](../operations/observability.md#metrics). See [rejections are evidence](../architecture/caching.md#rejections-are-evidence)

### Catalog

```http
GET /v1/catalog?tag=place_reviews&search=maps
GET /v1/catalog/versions
GET /v1/catalog/engines/{engine}
GET /v1/catalog/engines/{engine}/paths?params=q,location
GET /v1/catalog/tags
GET /v1/catalog/graph
```

- **Every catalog route needs `catalog:read`**, which every built-in role holds. `?version=` picks a catalog version on `/catalog`, `/engines/{engine}`, `/paths` and `/graph` ([`app/api/v1/catalog.py`](../../backend/app/api/v1/catalog.py))
- **`/graph` returns `dependency_edges` and `substitute_edges` as separate arrays**: one is how engines chain, the other how they compete ([ADR 0002](../adr/0002-typed-catalog-edges.md))
- **`/paths` answers** "what valid chains reach this engine from an ordinary query?", the question the planner asks internally
  - `params` defaults to `q`, and the query-like parameters (`q`, `query`, `text`, `term`, ...) are always added
- The data behind these routes, and the console page that draws them: [the engine catalog](../architecture/catalog.md#catalog-explorer)

### Governance

```http
GET    /v1/budgets                       budget:read        ledger and upstream quota, side by side
POST   /v1/budgets                       budget:write
PATCH  /v1/budgets/{id}                  budget:write
DELETE /v1/budgets/{id}                  budget:write

GET    /v1/cache                         cache:read         layers, hit rate, guard rejections
GET    /v1/cache/entries                 cache:read
GET    /v1/cache/guard-rejections        cache:read
POST   /v1/cache/invalidate              cache:invalidate

GET    /v1/analytics/dashboard           analytics:read
GET    /v1/analytics/savings             analytics:read     the decomposition waterfall
GET    /v1/analytics/attribution         analytics:read     org -> project -> principal -> run -> step -> engine
GET    /v1/analytics/routing             analytics:read
GET    /v1/analytics/volatility          analytics:read
GET    /v1/analytics/engine-reach        analytics:read
GET    /v1/analytics/cross-project       analytics:read

GET    /v1/benchmarks                    benchmark:read
GET    /v1/benchmarks/tasks              benchmark:read
GET    /v1/benchmarks/{run_id}/evals     benchmark:read
POST   /v1/benchmarks/run                benchmark:run      makes real model calls

GET    /v1/audit                         audit:read         append-only, hash chained
GET    /v1/audit/verify                  audit:read
GET    /v1/audit/export                  audit:export       up to 50,000 entries (?limit=, default 10,000)

GET    /v1/alerts                        alert:read
PATCH  /v1/alerts/{id}                   alert:write
GET    /v1/notification-channels         alert:read
POST   /v1/notification-channels         alert:write
DELETE /v1/notification-channels/{id}    alert:write
GET    /v1/notification-channels/labels  alert:read
```

- **Budgets:** the SerpFlow ledger and the upstream SerpApi quota are reported side by side and never merged. How a cap shapes a plan: [budget-aware reduction](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking); how it stops a run: [budget enforcement](../architecture/executor.md#budget-enforcement)
- **Cache:** the dashboard and entries are the [cache layers](../architecture/caching.md#two-entry-points) as stored; guard rejections are [the entity and numeral guard](../architecture/caching.md#the-entity-and-numeral-guard) at work
  - `POST /v1/cache/invalidate` takes `{ engine?, entry_id? }`: one entry, or every live entry in the project's partition, optionally for one engine. See [invalidation](../architecture/caching.md#invalidation)
- **Analytics:** the savings waterfall sums [`budget_ledger`](../database/schema.md#budget_ledger) savings by source (routing, exact, semantic, archive) on top of spend, the same split as the [savings counters](../architecture/marginal-replanning.md#instrumentation); cross-project flows come from [organization-level sharing](../architecture/caching.md#organization-level-sharing)
- **Benchmarks:** the 120-task routing suite. See [routing benchmark](../product/benchmark.md#running-it)
- **Audit:** a trigger makes [`audit_log`](../database/schema.md#audit_log) append-only and a hash chain makes tampering detectable; `/verify` walks the chain and reports where it breaks. See [the audit log](../database/rls.md#the-audit-log) and [ADR 0012](../adr/0012-append-only-audit-log.md)
- **Alerts and channels:** budget, exhaustion and quota alerts, delivered to `email`, `webhook` or `slack` channels. See [alerting](../operations/observability.md#alerting) and [email](../operations/email.md#what-gets-sent)

### Identity and access

```http
POST   /v1/auth/register                       public
POST   /v1/auth/login                          public
POST   /v1/auth/refresh                        public
POST   /v1/auth/logout                         signed in
GET    /v1/auth/me                             signed in
GET    /v1/auth/sessions                       signed in
DELETE /v1/auth/sessions/{id}                  signed in
POST   /v1/auth/verify-email                   public
POST   /v1/auth/forgot-password                public
POST   /v1/auth/reset-password                 public

GET    /v1/organizations/current               org:read
PATCH  /v1/organizations/current               org:update
GET    /v1/projects                            project:read
POST   /v1/projects                            project:write
GET    /v1/projects/{id}                       project:read
PATCH  /v1/projects/{id}                       project:write
GET    /v1/members                             member:read
POST   /v1/members                             member:write
PATCH  /v1/members/{id}                        member:write
DELETE /v1/members/{id}                        member:write
GET    /v1/roles                               role:read
POST   /v1/roles                               role:write
PATCH  /v1/roles/{id}                          role:write
DELETE /v1/roles/{id}                          role:write
GET    /v1/roles/permissions                   role:read       every permission a custom role can hold
GET    /v1/keys                                key:read
POST   /v1/projects/{id}/keys                  key:write or key:project_write
POST   /v1/keys/{id}/rotate                    key:write
DELETE /v1/keys/{id}                           key:write
GET    /v1/credentials                         credential:read
POST   /v1/credentials                         credential:write
GET    /v1/credentials/providers               credential:read     serpapi, groq
POST   /v1/credentials/{id}/validate           credential:write
POST   /v1/credentials/{id}/rotate             credential:rotate
DELETE /v1/credentials/{id}                    credential:rotate
POST   /v1/credentials/revalidate              credential:write
POST   /v1/credentials/reconcile-quota         credential:read
```

- **Auth:** `register` sends a verification link and `forgot-password` a reset link; `forgot-password` answers the same whether or not the address exists. See [what gets sent](../operations/email.md#what-gets-sent)
- **Projects** carry the execution mode, engine policy, semantic threshold and TTL overrides. See [setting the mode](../product/execution-modes.md#setting-it) and [engine policy](../architecture/executor.md#engine-policy)
- **Keys:** a new key's plaintext is returned once, and a key's role can never exceed its creator's. See [rotation](../security/api-keys.md#rotation) and [test keys](../security/api-keys.md#test-keys)
- **Roles:** owner-defined permission sets (migration [`0003_custom_roles`](../database/migrations.md#0003_custom_roles)). See [custom roles](../security/api-keys.md#custom-roles)
- **Credentials:** envelope-encrypted upstream keys, never returned in any response ([ADR 0006](../adr/0006-no-credential-field-in-schemas.md)). Validation, rotation and revocation: [upstream credentials](../security/credentials.md#validation-and-revocation); the `groq` provider is [bring your own key](../security/byok.md#what-you-bring) for the language model
  - `revalidate` and `reconcile-quota` only queue work on [Kafka](../operations/kafka.md#topics), and answer `ok: false` when the broker is unavailable

### Infrastructure

```http
GET /           service index: version, mode, links to the routes below
GET /healthz    liveness, touches no dependency
GET /readyz     readiness: postgres, redis, kafka, object storage, catalog
GET /metrics    Prometheus
```

- **All four are public** ([`app/main.py`](../../backend/app/main.py))
- **`/readyz` returns 503 only when PostgreSQL is unreachable**; it also reports the language-model provider in use
- **Redis and Kafka degrade rather than fail:**
  - Redis is a hot cache, not the source of truth
  - Kafka carries only background work
- What to point probes and scrapers at: [health](../operations/observability.md#health) and [metrics](../operations/observability.md#metrics)

## Provenance headers

```
X-Request-Id                every response; echoes an incoming X-Request-Id
X-SerpFlow-Mode             every response: LIVE | MOCK | REPLAY | RECORD
X-SerpFlow-Catalog-Version  every response
X-SerpFlow-Trace-Id         every response, when tracing is on

X-SerpFlow-Cache            the layer that served the most calls: exact | semantic |
                            archive | live | mock | miss
X-SerpFlow-Matched-Query    the cached query a semantic hit matched (first step)
X-SerpFlow-Age              age of the served entry, in seconds (first step)
X-SerpFlow-TTL-Source       volatility_prior | learned | project_override |
                            freshness_capped | archive (first step)
X-SerpFlow-Budget-Remaining credits left on the tightest applicable budget
X-SerpFlow-Run-Id
```

- **The first four come from middleware** on every response ([`app/api/middleware.py`](../../backend/app/api/middleware.py)); the rest are set by `/v1/search`, `/v1/run` and `/v1/runs/{id}/replay`. `/v1/plan` adds only `X-SerpFlow-Budget-Remaining`, and a streamed search's `202` only `X-SerpFlow-Run-Id`
- **`X-SerpFlow-Mode` is always present**
  - on the plan and search routes it is the resolved mode for that request (request, then project, then `SERPFLOW_MODE`)
  - elsewhere it is the server default, or `MOCK` for a test key
- So a replayed or mocked run is **never** labelled live
- **CORS exposes all ten to browsers**, alongside the security headers every response carries (`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`)
- Following one request through logs and traces: [correlating one request](../operations/observability.md#correlating-one-request)

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

- **Never a stack trace.** An unhandled exception is `INTERNAL_ERROR` with the `request_id` to find it in the logs. Codes are stable ([`app/core/exceptions.py`](../../backend/app/core/exceptions.py), [error model](../architecture/backend.md#error-model))
- **`details`** is added when there is more to say: the failing fields, the required permission, the budget verdict

| Code | Status | What to do |
| --- | ---: | --- |
| `UNAUTHENTICATED` | 401 | Supply a key or token |
| `INVALID_API_KEY` | 401 | The key is malformed, revoked or expired ([fix](../operations/troubleshooting.md#invalid_api_key-on-a-key-that-looks-right)) |
| `INVALID_CREDENTIALS` | 401 | Wrong email or password, or a refresh token already used |
| `PERMISSION_DENIED` | 403 | Your role lacks the permission named in `details.required_permission` |
| `NOT_FOUND` | 404 | Also returned for cross-tenant ids, deliberately ([application guards](../database/rls.md#the-application-guards)) |
| `CONFLICT` | 409 | The resource already exists, or is in a state that forbids the change |
| `REQUEST_TOO_LARGE` | 413 | The body exceeds 1 MiB |
| `BUDGET_EXHAUSTED` | 402 | Raise your SerpFlow cap |
| `UPSTREAM_QUOTA_EXHAUSTED` | 402 | Add SerpApi account capacity |
| `BUDGET_INFEASIBLE` | 422 | Defined, but **not raised at HEAD**: when no candidate fits even after reduction, the planner still ranks and selects one, each candidate recording why it cannot fit. Only a configured budget then stops execution, with `BUDGET_EXHAUSTED` ([`app/services/planner/cost.py`](../../backend/app/services/planner/cost.py)) |
| `NO_UPSTREAM_CREDENTIAL` | 412 | Attach a credential, or use a test key ([fix](../operations/troubleshooting.md#no_upstream_credential)) |
| `CREDENTIAL_VALIDATION_FAILED` | 422 | The provider rejected the credential, or could not be reached, when it was added or validated |
| `CREDENTIAL_REVOKED` | 409 | Revoked mid-run; the run failed rather than returning partial results ([revoked mid-run](../security/credentials.md#revoked-mid-run)) |
| `CREDENTIAL_REJECTED` | 502 | SerpApi answered 401 to a live call: the stored key is no longer valid upstream |
| `NO_VIABLE_PLAN` | 422 | No valid path from the parameters this intent supplies ([fix](../operations/troubleshooting.md#no_viable_plan)) |
| `ENGINE_NOT_ALLOWED` | 403 | Excluded by project policy ([engine policy](../architecture/executor.md#engine-policy)) |
| `UPSTREAM_ERROR` | 502 | A live step failed upstream; the run failed |
| `BINDING_FAILED` | 502 | A chained step found no value to bind from the step it depends on |
| `REPLAY_CASSETTE_MISS` | 503 | Record the cassette, or switch to a test key ([fix](../operations/troubleshooting.md#replay_cassette_miss)) |
| `SESSION_CAP_EXCEEDED` | 429 | The service principal's session cap is reached ([service sessions](../security/api-keys.md#service-principal-sessions)) |
| `RATE_LIMITED` | 429 | Back off; `details` gives the limit and window |
| `VALIDATION_ERROR` | 422 | `details.fields` names each one, as `location` and `message` (at most 20) |
| `CATALOG_ERROR` | 500 | The committed catalog failed to load |
| `INTERNAL_ERROR` | 500 | Quote the `request_id` |

- **`BUDGET_EXHAUSTED` and `UPSTREAM_QUOTA_EXHAUSTED` are never conflated:** different causes, different fixes ([which one you have](../operations/troubleshooting.md#budget_exhausted-against-upstream_quota_exhausted))
- **`TENANT_ISOLATION_VIOLATION` (403) is defined but not raised:** a cross-tenant id is `NOT_FOUND`, so an id's existence in another organization is never confirmed ([ADR 0011](../adr/0011-rls-plus-application-guards.md))

## Pagination

```http
GET /v1/runs?limit=25&offset=50
```

```json
{ "items": [], "total": 412, "limit": 25, "offset": 50 }
```

- **`limit` defaults to 50 and is capped at 200** ([`app/api/deps.py`](../../backend/app/api/deps.py))
- **This envelope is on** `/v1/runs`, `/v1/keys`, `/v1/cache/entries`, `/v1/cache/guard-rejections`, `/v1/benchmarks/tasks`, `/v1/audit` and `/v1/alerts`
- **Other lists return a plain array**: projects, members, sessions, credentials, providers, benchmark runs, evals and notification channels

## Rate limiting

- **On `POST /v1/plan`, `/v1/search` and `/v1/run` only**, per principal and path: 240 requests by default (`RATE_LIMIT_PER_MINUTE`, in [`.env.example`](../../.env.example))
- **The window is a Redis counter whose 60-second expiry is refreshed on every request**, so the count resets only after a minute with no calls on that path ([`app/services/cache/redis_client.py`](../../backend/app/services/cache/redis_client.py))
- **Backed by Redis**, and **fails open** if Redis is unavailable: a cache outage should not take the API down
- **Over the limit:** `429 RATE_LIMITED`. Neither SDK retries for you

## Checking every operation

```bash
make api-check                 # against http://localhost:8000
make api-check ARGS=--verbose  # print every call
```

- [`scripts/check_api.py`](../../scripts/check_api.py) reads the OpenAPI schema and calls **every** operation, filling path parameters from real records
- Destructive, long-running or upstream-billing calls are skipped **with the reason printed**, so the summary says what was not covered

## Related

- [Streaming](streaming.md): the SSE contract behind `GET /v1/runs/{id}/stream`
- [Worked examples](examples.md): these routes with real request and response bodies, and the SerpApi drop-in
- [SDKs and tools](../sdks/overview.md): the Python, TypeScript, CLI and MCP clients over this API
- [API keys](../security/api-keys.md#roles): the roles, custom roles and service sessions behind every permission above
- [Backend](../architecture/backend.md#error-model): where the error envelope and request lifecycle are implemented
- [ADR 0010](../adr/0010-test-key-mode-precedence.md): why a test key overrides every execution mode
- [Troubleshooting](../operations/troubleshooting.md#authentication): fixes for the authentication and execution error codes
- [Glossary](../product/glossary.md): every term used on this page, with its canonical page

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The public web surface](../architecture/web.md) | [Docs index](../README.md) | [Streaming](../api/streaming.md) |
