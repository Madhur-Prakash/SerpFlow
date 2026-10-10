# Local development

<p>
  <a href="../README.md#deployment"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="API keys: not required" src="https://img.shields.io/badge/API%20keys-not%20required-3fcf8e">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="uv: venv" src="https://img.shields.io/badge/uv-venv-DE5FE9?logo=uv&logoColor=white">
  <img alt="Node: 22" src="https://img.shields.io/badge/Node-22-5FA04E?logo=nodedotjs&logoColor=white">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../README.md#deployment) › **Local development** · page 6 of 50

**The target: a working system with no API keys at all.** `make dev` and `make seed` must both succeed on a machine that has never seen a SerpApi key, and they do:

- the planner falls back to a **deterministic adapter**
- execution falls back to **cassettes**
- `sf_test_...` keys return **mock** results

## Prerequisites

| Tool | Version | Why |
| --- | --- | --- |
| Python | 3.13+ | the backend targets it, and `uv venv --python 3.13` pins it |
| uv | latest | the only supported Python package manager here |
| Node | 20+ | Vite 6 and the TypeScript 5.9 toolchain |
| Docker | with Compose v2 | PostgreSQL, Redis and Kafka |
| GNU Make | any | the Makefile is the documented entry point |

- **On Windows**, run `make` from Git Bash or WSL
  - the Makefile finds `backend/.venv/Scripts/python.exe` as well as the POSIX `bin/python`, so the venv works either way
- **Moving a checkout between Windows and Linux or macOS?** The venv and `node_modules` contain platform-specific binaries. Recreate both, see [troubleshooting](../operations/troubleshooting.md#copied-a-checkout-from-windows)

## First run

```bash
cp .env.example .env     # nothing in it needs editing to get started
make install             # uv venv + backend deps, then npm install
make up                  # postgres, redis, kafka
make upgrade             # migrations
make seed                # catalog, benchmark fixtures, demo org - prints a test key
make dev                 # API on :8000, frontend on :5173
```

`make seed` prints **four API keys and two sign-in accounts**, shown once:

```
Sign in at http://localhost:5173
  owner    owner@serpflow.dev    /  serpflow-demo-2026
  analyst  analyst@serpflow.dev  /  serpflow-demo-2026

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

- **Use the `test` key** for everything in these docs

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

Optional compose profiles:

```bash
docker compose --profile storage up -d        # MinIO, for S3-backed payloads
docker compose --profile observability up -d  # Prometheus and Grafana
docker compose --profile full up -d           # both
```

- **Neither is needed.** Payload storage defaults to the filesystem, which is why `make dev` needs no extra services

## Everyday targets

```bash
make help            # the full list, generated from the Makefile itself

make backend         # API only
make frontend        # frontend only
make worker          # Kafka consumers on their own
make mcp             # MCP server over stdio

make test            # whole suite (216 tests)
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

make docs-check      # every relative link and path in the docs resolves
make docs-nav        # regenerate doc badges, breadcrumbs and prev/next links
```

## Modes

- `SERPFLOW_MODE` **defaults to `replay`:** cassettes only. A miss raises `REPLAY_CASSETTE_MISS` instead of silently reaching the network

```
live     normal billable execution against SerpApi
record   execute live and persist cassettes to fixtures/cassettes
replay   serve from cassettes only, fail loudly on a miss
```

- **A `test` API key routes to the deterministic mock regardless of this setting**
  - that precedence is absolute and cannot be overridden
  - it is what makes it safe to develop against a repository with a live key in its `.env`
- `SERPFLOW_MODE` is only the **instance default**. A project can set its own mode, and a single search can override it: see [execution modes](../product/execution-modes.md)

## Using real keys

- **SerpFlow is bring-your-own-key:** both upstream keys belong to the organization, not the deployment
- **There is no `SERPAPI_API_KEY` setting.** If your `.env` has one, it is ignored. Nothing falls back to a key held by the instance
- **To execute real searches**, attach your SerpApi key in the console under Settings → Credentials, or:

```bash
curl -X POST http://localhost:8000/v1/credentials   -H "Authorization: Bearer $SERPFLOW_API_KEY"   -H "Content-Type: application/json"   -d '{"name": "My SerpApi account", "api_key": "..."}'
```

- Then set the project's mode to `live` and use an `sf_live_...` key
- **For model-driven planning**, attach a Groq key the same way, with `"provider": "groq"`
  - planning calls Groq, not SerpApi: it costs Groq tokens and **zero** SerpApi credits
- **The two variables below are a self-hosting fallback**, used only when an organization has brought no Groq key of its own

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

- **Leave them unset if anyone else will use this instance:** otherwise your key answers for organizations that never supplied one
- More: [bring your own key](../security/byok.md)

## Proving the thesis

```bash
make demo
```

Three phases, all inside the SerpApi free tier:

1. A cold **dry run** that plans without executing, to record what the cold ranking chooses
2. A **warm-up** from a second project, filling the shared cache for one engine family and not the other
3. **The same intent as phase 1**, now warm

- If marginal-cost replanning did **not** change the selected plan, the script exits non-zero and says so
- A cache hit on the same plan is **not** accepted as a pass

```
  PROVEN: cache-aware marginal-cost replanning changed the selected plan.
```

- Walkthrough: [the reference demo](../product/demo.md)

## Resetting

```bash
make seed ARGS=--reset              # delete the demo org and reload
docker compose down -v && make up   # drop volumes and start from nothing
make clean                          # caches and build artefacts only
```

## Troubleshooting

A dedicated page covers the common failures: [operations/troubleshooting](../operations/troubleshooting.md). The two that catch people most often:

- **psycopg and the Windows event loop**
  - psycopg's async implementation cannot run on `ProactorEventLoop`
  - uvicorn 0.54 picks that loop itself for single-process runs, ignoring the policy
  - `app/server.py` exists to pass an explicit `loop_factory`, which is why `make backend` runs `python -m app.server` and not `uvicorn app.main:app`
- **Kafka not ready yet**
  - the broker takes a few seconds to form its KRaft quorum
  - `/readyz` reports it as degraded rather than failing, because Kafka only carries background work

## Related

- [Docker](docker.md)
- [Production](production.md)
- [Troubleshooting](../operations/troubleshooting.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Installation](../deployment/installation.md) | [Docs index](../README.md) | [Docker](../deployment/docker.md) |
