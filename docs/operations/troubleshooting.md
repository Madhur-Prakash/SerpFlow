# Troubleshooting

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka: 4.0 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <a href="../../backend/app/core/config.py"><img alt="source: core/config.py" src="https://img.shields.io/badge/source-core%2Fconfig.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 24 min" src="https://img.shields.io/badge/read-24%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Troubleshooting** · page 42 of 57

**Start here:**

```bash
make health          # the service and every dependency
curl -s localhost:8000/readyz | python -m json.tool
make ps              # container status
make logs            # tail everything
```

- What `/readyz` reports, and why only PostgreSQL makes it fail: [observability: health](observability.md#health). Every `make` target: [local development](../deployment/local.md#everyday-targets)

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

- **Correct:** there is no such setting, and unknown variables are ignored (`extra="ignore"` in [`app/core/config.py`](../../backend/app/core/config.py); every real one is in the [secrets inventory](../security/secrets.md#inventory))
- SerpApi keys are attached per organization, in the console or with [`POST /v1/credentials`](../api/overview.md#identity-and-access). See [bring your own key](../security/byok.md#adding-a-key)

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
- Why: [ADR 0013](../adr/0013-explicit-event-loop-factory.md) and [backend: async on Windows](../architecture/backend.md#async-on-windows)

### `connection refused` on 5432

```bash
make ps
docker compose logs postgres
```

- **PostgreSQL takes a few seconds on first boot** while initdb runs
- The compose healthcheck covers it for the backend container; a host process started right after `make up` can get ahead of it
- With `RUN_MIGRATIONS_ON_STARTUP` on, this kills the API at boot rather than on the first query: [bootstrap: failure behaviour](bootstrap.md#failure-behaviour)

### `type "vector" does not exist`

- The extensions are created by [`docker/postgres/init/01-extensions.sql`](../../docker/postgres/init/01-extensions.sql), which runs **only on an empty data directory** ([Docker: PostgreSQL](../deployment/docker.md#postgresql))
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

- **Working as designed:** the trigger refuses `UPDATE` unconditionally, and `DELETE` unless the transaction set `app.audit_purge` ([ADR 0012](../adr/0012-append-only-audit-log.md), [row-level security: the audit log](../database/rls.md#the-audit-log))
- `make seed ARGS=--reset` goes through `AuditService.allow_purge`, which sets it. It is the only caller at HEAD: there is no organization-deletion endpoint yet ([`app/db/seed.py`](../../backend/app/db/seed.py))
- **Anything else hitting this is trying to delete audit rows it should not**

### `MissingGreenlet: greenlet_spawn has not been called`

- **A lazy relationship load outside an async context**
- The fix is not to make the load eager; it is to **not load at all**. Build the collection locally and commit it explicitly:

```python
candidate_rows = [...]
set_committed_value(plan_row, "candidates", candidate_rows)
```

- This bit three times during development (plan candidates, the audit diff re-reading an assignment, run steps), always when a relationship was read after the session had moved on
- The rule and the places it is applied: [backend: lazy relationship loading](../architecture/backend.md#lazy-relationship-loading)

## Authentication

### The CLI or an SDK says `No API key`

```
No API key. Set SERPFLOW_API_KEY or pass --api-key. A test key routes to the deterministic mock and costs nothing.
```

- **The CLI, the Python SDK and the MCP server read `SERPFLOW_API_KEY` from the shell, not from `.env`.** Nothing loads `.env` into your shell; the variable is listed there (commented, in the *CLI, SDK and MCP* block) only so every variable lives in one place
- **Export the `test` key `make seed` printed:**

```bash
export SERPFLOW_API_KEY=sf_test_...     # PowerShell: $env:SERPFLOW_API_KEY = "sf_test_..."
```

- **Who says what:** the CLI prints the line above and exits 2 ([`app/cli/main.py`](../../backend/app/cli/main.py), [CLI exit codes](../sdks/cli.md#exit-codes)); the Python SDK raises `ValueError`; the MCP server fails each tool call with `UNAUTHENTICATED`; the TypeScript SDK reads no environment at all, so pass `apiKey` ([SDKs: configuration](../sdks/overview.md#configuration))
- **No key was printed?** The demo org already existed, so the seed printed *already present*. `make seed ARGS=--reset` prints fresh ones ([bootstrap: seeding by hand](bootstrap.md#seeding-by-hand))
- Every variable: [secrets](../security/secrets.md#inventory)

### `INVALID_API_KEY` on a key that looks right

- **Check the environment segment.** The lookup matches the `sf_live_` / `sf_test_` segment against the stored row's `environment`, so a key whose segment was edited or mistyped will not resolve. A project holds keys of both kinds ([API keys: resolution](../security/api-keys.md#resolution))
- **Check it has not been revoked or expired** (`revoked_at`, `expires_at` on `GET /v1/keys`)
- **Check `API_KEY_PEPPER` has not changed.** The pepper is an input to the hash, so changing it invalidates **every** stored key hash. There is no re-peppering without the plaintext, which is gone by design ([ADR 0004](../adr/0004-hmac-for-api-keys.md), [secrets: pepper](../security/secrets.md#pepper))
  - the MCP server and scripts load their own settings: one started outside `backend/` can pick up a different `.env` and pepper ([MCP: connect a client](../sdks/mcp.md#connect-a-client))

### A revoked key still works

- **Only if it was rotated first, and only until the grace window ends.** `POST /v1/keys/{id}/rotate` stamps `rotation_grace_until` (default 60 minutes, `grace_minutes`, at most 7 days) on the old key; a key revoked inside that window keeps resolving until it ends, so a deploy can roll
- **A key that was never rotated stops at once:** `DELETE /v1/keys/{id}` sets `revoked_at` and calls `invalidate_principal`, so the 60-second principal cache does not extend it
- **Rotation alone does not retire the old key.** `rotate_api_key` sets the grace stamp but never `revoked_at`, and resolution consults the grace window only for a revoked key ([`app/services/auth/service.py`](../../backend/app/services/auth/service.py)). After rotating, revoke the old key with `DELETE /v1/keys/{id}`; until then it keeps working, and rotation does not clear it from the principal cache either ([API keys: rotation](../security/api-keys.md#rotation))

### `NO_UPSTREAM_CREDENTIAL`

- **A `live` key with no SerpApi credential attached**
- Attach one through `POST /v1/credentials`, or use the `sf_test_...` key that `make seed` prints, which needs no credential at all ([bring your own key](../security/byok.md#what-happens-without-each-key))

### Password reset or verification email never arrives

- **Without Gmail configured, nothing is delivered**, and the link is **not** in the log (the console transport records only the subject and recipient) or in the API response
- Configure Gmail: [email: setting up Gmail](email.md#setting-up-gmail)
- **Gmail is configured, and the send failed?** Look for `email.failed` in the log: the error says whether it was transient or permanent. `invalid_grant` means a new token: [email: invalid_grant](email.md#invalid_grant)
- **It arrived, but the link points at `localhost`:** set `FRONTEND_URL` to the public origin ([email](email.md#what-gets-sent))

## Execution

### `REPLAY_CASSETTE_MISS`

- **The resolved mode is `replay`, and there is no cassette for this request.** The mode can come from the request, the project or `SERPFLOW_MODE` ([who chooses, and precedence](../product/execution-modes.md#who-chooses-and-precedence)); an unrecognised value also falls back to `replay`
- Designed behaviour: replay never silently falls back to the network
  - a quiet fallback would spend real credits during what you thought was an offline test
- **Options:**
  - record the cassette in `record` mode with a live credential
  - use a `test` key for the deterministic mock
  - set the mode to `live`, deliberately

### Results look wrong, but the request succeeded

- **Check `X-SerpFlow-Mode` on the response** ([provenance headers](../api/overview.md#provenance-headers)). `MOCK` or `REPLAY` means you are not looking at live data
- A `test` API key routes to the mock regardless of `SERPFLOW_MODE`, and that precedence is absolute ([ADR 0010](../adr/0010-test-key-mode-precedence.md))
- **Then check what was sent:** each step's `parameters` in the Plan Inspector are the values that went upstream. The next three entries are the known ways they went wrong

### Google Finance returned no results, or the ledger shows 0 credits for a search SerpApi charged

**Both fixed.** They were one bug seen from two sides.

- **Google Finance now gets a ticker, not a sentence.** `google_finance` takes a security identifier in `q`; sending the intent made SerpApi answer "Google Finance hasn't returned any results for this query". `adapt_query` in [`app/core/text.py`](../../backend/app/core/text.py) now reshapes it during parameter binding ([planner: query adapters](../architecture/planner.md#query-adapters)):
  - an explicit symbol in the intent wins (`NVDA:NASDAQ`, `BTC-USD`)
  - then a known company, index or crypto name (`FINANCE_SYMBOLS`)
  - otherwise the intent with the conversational filler removed
  - "what is nvidia trading at right now" is sent as `q=NVDA:NASDAQ`
- **An empty SerpApi answer is now a billed, successful search.** `SerpApiResponse.is_empty_result` ([`client.py`](../../backend/app/integrations/serpapi/client.py)) stops treating "no results" as an error, so the spend is recorded in the ledger and budgets, the payload is cached, and **SerpApi's own message is shown as the result's notice** (`summary.notice`, at most 300 characters) instead of a failed run ([executor: an empty answer is still a billed answer](../architecture/executor.md#an-empty-answer-is-still-a-billed-answer))
  - before the fix the step failed and the ledger recorded **0 credits** for a search SerpApi had charged for. Runs from before the fix keep the old numbers; the gap shows up as [`serpflow_upstream_quota_divergence`](observability.md#execution-and-upstream) after a reconciliation
- **Still empty for a company you expected?** It is not in `FINANCE_SYMBOLS`, so the filler-stripped text was sent. Put the symbol in the intent ("TATASTEEL:NSE share price"): an explicit symbol always wins

### `location=right` (or another word that is not a place) was sent upstream

**Fixed.** "what is nvidia trading at right now" used to bind `location=right`; "at least three" bound `location=least`.

- **`extract_location_phrase`** in [`app/core/text.py`](../../backend/app/core/text.py) now skips phrases led by a non-place word (`_NON_PLACE_LEADS`: "right now", "the moment", "least", "a week"...) and cuts the place at the next clause (`_PHRASE_BREAKS`), so "hotels near Shibuya at the moment" gives `Shibuya` ([planner: temporal phrases are not places](../architecture/planner.md#temporal-phrases-are-not-places))
- **A phrase on neither list can still get through.** Rephrase the intent, or add the lead word to `_NON_PLACE_LEADS`
- A wrong `location` is part of the cache key too, so the entry it produced is filed under parameters nobody will ask for again ([normalisation](../architecture/caching.md#normalisation))

### Naver, Baidu or Yandex was chosen for a query outside its market

**Fixed for the deterministic planner**, the default adapter.

- **Regional engines stay in their markets:** `REGIONAL_ENGINES` in [`app/integrations/llm/mock.py`](../../backend/app/integrations/llm/mock.py) marks Naver (`kr`), Baidu (`cn`), and Yandex and Yandex Images (`ru`, `by`, `kz`). Each loses `REGIONAL_PENALTY = 4.0` unless the resolved locale is in its market, the intent names the engine, or the intent is written in the market's script ([planner: stage B](../architecture/planner.md#stage-b-select))
  - "cafes in Koramangala" used to go to Naver, because its catalog entry mentions "blogs and cafes"
- **Still happening?** Check, in order:
  - **which adapter planned.** The Groq adapter has none of these scoring rules; the plan's `stage_trace` records `provider` and `model` ([which adapter plans](../architecture/planner.md#which-adapter-plans))
  - **the resolved locale.** "Seoul" resolves to `gl=kr`, and then Naver is the intended choice
  - **the intent itself.** Naming the engine, or writing in Hangul, CJK or Cyrillic, lifts the penalty on purpose
- The penalty's reason ("naver serves kr; this intent resolves to in") joins the engine's reason trail in the Plan Inspector

### A run failed: why, and what it cost

- **The search page shows it.** A failed run renders a *Run failed* panel with the error code and message, the credits recorded, the mode, and a button to the Run Inspector ([`SearchPage.tsx`](../../frontend/src/pages/SearchPage.tsx), [frontend routes](../architecture/frontend.md#routes))
- **"Credits recorded" can read 0 after a step SerpApi billed.** The failed request's transaction is rolled back, so that run's ledger rows are not persisted; a streamed run is then marked `failed` in a fresh transaction so the Inspector can show why ([executor: when a run fails](../architecture/executor.md#when-a-run-fails))
  - SerpApi's account still counts the search. A [reconciliation](../security/credentials.md#validation-and-revocation) shows the gap as quota divergence
- **The code** is one of the [API errors](../api/overview.md#errors); the common ones have their own entries on this page
- **"No results" is not a failure** any more: see [Google Finance returned no results](#google-finance-returned-no-results-or-the-ledger-shows-0-credits-for-a-search-serpapi-charged)

### `BUDGET_EXHAUSTED` against `UPSTREAM_QUOTA_EXHAUSTED`

Different causes, different fixes, never conflated:

| Error | Means | Fix |
| --- | --- | --- |
| `BUDGET_EXHAUSTED` | your SerpFlow cap | raise the budget |
| `UPSTREAM_QUOTA_EXHAUSTED` | SerpApi's account quota | add account capacity |

- **If the two disagree**, check [`serpflow_upstream_quota_divergence`](observability.md#execution-and-upstream): the credential is probably also used outside SerpFlow
- [`GET /v1/budgets`](../api/overview.md#governance) shows both numbers side by side for exactly that reason
- **`details.binding_scope` names the budget that refused:** session, key, project or organization, checked narrowest first ([executor: budget enforcement](../architecture/executor.md#budget-enforcement)). Before execution, the same allowance already drove [budget-aware reduction](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking)

### An MCP agent's session budget does not carry across calls

- **Set `SERPFLOW_MCP_SESSION` in the MCP server's environment.** Without it every tool call opens a fresh service session: `open_service_session` resumes an open session only when given an external reference ([`app/services/auth/service.py`](../../backend/app/services/auth/service.py))
- **The cap is checked when a named session is resumed** (`credits_used >= session_cap`). With no name nothing is ever resumed, so an agent stuck in a loop never sees `SESSION_CAP_EXCEEDED`
- **With a name**, every call that passes it resumes the same open session, across restarts; once the session has spent its cap the next call fails with `SESSION_CAP_EXCEEDED`. The check runs as a call starts, so the call that crosses the cap completes. Choose a new name to start fresh
- **The cumulative limit without it** is the key's own budget: creating a service principal with a cap (the seed, or `POST /v1/projects/{id}/keys`) also creates an `api_key` budget of the same size, which fails a call with `BUDGET_EXHAUSTED`
- **A `sf_test_` service key, like the seeded one, spends nothing**: the mock is not billed, so neither limit moves
- Setup: [MCP: sessions and budgets](../sdks/mcp.md#sessions-and-budgets) · [API keys: service principal sessions](../security/api-keys.md#service-principal-sessions)

### `NO_VIABLE_PLAN`

- **No chain in the catalog reaches the target capability** from the parameters this intent supplies ([planner: stage D](../architecture/planner.md#stage-d-path-find-and-generate-candidates), [catalog: dependency edges](../architecture/catalog.md#both-relationship-kinds-are-mandatory)). Check what the graph thinks:

```bash
curl -s -H "X-API-Key: $KEY" \
  "localhost:8000/v1/catalog/engines/<engine>/paths?params=q,location"
```

- **An empty `paths` array** means the needed dependency edges are missing from the catalog, not that the planner failed

### `CREDENTIAL_REVOKED` part-way through a run

- The credential was revoked while the run was in flight
- **The run fails rather than returning the hops that completed:** a partial result that looks complete is worse than an error, because a caller will act on it ([executor: revocation mid-run](../architecture/executor.md#revocation-mid-run), [credentials: revoked mid-run](../security/credentials.md#revoked-mid-run))

## Cache

### Nothing is ever warm

- **Mode:** a dry run (`POST /v1/plan`, `serpflow plan`) plans without executing, and therefore warms nothing
- **Partition:** the cache is partitioned by project by default. Two projects share entries only if `shared_cache_enabled` is on, and then only within one organization ([partitioning](../architecture/caching.md#partitioning), [organization-level sharing](../architecture/caching.md#organization-level-sharing))
- **Freshness:** "available" is not "acceptable". An entry that misses the step's freshness bound does not count as warm. Check `freshness_requirement` on the step and `age_seconds` on the entry ([available is not acceptable](../architecture/marginal-replanning.md#available-is-not-acceptable), [ADR 0009](../adr/0009-freshness-gates-warmth.md))
- **A failed run leaves no durable entry:** its transaction is rolled back, `cache_entries` rows included ([executor: when a run fails](../architecture/executor.md#when-a-run-fails)). The Redis pointer and the object-storage payload are written outside that transaction, so an exact repeat can still hit Redis until the pointer expires

### A semantic hit returned the wrong thing

Report it, which invalidates the entry and increments the counter:

```bash
curl -X POST localhost:8000/v1/runs/$RUN/report-false-hit \
  -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"note":"different neighbourhood","invalidate_entry":true}'
```

- **Then invalidate the engine too** (`POST /v1/cache/invalidate` with `{"engine": "..."}`). The report marks the PostgreSQL entry invalidated but leaves Redis alone, and the semantic hit wrote its pointer under the requesting query's key, so that exact query keeps getting the bad payload until the hot key expires ([Redis: invalidation](redis.md#invalidation))
- Then look at `GET /v1/cache/guard-rejections` to see what the deterministic guard is catching ([the entity and numeral guard](../architecture/caching.md#the-entity-and-numeral-guard), [ADR 0003](../adr/0003-deterministic-semantic-guard.md))
- **If the wrong hit had no numerals, versions or named entities to differ on**, raising `SEMANTIC_SIMILARITY_THRESHOLD` (default 0.95) is the lever. The guard cannot catch what it cannot see ([threshold](../architecture/caching.md#threshold-and-what-the-local-embedder-means-for-it))
- Reports are counted in [`serpflow_semantic_false_hit_reports_total`](observability.md#cache), which should page someone

### Redis evicting too much

- **Eviction pressure, not a correctness problem:** Redis and durable-index hits are both counted as `exact`, so the overall hit rate holds while latency rises ([`serpflow_cache_lookup_seconds`](observability.md#cache) shows it)
- Check `evicted_keys`, `keyspace_hits` and `used_memory` in `INFO`, then raise `maxmemory`. See [Redis: configuration](redis.md#configuration)

## Streaming

### The stream arrives all at once at the end

- **Proxy buffering.** `proxy_buffering off` is required on the stream route, and the bundled nginx config sets it ([`frontend/nginx.conf`](../../frontend/nginx.conf))
- Behind Caddy, use `flush_interval -1`. Behind any other proxy, set the equivalent ([streaming: behind a proxy](../api/streaming.md#behind-a-proxy), [deployment guide, step 9](../deployment/deployment-guide.md#9-put-tls-in-front))

### `EventSource` gets a 401

`EventSource` cannot set headers, so the stream endpoint takes a short-lived access token as a query parameter:

```js
new EventSource(`/v1/runs/${runId}/stream?access_token=${accessToken}`);
```

- **Only an access token.** Never an API key, never a refresh token ([streaming: authentication](../api/streaming.md#authentication))

### Reconnect replays frames I already saw

Send the last sequence you received:

```http
Last-Event-ID: 14
```

- The frames are buffered in-process, and mirrored to Redis for 15 minutes so another worker can serve the reconnect ([streaming: reconnecting](../api/streaming.md#reconnecting), [Redis](redis.md#what-lives-in-it))

## Kafka

### Producer hangs with no error

- **Almost always the advertised listener.** Use `localhost:9092` from the host and `kafka:19092` from inside a container
- A single listener cannot advertise an address correct from both sides, and the failure is silent: connection succeeds, metadata returns an unreachable address, send blocks until timeout ([Kafka: listeners](kafka.md#listeners))

### `kafka.degraded` in the logs

- **The producer could not start, and background messages are being dropped.** Logged once, not per message; each dropped message counts as `status="skipped"` in [`serpflow_kafka_messages_total`](observability.md#http-and-kafka)
- Nothing user-facing depends on it. The two credential endpoints that queue work answer `ok: false` with "Kafka is unavailable"
- **Recovery is silent:** each later publish retries the start, and the first success clears the flag. No "recovered" line is logged ([Kafka: degradation](kafka.md#degradation))
- `KAFKA_ENABLED=false` turns it off cleanly

### Consumer lag growing

```bash
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --all-groups
```

- **Each topic has its own group, `serpflow-workers.<topic>`**; there is no plain `serpflow-workers` group to describe ([Kafka: running consumers](kafka.md#running-consumers))
- **Usually the workers are not running:** `make worker`, or an API with `KAFKA_ENABLED=true`, which runs the same consumers in-process
- **A handler that raises does not stall the group:** it logs `kafka.handler_failed` and the offset is committed anyway, so lag is a throughput or liveness problem, not a poison message

## The demo

### `make demo` exits non-zero

**That is the script doing its job.** It prints `NOT PROVEN.` and exits 1 when marginal-cost replanning did **not** change the selected plan, because a cache hit on the same plan is not the claim being made ([the demo: what it is proving](../product/demo.md#what-it-is-proving)). Common causes:

- **The cache is already warm for both candidate families**, so there is nothing to disagree about: `make demo ARGS=--reset-cache`
- **The seed did not run:** the script stops at once with *Demo organization not found. Run `make seed` first.* Its other two messages say `make seed --reset`; the working form is `make seed ARGS=--reset`
- **A catalog edit changed relative costs**, so cold and marginal rankings now agree ([catalog: the reference demo chain](../architecture/catalog.md#the-reference-demo-chain))

- **The flip requires two candidates where `naive(X) < naive(Y)` but `marginal(X) > marginal(Y)`**, which requires their warm engines to be disjoint ([marginal replanning: the reference demo](../architecture/marginal-replanning.md#worked-example-the-reference-demo))
- Phase 2 denylists `yelp`, `yelp_reviews` and `google_local` specifically, so the Maps corpus warms and the Local corpus does not ([phase 2](../product/demo.md#phase-2-a-different-project-warms-the-maps-chain))

### Phase 1 says "3 of 3 steps warm"

- **The cache is still warm from a previous run.** The result is still valid, but the cold/warm comparison is not. Use `make demo ARGS=--reset-cache` ([reproducing from a clean state](../product/demo.md#reproducing-from-a-clean-state))

## Frontend

### Vite build fails on types

```bash
cd frontend && npm run typecheck
```

- `src/vite-env.d.ts` must exist for `import.meta.env` to type-check

### The pipeline animation does not move

- **It is driven by real SSE frames, with no simulated progression.** `usePacedRun` in [`useRunStream.ts`](../../frontend/src/hooks/useRunStream.ts) reveals stages one at a time, each visibly running for at least 320 ms (600 ms for executing) so it can be read, but it never shows a stage complete before its frame arrives and never runs ahead of the backend; the timings shown are the real ones ([frontend: the pipeline animation](../architecture/frontend.md#the-pipeline-animation))
- **So if it is not moving, the stream is not delivering.** Check the network tab for the `stream` request, and see [streaming](../api/streaming.md#the-stage-sequence)
- **Nothing moves, then everything appears at the end:** a proxy is buffering the stream ([the stream arrives all at once](#the-stream-arrives-all-at-once-at-the-end))

### `make test-ui` cannot launch a browser

- **It uses Playwright's `chrome` channel**, so it needs **Google Chrome** installed (not Chromium). What its checks assert: [web: verifying it](../architecture/web.md#verifying-it)

## Deployment

### `/docs/...` returns a JSON 404 in the container deployment

- **The bundled nginx proxies every path starting with `/docs` to the API**, shadowing the in-app docs routes
- Fix and details: [Docker: known issue](../deployment/docker.md#known-issue-docs-deep-links)

### The production frontend calls `localhost:8000`

- **`VITE_API_BASE_URL` was left at its default**, which is baked into the bundle at build time
- Set it to your public URL and rebuild. An empty value does not work: compose substitutes the default for empty too. See [deployment guide, step 4](../deployment/deployment-guide.md#4-configure-the-environment)

<a id="every-user-shares-one-rate-limit-bucket"></a>

### Every caller is recorded with the proxy's IP

- **`TRUSTED_PROXY_HOPS` is lower than the number of proxies** in front of the backend. `client_ip` reads the address that many entries from the right of `X-Forwarded-For`, so with too few hops every request looks like it comes from the outermost proxy ([`app/api/deps.py`](../../backend/app/api/deps.py))
- **What it affects:** the `ip` on [audit log](../database/rls.md#the-audit-log) entries, an API key's `last_used_ip`, and the IP stored on login sessions
- **What it does not affect: the rate limit.** That is keyed by principal and path, not by IP, so callers never share a bucket through this setting ([Redis: rate limits](redis.md#rate-limits), [API: rate limiting](../api/overview.md#rate-limiting))
- TLS proxy + bundled nginx: set it to **2** ([deployment guide, step 4](../deployment/deployment-guide.md#4-configure-the-environment))
- **Too high is worse than too low:** a client that sends its own `X-Forwarded-For` entries can then choose the address that gets recorded. With fewer entries than hops, the socket peer is used

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

- Collect the **request id** and **run id** from the response headers (`X-Request-Id`, `X-SerpFlow-Run-Id`), and the trace id if tracing is on ([correlating one request](observability.md#correlating-one-request))
- Grep the logs for the request id, then open an issue:

```bash
grep '"request_id": "8a9e9172' logs/serpflow.log | python -m json.tool
```

- **Mind the space after the colon:** the JSON log writes `"request_id": "..."`
- The log path is `LOG_FILE` (default `logs/serpflow.log`), relative to where the backend runs: `backend/logs/` under `make backend`
- **The run id opens the Run Inspector**, which shows the plan, each step's cache layer and the error ([`GET /v1/runs/{id}`](../api/overview.md#runs))
- **Report security problems privately**, not in an issue: [SECURITY.md](../../SECURITY.md)

## Related

- [Observability](observability.md#correlating-one-request): following one request through logs, metrics and traces
- [Local development](../deployment/local.md#troubleshooting): the problems specific to a laptop setup
- [Installation](../deployment/installation.md#if-something-fails): failures while installing prerequisites
- [API overview](../api/overview.md#errors): every error code, with its status
- [Executor](../architecture/executor.md#when-a-run-fails): what a failed run keeps, and what is rolled back
- [Planner](../architecture/planner.md#stage-c-synthesize): how parameters such as `location` and Google Finance's `q` are bound
- [ADR 0010](../adr/0010-test-key-mode-precedence.md): why a test key always means mock data
- [Kafka](kafka.md#degradation) and [Redis](redis.md#degradation): why neither outage takes the API down

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Redis](../operations/redis.md) | [Docs index](../README.md) | [Architecture decision records](../adr/README.md) |
