# Backend

<p>
  <a href="../architecture/README.md"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI: 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="SQLAlchemy: 2" src="https://img.shields.io/badge/SQLAlchemy-2-D71F00?logo=sqlalchemy&logoColor=white">
  <img alt="Pydantic: v2" src="https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white">
  <a href="../../backend/app/main.py"><img alt="source: app/main.py" src="https://img.shields.io/badge/source-app%2Fmain.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../architecture/README.md) › **Backend** · page 20 of 50

**Python 3.13, FastAPI, SQLAlchemy 2 with async psycopg, Pydantic v2.** How the pieces fit at the system level is in the [architecture overview](overview.md#layers); this page is the package itself. The console that calls it is the [frontend](frontend.md).

## Module map

```
backend/
├── app/
│   ├── main.py              FastAPI app, lifespan, /healthz /readyz /metrics
│   ├── server.py            uvicorn entry point with an explicit loop factory
│   ├── api/
│   │   ├── deps.py          session, principal resolution, tenant guard,
│   │   │                    require(permission), rate limit
│   │   ├── middleware.py    request ids, provenance and security headers,
│   │   │                    body size limit, error envelope
│   │   └── v1/              auth, organizations, credentials, search, runs,
│   │                        catalog, governance, roles, _serializers
│   ├── core/
│   │   ├── config.py        pydantic-settings, one source of truth for env
│   │   ├── security.py      Argon2id, HMAC keys, JWTs, envelope encryption
│   │   ├── permissions.py   five built-in roles plus custom roles, deny by default
│   │   ├── logging.py       Logifyx plus the credential redaction filter
│   │   ├── telemetry.py     OpenTelemetry spans
│   │   ├── metrics.py       22 Prometheus series
│   │   ├── text.py          locale, freshness, dates, entity extraction,
│   │   │                    per-engine query adapters
│   │   ├── routes.py        airport code resolution
│   │   └── exceptions.py    typed errors with stable machine codes
│   ├── db/
│   │   ├── base.py          declarative base, prefixed ULIDs
│   │   ├── session.py       async engine, session scope, SET LOCAL tenant guard
│   │   ├── bootstrap.py     migrate and seed on startup, advisory-locked
│   │   ├── seed.py          catalog, benchmarks and demo data
│   │   └── models/          identity, keys, planning, caching, catalog,
│   │                        governance, benchmark
│   ├── schemas/             request and response models: common, identity,
│   │                        planning, governance
│   ├── services/
│   │   ├── runs.py          plan_and_execute: the one place a plan becomes a run
│   │   ├── stream.py        the in-process SSE event bus
│   │   ├── planner/         retrieval, candidates, cost, budget reduction
│   │   ├── cache/           lookup and inspect, guard, keys, TTL, Redis client
│   │   ├── executor/        step execution, payload extraction
│   │   ├── catalog/         schema, loader, graph, vocabulary, data/v1
│   │   ├── budgets/  credentials/  auth/  roles/  audit/
│   │   └── analytics/  benchmark/  email/  notifications/
│   ├── integrations/        serpapi/, llm/, storage/
│   ├── workers/             kafka.py, runner.py, topics.py, producers/, consumers/
│   ├── templates/email/     HTML and text templates for transactional mail
│   ├── mcp/server.py        the MCP server (serpflow-mcp)
│   ├── cli/main.py          the CLI (serpflow)
│   └── sdk/__init__.py      the Python SDK
├── serpflow.py              top-level `from serpflow import SerpFlow`
├── alembic/versions/        0001 to 0004
├── scripts/                 seed.py, demo.py, catalog_build.py, mint_gmail_token.py
├── fixtures/benchmark/      the routing benchmark task set and results
└── tests/                   unit/, integration/, e2e/
```

**Where each part is documented:**

| Part | Canonical page |
| --- | --- |
| `main.py` lifespan, `/healthz` `/readyz` | [Bootstrap](../operations/bootstrap.md), [observability: health](../operations/observability.md#health) |
| `server.py` | [Async on Windows](#async-on-windows) |
| `api/v1/` | [API overview](../api/overview.md#core-endpoints) |
| `api/deps.py` principal resolution | [API keys: resolution](../security/api-keys.md#resolution), [RLS: application guards](../database/rls.md#the-application-guards) |
| `api/middleware.py` | [Provenance headers](../api/overview.md#provenance-headers), [errors](../api/overview.md#errors) |
| `core/config.py` | [Secrets](../security/secrets.md#inventory), [`.env.example`](../../.env.example) |
| `core/security.py` | [Credentials: envelope encryption](../security/credentials.md#envelope-encryption) |
| `core/permissions.py` | [API keys: roles](../security/api-keys.md#roles) |
| `core/logging.py` `telemetry.py` `metrics.py` | [Observability](../operations/observability.md) |
| `core/text.py` `routes.py` | [Planner: stage C](planner.md#stage-c-synthesize), [caching: the guard](caching.md#the-entity-and-numeral-guard) |
| `db/session.py` | [Row-level security: how it works](../database/rls.md#how-it-works) |
| `db/bootstrap.py` `seed.py` | [Bootstrap](../operations/bootstrap.md) |
| `db/models/` | [Database schema](../database/schema.md) |
| `alembic/` | [Migrations](../database/migrations.md) |
| `services/planner/` | [Planner](planner.md), [marginal-cost replanning](marginal-replanning.md) |
| `services/cache/` | [Caching](caching.md), [Redis](../operations/redis.md) |
| `services/executor/` `runs.py` | [Executor](executor.md) |
| `services/stream.py` | [Streaming](../api/streaming.md) |
| `services/catalog/` | [Catalog](catalog.md) |
| `services/budgets/` | [Executor: budget enforcement](executor.md#budget-enforcement) |
| `services/credentials/` | [Credentials](../security/credentials.md), [BYOK](../security/byok.md) |
| `services/auth/` `roles/` | [API keys](../security/api-keys.md), [custom roles](../security/api-keys.md#custom-roles) |
| `services/audit/` | [RLS: the audit log](../database/rls.md#the-audit-log) |
| `services/benchmark/`, `fixtures/benchmark/` | [Routing benchmark](../product/benchmark.md) |
| `services/email/` `notifications/`, `templates/email/` | [Email](../operations/email.md) |
| `integrations/serpapi/` | [Executor: where LIVE goes](executor.md#where-live-goes), [execution modes](../product/execution-modes.md) |
| `integrations/llm/` | [Planner: stage B](planner.md#stage-b-select) |
| `integrations/storage/` | [Caching: object storage](caching.md#object-storage) |
| `workers/` | [Kafka](../operations/kafka.md) |
| `mcp/` `cli/` `sdk/` `serpflow.py` | [MCP](../sdks/mcp.md), [CLI](../sdks/cli.md), [Python SDK](../sdks/python.md) |
| `backend/scripts/demo.py` | [The reference demo](../product/demo.md) |
| `backend/scripts/catalog_build.py` | [Catalog: how it is authored](catalog.md#how-the-catalog-is-authored) |
| `backend/scripts/mint_gmail_token.py` | [Email: setting up Gmail](../operations/email.md#setting-up-gmail) |

## Request lifecycle

Middleware is registered in [`main.py`](../../backend/app/main.py); the last one added is the outermost:

1. **`CORSMiddleware`** and **`GZipMiddleware`** wrap everything
2. **`BodySizeLimitMiddleware`** rejects a body over `MAX_REQUEST_BODY_BYTES` (1 MiB) with `REQUEST_TOO_LARGE` (413)
   - it runs before a request id exists, so that envelope carries none
3. **`RequestContextMiddleware`** assigns a request id (or keeps an inbound `X-Request-Id`), binds logging context and starts the timer
   - it turns any uncaught exception into the error envelope, and records `serpflow_api_requests_total` and `serpflow_api_request_seconds` ([HTTP metrics](../operations/observability.md#http-and-kafka))
4. **`get_session`** opens one transaction for the request: commit on success, **rollback on any exception** ([what that means for a failed run](executor.md#when-a-run-fails))
5. **`get_principal`** resolves an API key or a JWT, then sets `app.current_org` for this transaction (`set_config(..., true)`, the function form of `SET LOCAL`)
   - so [row-level security](../database/rls.md) applies to everything that follows on this transaction
6. **`require(Permission.X)`** asserts authorization ([checks are centralised](../security/api-keys.md#checks-are-centralised))
   - deny by default
   - no business-logic module performs its own check
7. **The route calls a service.** Services never touch `Request`
   - interactive search executes in-process; only background work goes to Kafka
8. **The response** picks up [provenance headers](../api/overview.md#provenance-headers) and security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`)

## Identifiers

- **Prefixed, lexicographically sortable ULIDs:** `run_01M3WQ...`, `plan_...`, `key_...`, `cred_...` ([`db/base.py`](../../backend/app/db/base.py))
- Sortable by creation time
- Readable in a log line
- Unambiguous about what they point at

## Error model

Every error carries a **stable machine code**, and never a stack trace:

```json
{
  "error": {
    "code": "BUDGET_EXHAUSTED",
    "message": "The project budget is exhausted: 500 of 500 credits used this monthly period. Raise the configured SerpFlow budget to continue. This is a SerpFlow cap, not the upstream SerpApi account quota.",
    "details": {
      "allowed": false,
      "binding_scope": "project",
      "binding_budget_id": "bgt_01M3WQ...",
      "remaining": 0,
      "limit": 500,
      "on_exhausted": "error",
      "checked": [
        { "scope": "project", "budget_id": "bgt_01M3WQ...", "limit": 500, "usage": 500,
          "remaining": 0, "period": "monthly", "on_exhausted": "error" }
      ]
    },
    "request_id": "8a9e917259104679a693370622a23f64"
  }
}
```

- Codes are defined **once**, in [`core/exceptions.py`](../../backend/app/core/exceptions.py), and listed with their statuses in [API errors](../api/overview.md#errors)
- **`details` appears when the error has context:** the binding budget scope and every budget checked, the failing step and engine, the expected cassette path
- **Only the TypeScript SDK maps codes to remedies:** `SerpFlowError.remedy` returns one for `BUDGET_EXHAUSTED`, `UPSTREAM_QUOTA_EXHAUSTED`, `NO_UPSTREAM_CREDENTIAL` and `REPLAY_CASSETTE_MISS`, and `null` otherwise ([`index.ts`](../../sdk/typescript/src/index.ts), [TypeScript SDK: errors](../sdks/typescript.md#errors))
  - the Python `SerpFlowError` carries `code`, `message`, `status` and `request_id`, with no remedy ([`app/sdk/__init__.py`](../../backend/app/sdk/__init__.py), [Python SDK: errors](../sdks/python.md#errors))
- Fixes for the common ones: [troubleshooting](../operations/troubleshooting.md)

## Async on Windows

- **The psycopg async driver cannot run on a proactor event loop**
- uvicorn picks its loop with a factory that returns one on Windows for single-process runs
- **`python -m app.server` drives uvicorn with an explicit selector loop factory**, so a laptop behaves like a container
- `--reload` and `--workers` above 1 take uvicorn's supervisor path, which spawns subprocesses, for which uvicorn picks a selector loop itself
- If you see `InterfaceError` from psycopg on Windows, you started uvicorn directly: [troubleshooting](../operations/troubleshooting.md#psycopg-fails-on-windows-proactoreventloop)

## Lazy relationship loading

- **Async SQLAlchemy raises `MissingGreenlet`** if a lazy relationship is touched outside the async context ([troubleshooting](../operations/troubleshooting.md#missinggreenlet-greenlet_spawn-has-not-been-called))
- Where a service creates rows that a serializer reads immediately (`Plan.candidates`, `Run.steps`):
  - the relationship is marked loaded with **`set_committed_value`**, not assigned
  - an ordinary assignment loads the old collection to diff against

## Degradation

| Dependency | If it is down |
| --- | --- |
| PostgreSQL | `/readyz` returns 503 with the reason. **Required** |
| Redis | Degraded. Cache lookups fall through to the durable index, the principal cache misses, rate limiting fails open ([Redis: degradation](../operations/redis.md#degradation)) |
| Kafka | Degraded. Background events are dropped with a `kafka.degraded` warning; the synchronous path is unaffected, which is why interactive search is not routed through it ([Kafka: degradation](../operations/kafka.md#degradation)) |
| Object storage | A cache index entry pointing at a missing object is treated as a miss, rather than failing the run |

- **`/readyz` reports `degraded`, with a 200**, when only Redis or Kafka is down

## Related

- [Architecture overview](overview.md): the layers and the request lifecycle at system level
- [Executor](executor.md): the service the search route ends in, and why a failed run rolls back
- [Bootstrap](../operations/bootstrap.md): what the lifespan runs before the first request
- [Database schema](../database/schema.md): the tables behind `db/models/`
- [API overview](../api/overview.md): the routes in `api/v1/` and the error codes
- [SDKs and tools](../sdks/overview.md): the CLI, SDK and MCP server packaged in this backend
- [Troubleshooting: database](../operations/troubleshooting.md#database): the async-driver failures this page explains

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The executor](../architecture/executor.md) | [Docs index](../README.md) · [Architecture index](../architecture/README.md) | [Frontend](../architecture/frontend.md) |
