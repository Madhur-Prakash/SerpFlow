# Installation

<p>
  <a href="../README.md#deployment"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="API keys: not required" src="https://img.shields.io/badge/API%20keys-not%20required-3fcf8e">
  <img alt="paths: dev · docker" src="https://img.shields.io/badge/paths-dev%20%C2%B7%20docker-2496ED">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="uv: venv" src="https://img.shields.io/badge/uv-venv-DE5FE9?logo=uv&logoColor=white">
  <img alt="Node: 22" src="https://img.shields.io/badge/Node-22-5FA04E?logo=nodedotjs&logoColor=white">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <a href="../../backend/pyproject.toml"><img alt="source: backend/pyproject.toml" src="https://img.shields.io/badge/source-backend%2Fpyproject.toml-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 10 min" src="https://img.shields.io/badge/read-10%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../README.md#deployment) › **Installation** · page 6 of 57

**From a blank machine to a running, verified SerpFlow**, with every command. No API keys are needed at any step.

> **Looking for a hosted version? There isn't one yet.** SerpFlow is self-hosted by the author's decision; the author will host it once enough people ask. To ask, open a GitHub issue: [hosting](../../README.md#hosting).

| Path | Pick it when | Time |
| --- | --- | --- |
| [**A. Developer install**](#path-a-developer-install) | you will change the code | ~10 min |
| [**B. Everything in Docker**](#path-b-everything-in-docker) | you only want to run it | ~5 min |

Then: [verify it](#verify-the-install) · [without make](#without-make) · [uninstall](#uninstall) · [if something fails](#if-something-fails)

## 1. Prerequisites

| Tool | Version | Needed for | Check |
| --- | --- | --- | --- |
| Git | any | cloning | `git --version` |
| Docker + Compose v2 | Compose 2.24+ | PostgreSQL, Redis, Kafka (and the full stack in path B): [Docker](docker.md) | `docker compose version` |
| GNU Make | any | the documented entry point: [every target](local.md#everyday-targets) | `make --version` |
| uv | latest | path A: the Python 3.13 venv | `uv --version` |
| Node.js | 20+ (22 recommended) | path A: the frontend | `node --version` |
| Google Chrome | stable | optional: [`make test-ui`](../architecture/web.md#verifying-it) only | `google-chrome --version` |

- **Python itself is not a prerequisite:** `uv` downloads a managed Python 3.13 if the machine does not have one. The backend requires 3.13 or later ([`backend/pyproject.toml`](../../backend/pyproject.toml))
- **Compose 2.24+** is only strictly needed for the `!reset` / `!override` tags in the [server port lockdown](deployment-guide.md#5-lock-down-the-ports); any Compose v2 runs the laptop stack
- **Memory:** plan for **8 GB+**. Kafka's JVM, PostgreSQL and the Docker Desktop VM add up; 16 GB is comfortable
- `uv` installed but not found? [Troubleshooting: `uv: command not found`](../operations/troubleshooting.md#uv-command-not-found)

### Linux (Ubuntu / Debian)

```bash
sudo apt-get update && sudo apt-get install -y git make curl ca-certificates

# Docker Engine + Compose plugin (or install Docker Desktop instead)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"     # then log out and back in

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js 22 via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
nvm install 22
```

### macOS

```bash
xcode-select --install          # git and make
brew install uv node
brew install --cask docker      # Docker Desktop; start it once from Applications
```

### Windows

- **Recommended: WSL2** with Ubuntu, then follow the Linux steps inside it, plus Docker Desktop with WSL integration enabled
- **Or native**, from Git Bash:

```powershell
winget install Git.Git Docker.DockerDesktop astral-sh.uv OpenJS.NodeJS.LTS GnuWin32.Make
```

- The [`Makefile`](../../Makefile) finds `backend/.venv/Scripts/python.exe` as well as `bin/python`, so the venv works either way
- **Run `make` from Git Bash or WSL**, not PowerShell or `cmd`: the Makefile sets `SHELL := /bin/bash`. See [troubleshooting: `make` fails on Windows](../operations/troubleshooting.md#make-fails-on-windows)
- **Never copy a checkout between Windows and Linux or macOS.** The venv and `node_modules` contain platform binaries. See [troubleshooting](../operations/troubleshooting.md#copied-a-checkout-from-windows)

## 2. Get the code

```bash
git clone https://github.com/Madhur-Prakash/SerpFlow.git
cd SerpFlow
```

- **The directory is `SerpFlow`, capitalised.** Linux paths are case-sensitive (as is a case-sensitive macOS volume), so `cd serpflow` fails there

## 3. Configure

```bash
cp .env.example .env
```

- **Nothing needs editing to get started.** The defaults in [`.env.example`](../../.env.example) are safe for a laptop. Every variable is listed in [secrets: inventory](../security/secrets.md#inventory) and read by [`app/core/config.py`](../../backend/app/core/config.py):

| Setting | Default | Meaning |
| --- | --- | --- |
| `SERPFLOW_MODE` | `replay` | cassettes only; never reaches the network. See [execution modes](../product/execution-modes.md) |
| `LLM_PROVIDER` | `mock` | the [deterministic mock adapter](../architecture/planner.md#stage-b-select); no Groq key needed |
| `STORAGE_BACKEND` | `filesystem` | payloads on disk; no MinIO needed. See [object storage](../architecture/caching.md#object-storage) |
| `RUN_MIGRATIONS_ON_STARTUP` / `SEED_ON_STARTUP` | `true` | the API [migrates and seeds itself on start](../operations/bootstrap.md): in the container (path B), and under `make dev` too (path A), because the API reads this `.env`. The code default is `false` |
| `GMAIL_CREDENTIALS_B64` | empty | emails are not sent; the log notes each one, without its link. See [email: console](../operations/email.md#console) |

- **Do not add a `SERPAPI_API_KEY`:** there is no such setting. Keys are brought per organization. See [BYOK](../security/byok.md) and [troubleshooting](../operations/troubleshooting.md#a-serpapi_api_key-in-env-does-nothing)
- **`.env` is for the API and compose only.** The `serpflow` CLI, the Python SDK and the MCP server read `SERPFLOW_API_KEY` / `SERPFLOW_BASE_URL` / `SERPFLOW_MCP_SESSION` from the **shell**: see [local development: CLI, SDK and MCP](local.md#cli-sdk-and-mcp)
- **`.env` is gitignored.** Keep it that way

## Path A: developer install

```bash
make install        # 1. backend venv (Python 3.13) + deps, then frontend npm install
make up             # 2. postgres, redis, kafka in Docker
make upgrade        # 3. apply the four Alembic migrations
make seed           # 4. catalog, 120 benchmark tasks, demo org, accounts and API keys
make dev            # 5. API on :8000 and the frontend on :5173, with reload
```

What each step does:

1. **`make install`** (`install-backend`, then `install-frontend`)
   - `cd backend && uv venv --python 3.13 .venv`
   - `uv pip install --python .venv -e ".[dev]"`: an **editable** install, which is also what makes the `serpflow` CLI and `from serpflow import ...` work ([Python SDK: install](../sdks/python.md#install))
   - `npm install` in `frontend/`
2. **`make up`** starts the three dependencies and waits for nothing. Check them with `make ps`: all three have healthchecks, and Kafka is the last to show `healthy` (its `start_period` is 30 s)
3. **`make upgrade`** runs `alembic upgrade head`: [migrations](../database/migrations.md#the-revision-chain)
4. **`make seed`** prints two sign-in accounts and four API keys, **once**. Copy them now
   - **Keys are printed only when the seed creates the demo organization.** If it already exists (a second run, or `make dev` started first and the [startup bootstrap](../operations/bootstrap.md) seeded it), it says so and prints none: run `make seed ARGS=--reset` for fresh keys ([seeding by hand](../operations/bootstrap.md#seeding-by-hand))
5. **`make dev`** runs `make backend` and `make frontend` together. `Ctrl+C` stops both
   - the API starts through `python -m app.server`, not `uvicorn` directly: [ADR 0013](../adr/0013-explicit-event-loop-factory.md)

| Open | What |
| --- | --- |
| http://localhost:5173 | the web app: landing page, docs, console at `/app` ([routes](../architecture/frontend.md#routes)) |
| http://localhost:8000/docs | interactive OpenAPI (Swagger): [API overview](../api/overview.md) |
| http://localhost:8000/readyz | readiness of every dependency: [health](../operations/observability.md#health) |

## Path B: everything in Docker

```bash
cp .env.example .env
docker compose up -d --build     # or: make docker-up
docker compose ps                # wait until backend shows (healthy)
```

- **The backend is self-bootstrapping:** on first start it migrates and seeds, under a PostgreSQL advisory lock ([bootstrap](../operations/bootstrap.md#1-an-advisory-lock))
- **Sign in** at http://localhost:5173 with the demo owner: `owner@serpflow.dev` / `serpflow-demo-2026`
  - a published, local-only password. Seeding is refused once `ENVIRONMENT` is `staging` or `production` ([the environment refusal](../operations/bootstrap.md#3-an-environment-refusal))
- **API keys are only printed by the seed script**, not by the startup bootstrap. To get a fresh set:

```bash
docker compose exec backend python scripts/seed.py --reset   # re-creates the demo org, prints its keys
```

- Or create one in the console under **Settings → API keys** ([API keys](../security/api-keys.md))

| Open | What |
| --- | --- |
| http://localhost:5173 | the web app (nginx), proxying the API |
| http://localhost:8000/docs | the API directly |

- **Compose's default `VITE_API_BASE_URL` is `http://localhost:8000`**, so the bundle's REST calls go to `:8000` directly (allowed by `CORS_ORIGINS`) while the SSE stream goes through nginx: [Docker: the frontend image](docker.md#the-frontend-image)
- **Optional profiles** ([Docker: running](docker.md#running)):

```bash
docker compose --profile observability up -d   # + Prometheus :9090, Grafana :3001
docker compose --profile storage up -d         # + MinIO :9000 / console :9001
```

## Verify the install

Run these in order. Each one is a stronger claim than the last.

```bash
curl -s localhost:8000/healthz          # the process is up
curl -s localhost:8000/readyz           # postgres, redis, kafka, object_storage, catalog all "ok"
make health                             # the same, from the CLI

make test-unit                          # 208 tests, no services needed
make test                               # 236 tests: 208 unit + 25 integration + 3 e2e
make demo                               # prints PROVEN, exits 0
make api-check                          # calls every API operation: 0 failed
make test-ui                            # every public page in Chrome, both themes
```

| Command | Pass looks like |
| --- | --- |
| `/readyz` | `"status":"ok"` and every check `ok`; catalog shows `"engines": 54`, `"edges": 30`, `"substitutes": 69`, `"capability_tags": 28` |
| `make test` | `236 passed`. Run `pytest -rs` from `backend/` to confirm no integration test [skipped for lack of Postgres](../operations/troubleshooting.md#integration-tests-all-report-skipped) |
| `make demo` | `PROVEN: cache-aware marginal-cost replanning changed the selected plan.` ([the reference demo](../product/demo.md)) |
| `make api-check` | `failed 0`, and `/metrics ok`, `/readyz ok`. `ARGS=--verbose` lists each skip with its reason ([checking every operation](../api/overview.md#checking-every-operation)) |
| `make test-ui` | `All pages render in both themes.` and `No horizontal overflow at any tested width.` ([verifying the web surface](../architecture/web.md#verifying-it)) |

- **`make health` runs the `serpflow` CLI**, which reads `SERPFLOW_BASE_URL` from the shell (default `http://localhost:8000`), not from `.env`: [CLI](../sdks/cli.md#serpflow-health)
- **`/readyz` is `degraded`, not `error`, while Kafka forms its quorum** or Redis is down; only an unreachable PostgreSQL returns `503`
- **Path B users:** run the `make` checks from a developer install, or call the endpoints with `curl`. `make demo` also runs inside the container:

```bash
docker compose exec backend python scripts/demo.py
```

## Without make

| `make` target | Equivalent |
| --- | --- |
| `install` | `cd backend && uv venv --python 3.13 .venv && uv pip install --python .venv -e ".[dev]"`, then `cd frontend && npm install` |
| `up` | `docker compose up -d postgres redis kafka` |
| `upgrade` | `cd backend && .venv/bin/python -m alembic upgrade head` |
| `seed` | `cd backend && .venv/bin/python scripts/seed.py` |
| `backend` | `cd backend && .venv/bin/python -m app.server --reload --host 0.0.0.0 --port 8000` |
| `frontend` | `cd frontend && npm run dev` |
| `demo` | `cd backend && .venv/bin/python scripts/demo.py` |
| `test` | `cd backend && .venv/bin/python -m pytest -q` |
| `health` | `cd backend && .venv/bin/python -m app.cli.main health` |
| `test-ui` | `cd frontend && node scripts/verify-ui.mjs` |
| `docker-up` | `docker compose up -d --build` |

- On Windows, replace `.venv/bin/python` with `.venv/Scripts/python.exe`
- The full target list, with what each one does: [local development: everyday targets](local.md#everyday-targets)

## Optional: real searches

Not needed for anything above. When you want live SerpApi results:

1. Sign in as the owner, go to **Settings → Credentials**, and add your **SerpApi** key
   - the console makes a SerpApi key the **organization default**, which matters: the seeded demo org's default is a placeholder that is never validated ([`app/db/seed.py`](../../backend/app/db/seed.py))
2. Optionally add a **Groq** key the same way, for model-driven planning
3. Set the project's execution mode to `live` (**Settings → Projects**): [setting it](../product/execution-modes.md#setting-it)
4. Use the `sf_live_...` key that `make seed` printed
   - an `sf_test_...` key **always** returns mock results, whatever the mode: [ADR 0010](../adr/0010-test-key-mode-precedence.md)

- Details: [bring your own key](../security/byok.md) · [execution modes](../product/execution-modes.md) · [using real keys locally](local.md#using-real-keys)

## Uninstall

```bash
make down                    # stop the containers, keep the data
make docker-down             # stop everything AND delete the volumes
make clean                   # caches, build artefacts and the local payload store
rm -rf backend/.venv frontend/node_modules
```

- **`make docker-up` also built two images.** Remove them with `docker compose down -v --rmi local`, which deletes images that have no custom tag

## If something fails

| Symptom | Fix |
| --- | --- |
| `port is already allocated` | another service holds 5432/6379/9092/8000/5173. Set `POSTGRES_PORT`, `BACKEND_PORT` etc. in `.env`. For path A, change the matching `DATABASE_URL` / `REDIS_URL` too. **`KAFKA_PORT` cannot move on its own:** the broker still advertises `localhost:9092` ([Docker: Kafka](docker.md#kafka)) |
| `connection refused` on 5432 | PostgreSQL is still running initdb: [troubleshooting](../operations/troubleshooting.md#connection-refused-on-5432) |
| `/readyz` shows kafka `degraded` | wait 20-30 s for the KRaft quorum; Kafka only carries background work ([`kafka.degraded`](../operations/troubleshooting.md#kafkadegraded-in-the-logs)) |
| `make seed` prints no keys | the demo org already exists: `make seed ARGS=--reset` ([seeding by hand](../operations/bootstrap.md#seeding-by-hand)) |
| `REPLAY_CASSETTE_MISS` | expected in `replay` mode with a live key: no cassettes are committed. Use a `test` key, or record the cassette ([troubleshooting](../operations/troubleshooting.md#replay_cassette_miss)) |
| integration tests all `skipped` | Postgres is not reachable from the test process: `make up`, then re-run ([troubleshooting](../operations/troubleshooting.md#integration-tests-all-report-skipped)) |
| `make test-ui` cannot launch | install Google Chrome; the checks launch Playwright's `chrome` channel ([troubleshooting](../operations/troubleshooting.md#make-test-ui-cannot-launch-a-browser)) |
| Docker Desktop quits mid-run | out of memory: close heavy apps, or raise Docker Desktop's memory limit ([troubleshooting](../operations/troubleshooting.md#docker-desktop-quits-mid-run)) |

- Everything else: [troubleshooting](../operations/troubleshooting.md)

## Related

- [Local development](local.md): every `make` target, modes, real keys, and the CLI / SDK / MCP environment
- [Docker](docker.md): what path B builds, the profiles, and the port overrides
- [Deployment guide](deployment-guide.md): putting it on a server, with real secrets and TLS
- [Startup bootstrap](../operations/bootstrap.md): why the API migrates and seeds itself, and why it refuses to seed in production
- [Secrets](../security/secrets.md): what the `.env.example` defaults are, and why they are safe only on a laptop
- [SDKs and tools](../sdks/overview.md): the CLI, Python SDK and MCP server this install also provides
- [Troubleshooting: setup](../operations/troubleshooting.md#setup): Windows, `uv` and packaging failures

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Glossary](../product/glossary.md) | [Docs index](../README.md) | [Local development](../deployment/local.md) |
