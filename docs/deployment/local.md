# Local development

The target is a working system with **no API keys at all**. `make dev` and
`make seed` must both succeed on a machine that has never seen a SerpApi key,
and they do: the planner falls back to a deterministic mock, execution falls
back to cassettes, and `sf_test_...` keys return mock results.

## Prerequisites

| Tool | Version | Why |
| --- | --- | --- |
| Python | 3.13+ | the backend targets it, and `uv venv --python 3.13` pins it |
| uv | latest | the only supported Python package manager here |
| Node | 20+ | Vite 7 and the TypeScript 5.9 toolchain |
| Docker | with Compose v2 | PostgreSQL, Redis and Kafka |
| GNU Make | any | the Makefile is the documented entry point |

On Windows, run `make` from Git Bash or WSL. The Makefile detects
`backend/.venv/Scripts/python.exe` as well as the POSIX `bin/python`, so the
venv works either way.

## First run

```bash
cp .env.example .env     # nothing in it needs editing to get started
make install             # uv venv + backend deps, then npm install
make up                  # postgres, redis, kafka
make upgrade             # migrations
make seed                # catalog, benchmark fixtures, demo org - prints a test key
make dev                 # API on :8000, frontend on :5173
```

`make seed` prints four API keys and two sign-in accounts. They are shown
once.

```
Sign in at http://localhost:5173
  owner    owner@serpflow.demo  /  ...
  analyst  analyst@serpflow.demo  /  ...

API keys (shown once, exactly as the product shows them):
  test     sf_test_...
           routes to the deterministic mock, spends 0 SerpApi credits
  live     sf_live_...
           honours SERPFLOW_MODE; needs a real credential in the vault
  service  sf_test_...
           MCP service principal, with its own session cap
  market   sf_test_...
           second project, for the cross-project cache benefit view
```

Use the `test` key for everything in these docs.

## What is running

```
make up
  postgres  localhost:5432   pgvector/pgvector:pg17
  redis     localhost:6379   redis:7-alpine
  kafka     localhost:9092   apache/kafka:4.0.0, KRaft mode, no ZooKeeper

make dev
  backend   localhost:8000   uvicorn with reload
  frontend  localhost:5173   vite dev server
```

Two optional compose profiles:

```bash
docker compose --profile storage up -d        # MinIO, for S3-backed payloads
docker compose --profile observability up -d  # Prometheus and Grafana
docker compose --profile full up -d           # both
```

Neither is needed. Payload storage defaults to the filesystem, which is exactly
why `make dev` needs no extra services.

## Everyday targets

```bash
make help            # the full list, generated from the Makefile itself

make backend         # API only
make frontend        # frontend only
make worker          # Kafka consumers on their own
make mcp             # MCP server over stdio

make test            # whole suite
make test-unit       # no services needed
make test-integration
make test-e2e        # includes the thesis assertion

make lint            # ruff + eslint
make format          # ruff format, ruff --fix, prettier
make typecheck       # mypy + tsc

make demo            # the reference demo, exits non-zero if the thesis fails
make health          # service and every dependency
make psql            # psql shell
make redis-cli       # redis-cli shell
```

## Modes

`SERPFLOW_MODE` defaults to `replay`: cassettes only, and a miss raises
`REPLAY_CASSETTE_MISS` rather than silently reaching the network.

```
live     normal billable execution against SerpApi
record   execute live and persist cassettes to fixtures/cassettes
replay   serve from cassettes only, fail loudly on a miss
```

A `test` API key routes to the deterministic mock **regardless** of this
setting. That precedence is absolute and cannot be overridden, which is what
makes it safe to develop against a repository that has a live key in its `.env`.

To use real SerpApi credits, set `SERPFLOW_MODE=live`, attach a credential
through `POST /v1/credentials` or `SERPAPI_API_KEY` for the seed script, and
use a `sf_live_...` key.

For real LLM planning instead of the deterministic mock:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
```

Planning calls the model, not SerpApi, so this costs Groq tokens and zero
SerpApi credits.

## Proving the thesis

```bash
make demo
```

Three phases, all inside the SerpApi free tier:

1. A cold **dry run** that plans without executing, to record what the cold
   ranking chooses.
2. A warm-up that executes a related intent, filling the cache for one engine
   family and not the other.
3. The same intent as phase 1, now warm.

If marginal-cost replanning did not change the selected plan, the script exits
non-zero and says so. A cache hit on the same plan is not sufficient and is not
accepted as a pass.

```
  PROVEN: cache-aware marginal-cost replanning changed the selected plan.
```

## Resetting

```bash
make seed ARGS=--reset              # delete the demo org and reload
docker compose down -v && make up   # drop volumes and start from nothing
make clean                          # caches and build artefacts only
```

## Troubleshooting

A dedicated page covers the common failures:
[operations/troubleshooting](../operations/troubleshooting.md).

The two that catch people most often:

**psycopg and the Windows event loop.** psycopg's async implementation cannot
run on `ProactorEventLoop`, and uvicorn 0.54 selects that loop itself for
single-process runs, ignoring the policy. `app/server.py` exists specifically
to pass an explicit `loop_factory`, which is why `make backend` runs
`python -m app.server` rather than `uvicorn app.main:app`.

**Kafka not ready yet.** The broker takes a few seconds to form its KRaft
quorum. `/readyz` reports it as degraded rather than failing, because Kafka
carries only background work.

## Related

- [Docker](docker.md)
- [Production](production.md)
- [Troubleshooting](../operations/troubleshooting.md)
