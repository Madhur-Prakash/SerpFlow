# Backend

Python 3.13, FastAPI, SQLAlchemy 2 with async psycopg, Pydantic v2.

## Module map

```
app/
├── main.py              app factory, lifespan, /healthz /readyz /metrics
├── server.py            uvicorn entry point with an explicit loop factory
├── api/
│   ├── deps.py          principal resolution, tenant guard, require(permission)
│   ├── middleware.py    request ids, provenance headers, error envelope
│   └── v1/              auth, organizations, credentials, search, runs,
│                        catalog, governance
├── core/
│   ├── config.py        pydantic-settings, one source of truth for env
│   ├── security.py      Argon2id, HMAC keys, JWTs, envelope encryption
│   ├── permissions.py   five roles, deny by default
│   ├── logging.py       Logifyx plus the credential redaction filter
│   ├── telemetry.py     OpenTelemetry spans
│   ├── metrics.py       20 Prometheus series
│   ├── text.py          locale, freshness, dates, entity extraction
│   ├── routes.py        airport code resolution
│   └── exceptions.py    typed errors with stable machine codes
├── db/
│   ├── base.py          declarative base, prefixed ULIDs
│   ├── session.py       async engine, session scope, SET LOCAL tenant guard
│   └── models/          identity, keys, planning, caching, catalog,
│                        governance, benchmark
├── schemas/             request and response models
├── services/            see the architecture overview
├── workers/             kafka.py, runner.py, topics.py, consumers/
├── integrations/        serpapi/, llm/, storage/
├── mcp/ cli/ sdk/
└── alembic/versions/
```

## Request lifecycle

1. `RequestContextMiddleware` assigns a request id, binds logging context and
   starts the timer.
2. `BodySizeLimitMiddleware` rejects oversized bodies.
3. `get_principal` resolves an API key or a JWT, then issues
   `SET LOCAL app.current_org` so row-level security applies to everything that
   follows on this transaction.
4. `require(Permission.X)` asserts authorization. Deny by default; no
   business-logic module performs its own check.
5. The route calls a service. Services never touch `Request`.
6. The response picks up provenance headers and security headers.

## Identifiers

Prefixed, lexicographically sortable ULIDs: `run_01M3WQ...`, `plan_...`,
`key_...`, `cred_...`. Sortable by creation time, readable in a log line, and
unambiguous about what they point at.

## Error model

Every error carries a stable machine code and never a stack trace:

```json
{
  "error": {
    "code": "BUDGET_EXHAUSTED",
    "message": "The configured SerpFlow budget has been exhausted. Raise the configured budget to continue.",
    "request_id": "8a9e917259104679a693370622a23f64"
  }
}
```

Codes are defined once in
[`core/exceptions.py`](../../backend/app/core/exceptions.py) and both SDKs map
them to remedies.

## Async on Windows

The psycopg async driver cannot run on a proactor event loop, and uvicorn picks
its loop with a factory that returns one on Windows for a single-process run.
`python -m app.server` drives uvicorn with an explicit selector loop factory so
a laptop behaves the same as a container. The reload path already spawns
subprocesses, for which uvicorn selects a selector loop itself.

## Lazy relationship loading

Async SQLAlchemy raises `MissingGreenlet` if a lazy relationship is touched
outside the async context. Where a service creates rows that a serializer reads
immediately, such as `Plan.candidates` and `Run.steps`, the relationship is
marked loaded with `set_committed_value` rather than assigned, because an
ordinary assignment loads the old collection to diff against.

## Degradation

| Dependency | If it is down |
| --- | --- |
| PostgreSQL | `/readyz` returns 503 with the reason. Required. |
| Redis | Degraded. Cache lookups fall through to the durable index, the principal cache misses, rate limiting fails open. |
| Kafka | Degraded. Background events are dropped with a warning; the synchronous path is unaffected, which is why interactive search is not routed through it. |
| Object storage | A cache index entry pointing at a missing object is treated as a miss rather than failing the run. |
