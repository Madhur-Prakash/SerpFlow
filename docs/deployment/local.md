# Local development

<p>
  <a href="../deployment/README.md"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="API keys: not required" src="https://img.shields.io/badge/API%20keys-not%20required-3fcf8e">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="uv: venv" src="https://img.shields.io/badge/uv-venv-DE5FE9?logo=uv&logoColor=white">
  <img alt="Node: 22" src="https://img.shields.io/badge/Node-22-5FA04E?logo=nodedotjs&logoColor=white">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <a href="../../backend/app/integrations/llm/mock.py"><img alt="source: llm/mock.py" src="https://img.shields.io/badge/source-llm%2Fmock.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 13 min" src="https://img.shields.io/badge/read-13%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../deployment/README.md) › **Local development** · page 9 of 50

**The target: a working system with no API keys at all.** `make dev` and `make seed` must both succeed on a machine that has never seen a SerpApi key, and they do:

- the planner falls back to a **deterministic adapter** ([`app/integrations/llm/mock.py`](../../backend/app/integrations/llm/mock.py), returned by `get_llm()` unless `LLM_PROVIDER=groq`)
- execution falls back to **cassettes** ([execution modes](../product/execution-modes.md))
- `sf_test_...` keys return **mock** results ([test keys](../security/api-keys.md#test-keys))

## Prerequisites

| Tool | Version | Why |
| --- | --- | --- |
| Python | 3.13+ | the backend targets it, and `uv venv --python 3.13` pins it; `uv` downloads it if the machine lacks it |
| uv | latest | the only supported Python package manager here |
| Node | 20+ | Vite 6 and the TypeScript 5.9 toolchain |
| Docker | with Compose v2 | PostgreSQL, Redis and Kafka |
| GNU Make | any | the [`Makefile`](../../Makefile) is the documented entry point |

- Per-OS install commands: [installation: prerequisites](installation.md#1-prerequisites)
- **On Windows**, run `make` from Git Bash or WSL ([troubleshooting](../operations/troubleshooting.md#make-fails-on-windows))
  - the Makefile finds `backend/.venv/Scripts/python.exe` as well as the POSIX `bin/python`, so the venv works either way
- **Moving a checkout between Windows and Linux or macOS?** The venv and `node_modules` contain platform-specific binaries. Recreate both, see [troubleshooting](../operations/troubleshooting.md#copied-a-checkout-from-windows)

## First run

```bash
cp .env.example .env     # nothing in it needs editing to get started
make install             # uv venv + backend deps, then npm install
make up                  # postgres, redis, kafka
make upgrade             # migrations
make seed                # catalog, benchmark fixtures, demo org - prints two sign-ins and four keys
make dev                 # API on :8000, frontend on :5173
```

- Every step explained: [installation: path A](installation.md#path-a-developer-install)
- **`.env.example` turns on the [startup bootstrap](../operations/bootstrap.md)** (`RUN_MIGRATIONS_ON_STARTUP`, `SEED_ON_STARTUP`), and `make backend` reads the same `.env`, so the API also migrates and seeds itself on start. `make upgrade` and `make seed` stay in the sequence: the seed script needs the schema, and only the seed script prints keys

`make seed` prints **four API keys and two sign-in accounts**, shown once ([`backend/scripts/seed.py`](../../backend/scripts/seed.py)):

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
           MCP service principal, 20-credit session cap
  market   sf_test_...
           second project, for the cross-project cache benefit view
```

- **Use the `test` key** for everything in these docs
- **Keys are printed only when the seed creates the demo organization.** A second run says `Demo organization already present` and prints none: `make seed ARGS=--reset` recreates it with fresh keys ([seeding by hand](../operations/bootstrap.md#seeding-by-hand))
- The `service` key is a [service principal](../security/api-keys.md#service-principal-sessions); the other three carry the `developer` role, and `service` carries `service` ([roles](../security/api-keys.md#roles))

## CLI, SDK and MCP

**The `serpflow` CLI, the Python SDK and the MCP server read their settings from the shell, not from `.env`.** Nothing loads `.env` into your shell for them:

```bash
export SERPFLOW_API_KEY=sf_test_...            # the test key make seed printed
export SERPFLOW_BASE_URL=http://localhost:8000 # optional; this is the default
export SERPFLOW_MCP_SESSION=my-agent           # optional, MCP only
```

| Variable | Read by | Meaning |
| --- | --- | --- |
| `SERPFLOW_API_KEY` | CLI, Python SDK, MCP | the key every call authenticates with. A `test` key spends zero SerpApi credits |
| `SERPFLOW_BASE_URL` | CLI, Python SDK | the API to call. **The MCP server ignores it:** it runs the services in-process against `DATABASE_URL`, which it reads from `.env` because it starts in `backend/` |
| `SERPFLOW_MCP_SESSION` | MCP | names the service session; the same name resumes it, so the session budget carries across restarts. Unset, each tool call made with a service key opens a new session, so the cap bounds single calls rather than the agent's total |

- Sources: [`app/cli/main.py`](../../backend/app/cli/main.py) · [`app/sdk/__init__.py`](../../backend/app/sdk/__init__.py) · [`app/mcp/server.py`](../../backend/app/mcp/server.py). Listed in the `.env.example` "CLI, SDK and MCP" block and in [secrets](../security/secrets.md#inventory)
- **`make install` already installed all three** into `backend/.venv`, as an editable install. The SDKs are not released to PyPI or npm until the author decides to host SerpFlow, so a self-hosted setup uses them from this checkout ([why](../sdks/releasing.md#first-who-runs-the-server))
- How to run each: [CLI](../sdks/cli.md) · [Python SDK: install](../sdks/python.md#install) · [MCP: connect a client](../sdks/mcp.md#connect-a-client) · [which one to use](../sdks/overview.md#which-one-to-use)

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

- The images, ports and healthchecks: [Docker](docker.md#running)

Optional compose profiles, **naming the services** so compose does not also build and start the `backend` and `frontend` containers, which would take ports 8000 and 5173 from `make dev`:

```bash
docker compose --profile storage up -d minio                     # MinIO, for S3-backed payloads
docker compose --profile observability up -d prometheus grafana  # Prometheus and Grafana
```

- **Neither is needed.** Payload storage defaults to the filesystem, which is why `make dev` needs no extra services
- **MinIO from a host process:** set `STORAGE_BACKEND=s3`; the `.env.example` S3 values (`http://localhost:9000`, `serpflow` / `serpflow-secret`) already match the container ([object storage](../architecture/caching.md#object-storage))
- **Prometheus scrapes `backend:8000`**, the container ([`docker/prometheus/prometheus.yml`](../../docker/prometheus/prometheus.yml)), so with `make dev` on the host it has no target. Read `http://localhost:8000/metrics` directly, or run the full stack ([observability](../operations/observability.md#metrics))

## Everyday targets

```bash
make help            # the list, generated from the ## comments in the Makefile

make backend         # API only
make frontend        # frontend only
make worker          # Kafka consumers on their own
make mcp             # MCP server over stdio

make test            # whole suite (236 tests)
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

make docs-check      # every link, path and anchor resolves; every doc page is cross-linked
make docs-nav        # regenerate doc badges, breadcrumbs, prev/next links and the docs browser order
```

- **`make help` does not list `test-e2e`:** its pattern, `^[a-zA-Z_-]+:`, skips target names that contain a digit. The target itself works
- **`ARGS=` passes flags through** to the targets that take them, for example `make seed ARGS=--reset`

**Every target in the [`Makefile`](../../Makefile)**, and where it is explained:

| Target | What it runs | More |
| --- | --- | --- |
| `help` | lists the targets that carry a `##` comment | |
| `install` | `install-backend`, then `install-frontend` | [installation: path A](installation.md#path-a-developer-install) |
| `install-backend` | `uv venv --python 3.13 .venv` and an editable `uv pip install -e ".[dev]"` in `backend/` | [CLI: install](../sdks/cli.md#install) · [Python SDK: install](../sdks/python.md#install) |
| `install-frontend` | `npm install` in `frontend/` | [frontend](../architecture/frontend.md#structure) |
| `dev` | `backend` and `frontend` in parallel (`make -j2`) | [first run](#first-run) |
| `backend` | `python -m app.server --reload` on `0.0.0.0:8000` | [async on Windows](../architecture/backend.md#async-on-windows) |
| `frontend` | `npm run dev`: Vite on 5173, proxying `/v1`, `/healthz`, `/readyz`, `/metrics` to the API | [frontend](../architecture/frontend.md) |
| `worker` | `python -m app.workers.runner`: ensures the topics, then runs every consumer | [Kafka: running consumers](../operations/kafka.md#running-consumers) |
| `mcp` | `python -m app.mcp.server`, stdio; needs `SERPFLOW_API_KEY` in the shell | [MCP server](../sdks/mcp.md#run-it) |
| `up` | `docker compose up -d postgres redis kafka` | [what is running](#what-is-running) |
| `down` | `docker compose down`: stops the containers, keeps the volumes | [Docker: volumes](docker.md#volumes) |
| `restart` | `docker compose restart` | [Docker: running](docker.md#running) |
| `logs` | `docker compose logs -f --tail=120` | [observability: logging](../operations/observability.md#logging) |
| `ps` | `docker compose ps` | [Docker: healthchecks](docker.md#healthchecks-and-ordering) |
| `upgrade` | `alembic upgrade head` | [migrations: commands](../database/migrations.md#commands) |
| `migrate` | alias for `upgrade` | [migrations: commands](../database/migrations.md#commands) |
| `migration` | `alembic revision --autogenerate $(ARGS)`, e.g. `ARGS="-m 'message'"` | [writing a new revision](../database/migrations.md#writing-a-new-revision) |
| `downgrade` | `alembic downgrade -1` | [migrations: commands](../database/migrations.md#commands) |
| `seed` | `backend/scripts/seed.py`; `ARGS=--reset` or `ARGS=--if-absent` | [seeding by hand](../operations/bootstrap.md#seeding-by-hand) |
| `demo` | `backend/scripts/demo.py`; `ARGS=--reset-cache` invalidates first | [the reference demo](../product/demo.md#reproducing-from-a-clean-state) |
| `psql` | `psql -U serpflow -d serpflow` in the postgres container | [schema](../database/schema.md) · [RLS: verifying it](../database/rls.md#verifying-it) |
| `redis-cli` | `redis-cli` in the redis container | [Redis: inspecting](../operations/redis.md#inspecting) |
| `kafka-topics` | `python -m app.workers.topics`: creates the 8 topics, 3 partitions each, if missing | [Kafka: topics](../operations/kafka.md#topics) |
| `api-reference` | `scripts/generate_api_reference.py`: rewrites `frontend/src/lib/api-reference.generated.ts` from the OpenAPI schema; `ARGS=--offline` needs no server | [the API reference](../architecture/web.md#the-api-reference) |
| `docs-check` | `scripts/check_doc_links.py --anchors --interlinks`: every link, repository path and `#anchor` resolves, every page ends with a Related section of 3+ links, and no page is an orphan | [contributing: docs](../../CONTRIBUTING.md#changing-the-docs) |
| `docs-nav` | `scripts/build_docs_nav.py`: rewrites every page's badge header, breadcrumb and prev/next footer, and `frontend/src/lib/docs-order.generated.ts`, the docs browser's sidebar and pager order | [the documentation browser](../architecture/web.md#the-documentation-browser) |
| `api-check` | `scripts/check_api.py`: calls every operation against a running instance; `ARGS=--verbose` lists the skips | [checking every operation](../api/overview.md#checking-every-operation) |
| `catalog-build` | `backend/scripts/catalog_build.py`: regenerates catalog drafts from the SerpApi docs; `ARGS=--diff` | [how the catalog is authored](../architecture/catalog.md#how-the-catalog-is-authored) |
| `catalog-validate` | `serpflow catalog validate`: lints the committed catalog | [how the catalog is authored](../architecture/catalog.md#how-the-catalog-is-authored) |
| `benchmark` | `serpflow benchmark compare`: real LLM calls with `LLM_PROVIDER=groq` (the default adapter makes none), on demand only | [benchmark: running it](../product/benchmark.md#running-it) |
| `test` | `pytest -q` in `backend/`: 236 tests | [contributing: tests](../../CONTRIBUTING.md#tests) |
| `test-unit` | `pytest tests/unit`: 208 tests, no services | [contributing: tests](../../CONTRIBUTING.md#tests) |
| `test-integration` | `pytest tests/integration`: 25 tests, needs PostgreSQL and Redis | [skipped integration tests](../operations/troubleshooting.md#integration-tests-all-report-skipped) |
| `test-e2e` | `pytest tests/e2e`: 3 tests, including the thesis assertion | [the same assertion in CI](../product/demo.md#the-same-assertion-in-ci) |
| `test-ui` | `frontend/scripts/verify-ui.mjs`: builds, serves `vite preview` on 4178, checks every public page in Chrome | [verifying the web surface](../architecture/web.md#verifying-it) |
| `lint` | `ruff check` and `npm run lint` (eslint, zero warnings) | [contributing: before a pull request](../../CONTRIBUTING.md#before-you-open-a-pull-request) |
| `format` | `ruff format`, `ruff check --fix`, `npm run format` (prettier) | [contributing: style](../../CONTRIBUTING.md#style) |
| `typecheck` | `mypy app` and `npm run typecheck` (`tsc -b --noEmit`) | [contributing: before a pull request](../../CONTRIBUTING.md#before-you-open-a-pull-request) |
| `build` | `npm run build`: `tsc -b && vite build` into `dist/` in `frontend/` | [frontend](../architecture/frontend.md) |
| `docker-build` | `docker compose build`: the backend and frontend images | [Docker: building](docker.md#building) |
| `docker-up` | `docker compose up -d --build`: the full stack | [installation: path B](installation.md#path-b-everything-in-docker) |
| `docker-down` | `docker compose down -v`: stops the stack **and deletes the volumes** | [Docker: volumes](docker.md#volumes) |
| `health` | `serpflow health`: calls `/readyz` at `SERPFLOW_BASE_URL` | [CLI: health](../sdks/cli.md#serpflow-health) · [observability: health](../operations/observability.md#health) |
| `shell` | a Python REPL in `backend/`, with `app` importable | |
| `clean` | removes `__pycache__`, the pytest / ruff / mypy caches, the frontend's `dist/` and `.vite/`, and the backend's filesystem object store (`.serpflow-objects/`); leaves the venv, `node_modules` and volumes | [resetting](#resetting) |

## Modes

- [`SERPFLOW_MODE`](../security/secrets.md#inventory) **defaults to `replay`:** cassettes only. A miss raises [`REPLAY_CASSETTE_MISS`](../operations/troubleshooting.md#replay_cassette_miss) instead of silently reaching the network

```
live     normal billable execution against SerpApi
record   execute live and persist cassettes to fixtures/cassettes/ (CASSETTE_DIR, relative to backend/)
replay   serve from cassettes only, fail loudly on a miss
```

- **No cassettes are committed**, so on a fresh checkout every live-key search in `replay` misses until you have recorded it
- **A `test` API key routes to the deterministic mock regardless of this setting**
  - that precedence is absolute and cannot be overridden
  - it is what makes it safe to develop against a repository with a live key in its `.env`
- `SERPFLOW_MODE` is only the **instance default**. A project can set its own mode, and a single search can override it: see [execution modes](../product/execution-modes.md#who-chooses-and-precedence)

## Using real keys

- **SerpFlow is [bring-your-own-key](../security/byok.md):** both upstream keys belong to the organization, not the deployment
- **There is no `SERPAPI_API_KEY` setting.** If your `.env` has one, it is ignored ([troubleshooting](../operations/troubleshooting.md#a-serpapi_api_key-in-env-does-nothing)). Nothing falls back to a key held by the instance
- **To execute real searches**, attach your SerpApi key in the console under Settings → Credentials, or over the API
  - **this needs `credential:write`**, which only the owner and admin roles carry. The seeded API keys are `developer` keys and get a `403`, so sign in as the owner for a token:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "owner@serpflow.dev", "password": "serpflow-demo-2026"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/v1/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My SerpApi account", "api_key": "...", "set_as_org_default": true}'
```

- **`set_as_org_default: true` matters in the demo org.** Its default credential is a seeded placeholder, and a new key only becomes the default by itself when none is set ([how a key is chosen](../security/byok.md#how-a-key-is-chosen-for-a-request)). The console sends it for SerpApi keys
- The key is validated on arrival with one call that spends nothing, then [encrypted](../security/credentials.md#envelope-encryption)
- Then set the project's mode to `live` and use an `sf_live_...` key
- **For model-driven planning**, attach a Groq key the same way, with `"provider": "groq"`
  - planning calls Groq, not SerpApi: it costs Groq tokens and **zero** SerpApi credits
- **The two variables below are a self-hosting fallback**, used only when an organization has brought no Groq key of its own ([the self-hosting exception](../security/byok.md#the-self-hosting-exception))

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

- If [marginal-cost replanning](../architecture/marginal-replanning.md) did **not** change the selected plan, the script exits non-zero and says so ([troubleshooting](../operations/troubleshooting.md#make-demo-exits-non-zero))
- A cache hit on the same plan is **not** accepted as a pass

```
  PROVEN: cache-aware marginal-cost replanning changed the selected plan.
```

- **Run it again with `make demo ARGS=--reset-cache`:** without it, phase 1 may find entries an earlier run left warm ([phase 1 says "3 of 3 steps warm"](../operations/troubleshooting.md#phase-1-says-3-of-3-steps-warm))
- Walkthrough: [the reference demo](../product/demo.md) · why it ranks on marginal cost: [marginal-cost replanning](../architecture/marginal-replanning.md)

## Resetting

```bash
make seed ARGS=--reset              # delete the demo org, recreate it, print fresh keys
docker compose down -v && make up   # drop volumes and start from nothing
make upgrade && make seed           # then rebuild the schema and the data
make clean                          # caches, build artefacts and the local payload store
```

- **`make clean` also deletes `.serpflow-objects/`** in `backend/`, the filesystem payload store, while the cache index in PostgreSQL still points at it
  - `lookup` treats a missing payload as a miss rather than failing the run ([`app/services/cache/service.py`](../../backend/app/services/cache/service.py)), but `inspect` reads only the index, so planning still prices those entries as warm
  - follow it with a cache invalidation or a volume reset ([invalidation](../architecture/caching.md#invalidation))
- Schema-only resets: [migrations: resetting](../database/migrations.md#resetting)

## Troubleshooting

A dedicated page covers the common failures: [operations/troubleshooting](../operations/troubleshooting.md). The two that catch people most often:

- **psycopg and the Windows event loop** ([troubleshooting](../operations/troubleshooting.md#psycopg-fails-on-windows-proactoreventloop))
  - psycopg's async implementation cannot run on `ProactorEventLoop`
  - uvicorn 0.54 picks that loop itself for single-process runs, ignoring the policy
  - [`app/server.py`](../../backend/app/server.py) exists to pass an explicit `loop_factory`, which is why `make backend` runs `python -m app.server` and not `uvicorn app.main:app` ([async on Windows](../architecture/backend.md#async-on-windows))
- **Kafka not ready yet** ([`kafka.degraded` in the logs](../operations/troubleshooting.md#kafkadegraded-in-the-logs))
  - the broker takes a few seconds to form its KRaft quorum
  - `/readyz` reports it as degraded rather than failing, because Kafka only carries background work

## Related

- [Installation](installation.md): per-OS prerequisites, the Docker path, and how to verify an install
- [Docker](docker.md): what `make up` starts, and how the full container stack differs
- [Production](production.md): what changes once the instance is not a laptop
- [Startup bootstrap](../operations/bootstrap.md): why `make dev` migrates and seeds on its own
- [SDKs and tools](../sdks/overview.md): the CLI, Python SDK, TypeScript SDK and MCP server, and how they are configured
- [Execution modes](../product/execution-modes.md): live, record, replay and mock, and who chooses
- [Troubleshooting](../operations/troubleshooting.md): every failure above, with its fix

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Installation](../deployment/installation.md) | [Docs index](../README.md) · [Deployment index](../deployment/README.md) | [Docker](../deployment/docker.md) |
