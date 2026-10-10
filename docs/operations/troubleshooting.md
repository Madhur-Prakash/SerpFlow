# Troubleshooting

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka: 4.0 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <a href="../../docker/postgres/init/01-extensions.sql"><img alt="source: init/01-extensions.sql" src="https://img.shields.io/badge/source-init%2F01--extensions.sql-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 11 min" src="https://img.shields.io/badge/read-11%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Troubleshooting** · page 35 of 50

**Start here:**

```bash
make health          # the service and every dependency
curl -s localhost:8000/readyz | python -m json.tool
make ps              # container status
make logs            # tail everything
```

**Jump to:** [setup](#setup) · [database](#database) · [authentication](#authentication) · [execution](#execution) · [cache](#cache) · [streaming](#streaming) · [Kafka](#kafka) · [the demo](#the-demo) · [frontend](#frontend) · [deployment](#deployment) · [logs and resources](#logs-and-resources)

## Setup

### Copied a checkout from Windows

**Symptoms**, after moving a working tree from Windows to Linux or macOS:

- `backend/.venv` holds `Scripts/*.exe` and a `pyvenv.cfg` pointing at `C:\...`: no Python runs
- `frontend/node_modules` holds only `win32` native builds (`@esbuild/win32-x64`, `@rollup/rollup-win32-*`, `lightningcss-win32-*`, `@tailwindcss/oxide-win32-*`): Vite and the build fail
- `git status` shows **every file modified** with equal insertions and deletions: the working tree has CRLF line endings, the repository LF

**Fix:**

```bash
rm -rf backend/.venv frontend/node_modules
make install

git diff --ignore-cr-at-eol --stat     # empty? then the changes are only line endings
```

- **Only if that diff is empty**, `git restore .` puts LF back. It discards **every** uncommitted change, so check first
- To stop it recurring, set `git config core.autocrlf input` on the Linux side, or commit a `.gitattributes` with `* text=auto eol=lf`
- **Clone fresh on each OS** instead of copying a working tree

### `make` fails on Windows

- Run it from **Git Bash or WSL**. The Makefile sets `SHELL := /bin/bash` and uses POSIX syntax throughout
- It detects `backend/.venv/Scripts/python.exe` as well as the POSIX `bin/python`, so the venv itself works either way

### `uv: command not found`

```bash
# https://docs.astral.sh/uv/
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- **uv is the only supported package manager for the backend.** The Makefile and the Docker build both assume it
- **There is no lockfile yet:** dependencies are lower-bounded in `pyproject.toml`, so a fresh install can resolve newer versions than a teammate's

### `hatchling: Readme path must be within the project directory`

- `backend/README.md` is referenced by `backend/pyproject.toml` and **must exist**
- If it was deleted, restore it: hatchling will not resolve a readme above the package root

### `ModuleNotFoundError: greenlet`

SQLAlchemy's async layer needs it explicitly:

```bash
cd backend && uv pip install --python .venv -e ".[dev]"
```

- The dependency is declared as `sqlalchemy[asyncio]` plus `greenlet`, so a clean install picks it up

### A `SERPAPI_API_KEY` in `.env` does nothing

- **Correct:** there is no such setting, and unknown variables are ignored
- SerpApi keys are attached per organization, in the console or with `POST /v1/credentials`. See [bring your own key](../security/byok.md)

## Database

### psycopg fails on Windows (`ProactorEventLoop`)

```
psycopg.errors.OperationalError / RuntimeError: Event loop is closed
```

- **psycopg's async implementation cannot run on `ProactorEventLoop`**, the Windows default. Two things handle it:
  1. `app/__init__.py` sets `WindowsSelectorEventLoopPolicy` at import
  2. `app/server.py` exists because that is not enough: uvicorn 0.54 picks its own loop through a `loop_factory` that returns `ProactorEventLoop` for single-process runs, ignoring the policy

```python
server = uvicorn.Server(uvicorn.Config("app.main:app", **common))
asyncio.run(server.serve(), loop_factory=_loop_factory())
```

- **So run the server as `python -m app.server`**, as `make backend` and the container both do. `uvicorn app.main:app` directly on Windows will fail

### `connection refused` on 5432

```bash
make ps
docker compose logs postgres
```

- **PostgreSQL takes a few seconds on first boot** while initdb runs
- The compose healthcheck covers it for the backend container; a host process started right after `make up` can get ahead of it

### `type "vector" does not exist`

- The extensions are created by [`docker/postgres/init/01-extensions.sql`](../../docker/postgres/init/01-extensions.sql), which runs **only on an empty data directory**
- If the volume predates that file:

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

- **Working as designed:** the trigger refuses `UPDATE` unconditionally, and `DELETE` unless the transaction set `app.audit_purge`
- Deleting an organization and `make seed ARGS=--reset` both go through `AuditService.allow_purge`, which sets it
- **Anything else hitting this is trying to delete audit rows it should not**

### `MissingGreenlet: greenlet_spawn has not been called`

- **A lazy relationship load outside an async context**
- The fix is not to make the load eager; it is to **not load at all**. Build the collection locally and commit it explicitly:

```python
candidate_rows = [...]
set_committed_value(plan_row, "candidates", candidate_rows)
```

- This bit three times during development (plan candidates, the audit diff re-reading an assignment, run steps), always when a relationship was read after the session had moved on

## Authentication

### `INVALID_API_KEY` on a key that looks right

- **Check the environment segment.** An `sf_test_...` key against a project that expects `live` will not resolve; the lookup filters on `environment`
- **Check it was not rotated.** The old key works until `rotation_grace_until`, then stops
- **Check `API_KEY_PEPPER` has not changed.** The pepper is an input to the hash, so changing it invalidates **every** stored key hash. There is no re-peppering without the plaintext, which is gone by design

### A revoked key still works

- **For up to `rotation_grace_until`, deliberately**, so a deploy can roll. `DELETE /v1/keys/{id}` revokes with no grace window
- The 60-second principal cache does **not** extend this: `rotate` and `revoke` both call `invalidate_principal` directly

### `NO_UPSTREAM_CREDENTIAL`

- **A `live` key with no SerpApi credential attached**
- Attach one through `POST /v1/credentials`, or use the `sf_test_...` key that `make seed` prints, which needs no credential at all

### Password reset or verification email never arrives

- **Without Gmail configured, nothing is delivered**, and the link is **not** in the log (the console transport records only template, subject and recipient)
- Configure Gmail: [email](email.md)

## Execution

### `REPLAY_CASSETTE_MISS`

- **`SERPFLOW_MODE=replay`, and no cassette for this request.** Designed behaviour: replay never silently falls back to the network
  - a quiet fallback would spend real credits during what you thought was an offline test
- **Options:**
  - record the cassette with `SERPFLOW_MODE=record` and a live credential
  - use a `test` key for the deterministic mock
  - set the mode to `live`, deliberately

### Results look wrong, but the request succeeded

- **Check `X-SerpFlow-Mode` on the response.** `MOCK` or `REPLAY` means you are not looking at live data
- A `test` API key routes to the mock regardless of `SERPFLOW_MODE`, and that precedence is absolute

### `BUDGET_EXHAUSTED` against `UPSTREAM_QUOTA_EXHAUSTED`

Different causes, different fixes, never conflated:

| Error | Means | Fix |
| --- | --- | --- |
| `BUDGET_EXHAUSTED` | your SerpFlow cap | raise the budget |
| `UPSTREAM_QUOTA_EXHAUSTED` | SerpApi's account quota | add account capacity |

- **If the two disagree**, check `serpflow_upstream_quota_divergence`: the credential is probably also used outside SerpFlow
- `GET /v1/budgets` shows both numbers side by side for exactly that reason

### `NO_VIABLE_PLAN`

- **No chain in the catalog reaches the target capability** from the parameters this intent supplies. Check what the graph thinks:

```bash
curl -s -H "X-API-Key: $KEY" \
  "localhost:8000/v1/catalog/engines/<engine>/paths?params=q,location"
```

- **An empty `paths` array** means the needed dependency edges are missing from the catalog, not that the planner failed

### `CREDENTIAL_REVOKED` part-way through a run

- The credential was revoked while the run was in flight
- **The run fails rather than returning the hops that completed:** a partial result that looks complete is worse than an error, because a caller will act on it

## Cache

### Nothing is ever warm

- **Mode:** a dry run (`execute: false`) plans without executing, and therefore warms nothing
- **Partition:** the cache is partitioned by project by default. Two projects share entries only if `shared_cache_enabled` is on, and then only within one organization
- **Freshness:** "available" is not "acceptable". An entry that misses the step's freshness bound does not count as warm. Check `freshness` on the step and `age_seconds` on the entry

### A semantic hit returned the wrong thing

Report it, which invalidates the entry and increments the counter:

```bash
curl -X POST localhost:8000/v1/runs/$RUN/report-false-hit \
  -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"note":"different neighbourhood","invalidate_entry":true}'
```

- Then look at `GET /v1/cache/guard-rejections` to see what the deterministic guard is catching
- **If the wrong hit had no numerals, versions or named entities to differ on**, raising `SEMANTIC_SIMILARITY_THRESHOLD` is the lever. The guard cannot catch what it cannot see

### Redis evicting too much

- **Eviction pressure, not a correctness problem:** Redis and durable-index hits are both counted as `exact`, so the overall hit rate holds while latency rises
- Check `evicted_keys`, `keyspace_hits` and `used_memory` in `INFO`, then raise `maxmemory`. See [Redis](redis.md)

## Streaming

### The stream arrives all at once at the end

- **Proxy buffering.** `proxy_buffering off` is required on the stream route, and the bundled nginx config sets it
- Behind Caddy, use `flush_interval -1`. Behind any other proxy, set the equivalent

### `EventSource` gets a 401

`EventSource` cannot set headers, so the stream endpoint takes a short-lived access token as a query parameter:

```js
new EventSource(`/v1/runs/${runId}/stream?access_token=${accessToken}`);
```

- **Only an access token.** Never an API key, never a refresh token

### Reconnect replays frames I already saw

Send the last sequence you received:

```http
Last-Event-ID: 14
```

## Kafka

### Producer hangs with no error

- **Almost always the advertised listener.** Use `localhost:9092` from the host and `kafka:19092` from inside a container
- A single listener cannot advertise an address correct from both sides, and the failure is silent: connection succeeds, metadata returns an unreachable address, send blocks until timeout

### `kafka.degraded` in the logs

- **The broker is unreachable, and background delivery has degraded.** Logged once, not per message
- Nothing user-facing depends on it, and the next successful send clears the flag
- `KAFKA_ENABLED=false` turns it off cleanly

### Consumer lag growing

```bash
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group serpflow-workers
```

- **Usually the workers are not running:** `make worker`

## The demo

### `make demo` exits non-zero

**That is the script doing its job.** It fails when marginal-cost replanning did **not** change the selected plan, because a cache hit on the same plan is not the claim being made. Common causes:

- **The cache is already warm for both candidate families**, so there is nothing to disagree about: `make demo ARGS=--reset-cache`
- **The seed did not run**, so the catalog has no substitute edges and only one candidate exists
- **A catalog edit changed relative costs**, so cold and marginal rankings now agree

- **The flip requires two candidates where `naive(X) < naive(Y)` but `marginal(X) > marginal(Y)`**, which requires their warm engines to be disjoint
- Phase 2 denylists `yelp`, `yelp_reviews` and `google_local` specifically, so the Maps corpus warms and the Local corpus does not

### Phase 1 says "3 of 3 steps warm"

- **The cache is still warm from a previous run.** The result is still valid, but the cold/warm comparison is not. Use `make demo ARGS=--reset-cache`

## Frontend

### Vite build fails on types

```bash
cd frontend && npm run typecheck
```

- `src/vite-env.d.ts` must exist for `import.meta.env` to type-check

### The pipeline animation does not move

- **It is driven by real SSE frames, not a timer.** If it is not moving, the stream is not delivering
- Check the network tab for the `stream` request, and see [streaming](../api/streaming.md)

### `make test-ui` cannot launch a browser

- **It uses Playwright's `chrome` channel**, so it needs **Google Chrome** installed (not Chromium)

## Deployment

### `/docs/...` returns a JSON 404 in the container deployment

- **The bundled nginx proxies every path starting with `/docs` to the API**, shadowing the in-app docs routes
- Fix and details: [Docker: known issue](../deployment/docker.md#known-issue-docs-deep-links)

### The production frontend calls `localhost:8000`

- **`VITE_API_BASE_URL` was left at its default**, which is baked into the bundle at build time
- Set it to your public URL and rebuild. An empty value does not work: compose substitutes the default for empty too. See [deployment guide, step 4](../deployment/deployment-guide.md#4-configure-the-environment)

### Every user shares one rate-limit bucket

- **`TRUSTED_PROXY_HOPS` is lower than the number of proxies** in front of the backend, so every request looks like it comes from the proxy
- TLS proxy + bundled nginx: set it to **2**

### Datastore ports are open on a server

- **The bundled compose publishes PostgreSQL, Redis and Kafka on every interface**, and `ufw` does not filter Docker-published ports
- Use the production override in the [deployment guide, step 5](../deployment/deployment-guide.md#5-lock-down-the-ports)

## Logs and resources

### The log fills with SQLAlchemy INFO lines

- **A known issue:** two SQLAlchemy child loggers keep an explicit INFO level, so DDL and mapper-configuration lines get through despite the WARNING pin
- Diagnosis and fix: [observability: known issue](observability.md#known-issue-sqlalchemy-info-lines)

### Integration tests all report `skipped`

- **They skip themselves when PostgreSQL is unreachable**, so a green run can hide them
- Start the services (`make up`), then run `pytest -rs` to see skip reasons

### Docker Desktop quits mid-run

- **Out of memory.** The stack (Kafka's JVM, PostgreSQL), the Docker Desktop VM and a headless browser or large build together can exceed a 16 GB laptop
- Close heavy apps, raise Docker Desktop's memory limit, or stop the stack while doing heavy builds
- After a restart, containers come back on their own (`restart: unless-stopped`). Stop them with `make down`

## Still stuck

- Collect the **request id** and **run id** from the response headers
- Grep the logs for the request id, then open an issue:

```bash
grep '"request_id":"8a9e9172' logs/serpflow.log | python -m json.tool
```

- The log path is `LOG_FILE` (default `logs/serpflow.log`), relative to where the backend runs: `backend/logs/` under `make backend`
- **Report security problems privately**, not in an issue: [SECURITY.md](../../SECURITY.md)

## Related

- [Installation](../deployment/installation.md)
- [Local development](../deployment/local.md)
- [Observability](observability.md)
- [Kafka](kafka.md)
- [Redis](redis.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Redis](../operations/redis.md) | [Docs index](../README.md) | [Architecture decision records](../adr/README.md) |
