# Troubleshooting

Start here:

```bash
make health          # the service and every dependency
curl -s localhost:8000/readyz | python -m json.tool
make ps              # container status
make logs            # tail everything
```

## Setup

### `make` fails on Windows

Run it from Git Bash or WSL. The Makefile sets `SHELL := /bin/bash` and uses
POSIX syntax throughout. It does detect `backend/.venv/Scripts/python.exe` as
well as the POSIX `bin/python`, so the venv itself works either way.

### `uv: command not found`

```bash
# https://docs.astral.sh/uv/
curl -LsSf https://astral.sh/uv/install.sh | sh
```

uv is the only supported package manager for the backend. The lockfile and the
Docker build both assume it.

### `hatchling: Readme path must be within the project directory`

`backend/README.md` is referenced by `backend/pyproject.toml` and must exist.
If it was deleted, restore it; hatchling will not resolve a readme above the
package root.

### `ModuleNotFoundError: greenlet`

SQLAlchemy's async layer needs it explicitly:

```bash
cd backend && uv pip install --python .venv -e ".[dev]"
```

The dependency is declared as `sqlalchemy[asyncio]` plus `greenlet`, so a clean
install picks it up.

## Database

### `ProactorEventLoop` / psycopg fails on Windows

```
psycopg.errors.OperationalError / RuntimeError: Event loop is closed
```

psycopg's async implementation cannot run on `ProactorEventLoop`, which is the
Windows default. Two things are in place for it:

1. `app/__init__.py` sets `WindowsSelectorEventLoopPolicy` at import.
2. `app/server.py` exists because that is not enough: uvicorn 0.54 picks its
   own loop through a `loop_factory` that returns `ProactorEventLoop` for
   single-process runs, ignoring the policy.

```python
server = uvicorn.Server(uvicorn.Config("app.main:app", **common))
asyncio.run(server.serve(), loop_factory=_loop_factory())
```

So run the server as `python -m app.server`, which is what `make backend` and
the container both do. Running `uvicorn app.main:app` directly on Windows will
fail.

### `connection refused` on 5432

```bash
make ps
docker compose logs postgres
```

PostgreSQL takes a few seconds on first boot while initdb runs. The compose
healthcheck covers it for the backend container; a host process started
immediately after `make up` can get ahead of it.

### `type "vector" does not exist`

The extensions are created by
[`docker/postgres/init/01-extensions.sql`](../../docker/postgres/init/01-extensions.sql),
which runs **only on an empty data directory**. If the volume predates that
file:

```bash
docker compose down -v && make up && make upgrade
```

Or create them by hand as superuser:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
```

### `audit_log is append-only; DELETE is not permitted`

Working as designed. The trigger refuses `UPDATE` unconditionally and `DELETE`
unless the transaction has set `app.audit_purge`. Deleting an organization and
`make seed ARGS=--reset` both go through `AuditService.allow_purge`, which sets
it. Anything else hitting this is trying to delete audit rows it should not.

### `MissingGreenlet: greenlet_spawn has not been called`

A lazy relationship load outside an async context. The fix is not to make the
load eager; it is to not load at all. Build the collection locally and commit
it explicitly:

```python
candidate_rows = [...]
set_committed_value(plan_row, "candidates", candidate_rows)
```

This bit three times during development — plan candidates, the audit diff
re-reading an assignment, and run steps — always at the moment a relationship
was read after the session had moved on.

## Authentication

### `INVALID_API_KEY` on a key that looks right

- Check the environment segment. An `sf_test_...` key against a project that
  expects `live` will not resolve; the lookup filters on `environment`.
- Check it was not rotated. The old key works until `rotation_grace_until`,
  then stops.
- Check `API_KEY_PEPPER` has not changed. The pepper is an input to the hash,
  so changing it invalidates every stored key hash. There is no re-peppering
  without the plaintext, and the plaintext is gone by design.

### A revoked key still works

For up to `rotation_grace_until`, deliberately, so a deploy can roll. `DELETE
/v1/keys/{id}` revokes with no grace window.

The 60-second principal cache does not extend this: `rotate` and `revoke` both
call `invalidate_principal` directly.

### `NO_UPSTREAM_CREDENTIAL`

A `live` key with no SerpApi credential attached. Either attach one through
`POST /v1/credentials`, or use the `sf_test_...` key that `make seed` prints,
which needs no credential at all.

## Execution

### `REPLAY_CASSETTE_MISS`

`SERPFLOW_MODE=replay` and no cassette for this request. This is the designed
behaviour: replay never silently falls back to the network, because a quiet
fallback spends real credits during what you thought was an offline test.

Options: record the cassette with `SERPFLOW_MODE=record` and a live
credential, use a `test` key for the deterministic mock, or set
`SERPFLOW_MODE=live` deliberately.

### Results look wrong but the request succeeded

Check `X-SerpFlow-Mode` on the response. `MOCK` or `REPLAY` means you are not
looking at live data. A `test` API key routes to the mock regardless of
`SERPFLOW_MODE`, and that precedence is absolute.

### `BUDGET_EXHAUSTED` against `UPSTREAM_QUOTA_EXHAUSTED`

Different causes, different fixes, never conflated:

- `BUDGET_EXHAUSTED` — your SerpFlow cap. Raise the budget.
- `UPSTREAM_QUOTA_EXHAUSTED` — SerpApi's account quota. Add account capacity.

If the two disagree with each other, check
`serpflow_upstream_quota_divergence`: the credential is probably being used
outside SerpFlow as well, and `GET /v1/budgets` shows both numbers side by
side for that reason.

### `NO_VIABLE_PLAN`

No chain in the catalog reaches the target capability from the parameters this
intent supplies. Check what the graph thinks:

```bash
curl -s -H "X-API-Key: $KEY" \
  "localhost:8000/v1/catalog/engines/<engine>/paths?params=q,location"
```

An empty `paths` array means the dependency edges needed are missing from the
catalog, not that the planner failed.

### `CREDENTIAL_REVOKED` part-way through a run

The credential was revoked while the run was in flight. The run fails rather
than returning the hops that completed, because a partial result set that looks
complete is worse than an error — a caller will act on it.

## Cache

### Nothing is ever warm

- Mode: a dry run (`execute: false`) plans without executing and therefore
  warms nothing.
- Partition: the cache is partitioned by project by default. Two projects do
  not share entries unless `shared_cache_enabled` is on, and then only within
  one organization.
- Freshness: "available" is not "acceptable". An entry that does not satisfy
  the step's freshness bound does not count as warm. Check `freshness` on the
  step and `age_seconds` on the entry.

### A semantic hit returned the wrong thing

Report it, which invalidates the entry and increments the counter:

```bash
curl -X POST localhost:8000/v1/runs/$RUN/report-false-hit \
  -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"note":"different neighbourhood","invalidate_entry":true}'
```

Then look at `GET /v1/cache/guard-rejections` to see what the deterministic
guard is catching. If the wrong hit had no numerals, versions or named entities
to differ on, raising `SEMANTIC_SIMILARITY_THRESHOLD` is the lever; the guard
cannot catch what it cannot see.

### Hot hits collapsed into exact hits

Redis eviction pressure, not a correctness problem. Check `evicted_keys` and
`used_memory` in `INFO`, and raise `maxmemory`. See [Redis](redis.md).

## Streaming

### The stream arrives all at once at the end

Proxy buffering. `proxy_buffering off` is required on the stream route, and the
bundled nginx config sets it. Behind any other proxy, set the equivalent.

### `EventSource` gets a 401

`EventSource` cannot set headers, so the stream endpoint takes a short-lived
access token as a query parameter:

```js
new EventSource(`/v1/runs/${runId}/stream?access_token=${accessToken}`);
```

Only an access token. Never an API key, never a refresh token.

### Reconnect replays frames I already saw

Send the last sequence you received:

```http
Last-Event-ID: 14
```

## Kafka

### Producer hangs with no error

Almost always the advertised listener. Use `localhost:9092` from the host and
`kafka:19092` from inside a container. A single listener cannot advertise an
address correct from both sides, and the failure is silent: connection
succeeds, metadata returns an unreachable address, send blocks until timeout.

### `kafka.degraded` in the logs

The broker is unreachable and background delivery has degraded. Logged once,
not per message. Nothing user-facing depends on it, and the next successful
send clears the flag. `KAFKA_ENABLED=false` turns it off cleanly.

### Consumer lag growing

```bash
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group serpflow-workers
```

Usually the workers are not running. `make worker`.

## The demo

### `make demo` exits non-zero

That is the script doing its job. It fails when marginal-cost replanning did
**not** change the selected plan, because a cache hit on the same plan is not
the claim being made.

Common causes:

- The cache is already warm for both candidate families, so there is nothing to
  disagree about. `make demo ARGS=--reset-cache`.
- The seed did not run, so the catalog has no substitute edges and only one
  candidate exists.
- A catalog edit changed relative costs such that cold and marginal rankings
  now agree.

The flip requires two candidates where `naive(X) < naive(Y)` but
`marginal(X) > marginal(Y)`, which requires their warm engines to be disjoint.
Phase 2 of the demo denylists `yelp`, `yelp_reviews` and `google_local`
specifically so the Maps corpus warms and the Local corpus does not.

## Frontend

### Vite build fails on types

```bash
cd frontend && npm run typecheck
```

`src/vite-env.d.ts` must exist for `import.meta.env` to type-check.

### The pipeline animation does not move

It is driven by real SSE frames, not a timer. If it is not moving, the stream
is not delivering — check the network tab for the `stream` request and see
[streaming](../api/streaming.md).

## Still stuck

Collect the request id and run id from the response headers, grep the logs for
the request id, and open an issue:

```bash
grep '"request_id":"8a9e9172' backend/logs/serpflow.log | python -m json.tool
```

## Related

- [Local development](../deployment/local.md)
- [Observability](observability.md)
- [Kafka](kafka.md)
- [Redis](redis.md)
