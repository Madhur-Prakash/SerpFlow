# Backend

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI: 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="SQLAlchemy: 2" src="https://img.shields.io/badge/SQLAlchemy-2-D71F00?logo=sqlalchemy&logoColor=white">
  <img alt="Pydantic: v2" src="https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white">
  <a href="../../backend/app/core/exceptions.py"><img alt="source: core/exceptions.py" src="https://img.shields.io/badge/source-core%2Fexceptions.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **Backend** · page 16 of 50

**Python 3.13, FastAPI, SQLAlchemy 2 with async psycopg, Pydantic v2.**

## Module map

```
backend/
├── app/
│   ├── main.py              app factory, lifespan, /healthz /readyz /metrics
│   ├── server.py            uvicorn entry point with an explicit loop factory
│   ├── api/
│   │   ├── deps.py          principal resolution, tenant guard, require(permission)
│   │   ├── middleware.py    request ids, provenance headers, error envelope
│   │   └── v1/              auth, organizations, credentials, search, runs,
│   │                        catalog, governance, roles
│   ├── core/
│   │   ├── config.py        pydantic-settings, one source of truth for env
│   │   ├── security.py      Argon2id, HMAC keys, JWTs, envelope encryption
│   │   ├── permissions.py   five built-in roles plus custom roles, deny by default
│   │   ├── logging.py       Logifyx plus the credential redaction filter
│   │   ├── telemetry.py     OpenTelemetry spans
│   │   ├── metrics.py       22 Prometheus series
│   │   ├── text.py          locale, freshness, dates, entity extraction
│   │   ├── routes.py        airport code resolution
│   │   └── exceptions.py    typed errors with stable machine codes
│   ├── db/
│   │   ├── base.py          declarative base, prefixed ULIDs
│   │   ├── session.py       async engine, session scope, SET LOCAL tenant guard
│   │   ├── bootstrap.py     migrate and seed on startup, advisory-locked
│   │   ├── seed.py          catalog, benchmarks and demo data
│   │   └── models/          identity, keys, planning, caching, catalog,
│   │                        governance, benchmark
│   ├── schemas/             request and response models
│   ├── services/            see the architecture overview
│   ├── workers/             kafka.py, runner.py, topics.py, producers/, consumers/
│   ├── integrations/        serpapi/, llm/, storage/
│   └── mcp/ cli/ sdk/
└── alembic/versions/        0001 to 0004
```

## Request lifecycle

1. **`RequestContextMiddleware`** assigns a request id, binds logging context and starts the timer
2. **`BodySizeLimitMiddleware`** rejects oversized bodies
3. **`get_principal`** resolves an API key or a JWT, then issues `SET LOCAL app.current_org`
   - so row-level security applies to everything that follows on this transaction
4. **`require(Permission.X)`** asserts authorization
   - deny by default
   - no business-logic module performs its own check
5. **The route calls a service.** Services never touch `Request`
6. **The response** picks up provenance headers and security headers

## Identifiers

- **Prefixed, lexicographically sortable ULIDs:** `run_01M3WQ...`, `plan_...`, `key_...`, `cred_...`
- Sortable by creation time
- Readable in a log line
- Unambiguous about what they point at

## Error model

Every error carries a **stable machine code**, and never a stack trace:

```json
{
  "error": {
    "code": "BUDGET_EXHAUSTED",
    "message": "The configured SerpFlow budget has been exhausted. Raise the configured budget to continue.",
    "request_id": "8a9e917259104679a693370622a23f64"
  }
}
```

- Codes are defined **once**, in [`core/exceptions.py`](../../backend/app/core/exceptions.py)
- **Both SDKs map them to remedies**

## Async on Windows

- **The psycopg async driver cannot run on a proactor event loop**
- uvicorn picks its loop with a factory that returns one on Windows for single-process runs
- **`python -m app.server` drives uvicorn with an explicit selector loop factory**, so a laptop behaves like a container
- The reload path already spawns subprocesses, for which uvicorn picks a selector loop itself
- More: [ADR 0013](../adr/0013-explicit-event-loop-factory.md)

## Lazy relationship loading

- **Async SQLAlchemy raises `MissingGreenlet`** if a lazy relationship is touched outside the async context
- Where a service creates rows that a serializer reads immediately (`Plan.candidates`, `Run.steps`):
  - the relationship is marked loaded with **`set_committed_value`**, not assigned
  - an ordinary assignment loads the old collection to diff against

## Degradation

| Dependency | If it is down |
| --- | --- |
| PostgreSQL | `/readyz` returns 503 with the reason. **Required** |
| Redis | Degraded. Cache lookups fall through to the durable index, the principal cache misses, rate limiting fails open |
| Kafka | Degraded. Background events are dropped with a warning; the synchronous path is unaffected, which is why interactive search is not routed through it |
| Object storage | A cache index entry pointing at a missing object is treated as a miss, rather than failing the run |

## Related

- [Architecture overview](overview.md)
- [Bootstrap](../operations/bootstrap.md)
- [Database schema](../database/schema.md)
- [API overview](../api/overview.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The executor](../architecture/executor.md) | [Docs index](../README.md) | [Frontend](../architecture/frontend.md) |
