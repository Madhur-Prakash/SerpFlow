# Installation

<p>
  <a href="../README.md#deployment"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="API keys: not required" src="https://img.shields.io/badge/API%20keys-not%20required-3fcf8e">
  <img alt="paths: dev · docker" src="https://img.shields.io/badge/paths-dev%20%C2%B7%20docker-2496ED">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="uv: venv" src="https://img.shields.io/badge/uv-venv-DE5FE9?logo=uv&logoColor=white">
  <img alt="Node: 22" src="https://img.shields.io/badge/Node-22-5FA04E?logo=nodedotjs&logoColor=white">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../README.md#deployment) › **Installation** · page 5 of 50

**From a blank machine to a running, verified SerpFlow**, with every command. No API keys are needed at any step.

| Path | Pick it when | Time |
| --- | --- | --- |
| [**A. Developer install**](#path-a-developer-install) | you will change the code | ~10 min |
| [**B. Everything in Docker**](#path-b-everything-in-docker) | you only want to run it | ~5 min |

Then: [verify it](#verify-the-install) · [without make](#without-make) · [uninstall](#uninstall) · [if something fails](#if-something-fails)

## 1. Prerequisites

| Tool | Version | Needed for | Check |
| --- | --- | --- | --- |
| Git | any | cloning | `git --version` |
| Docker + Compose v2 | Compose 2.24+ | PostgreSQL, Redis, Kafka (and the full stack in path B) | `docker compose version` |
| GNU Make | any | the documented entry point | `make --version` |
| uv | latest | path A: the Python 3.13 venv | `uv --version` |
| Node.js | 20+ (22 recommended) | path A: the frontend | `node --version` |
| Google Chrome | stable | optional: `make test-ui` only | `google-chrome --version` |

- **Python itself is not a prerequisite:** `uv` downloads a managed Python 3.13 if the machine does not have one
- **Memory:** plan for **8 GB+**. Kafka's JVM, PostgreSQL and the Docker Desktop VM add up; 16 GB is comfortable

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

- The Makefile finds `backend/.venv/Scripts/python.exe` as well as `bin/python`, so the venv works either way
- **Never copy a checkout between Windows and Linux or macOS.** The venv and `node_modules` contain platform binaries. See [troubleshooting](../operations/troubleshooting.md#copied-a-checkout-from-windows)

## 2. Get the code

```bash
git clone https://github.com/serpflow/serpflow.git
cd serpflow
```

## 3. Configure

```bash
cp .env.example .env
```

- **Nothing needs editing to get started.** The defaults are safe for a laptop:

| Setting | Default | Meaning |
| --- | --- | --- |
| `SERPFLOW_MODE` | `replay` | cassettes only; never reaches the network |
| `LLM_PROVIDER` | `mock` | the deterministic planner; no Groq key needed |
| `STORAGE_BACKEND` | `filesystem` | payloads on disk; no MinIO needed |
| `RUN_MIGRATIONS_ON_STARTUP` / `SEED_ON_STARTUP` | `true` | the container bootstraps itself (path B) |
| `GMAIL_CREDENTIALS_B64` | empty | emails are not sent; the log notes each one, without its link |

- **Do not add a `SERPAPI_API_KEY`:** there is no such setting. Keys are brought per organization. See [BYOK](../security/byok.md)
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

1. **`make install`**
   - `uv venv --python 3.13 backend/.venv`
   - `uv pip install -e "backend[dev]"`
   - `npm install` in `frontend/`
2. **`make up`** starts the three dependencies and waits for nothing. Check them with `make ps`: postgres and redis should show `healthy`
3. **`make upgrade`** runs `alembic upgrade head`
4. **`make seed`** prints two sign-in accounts and four API keys, **once**. Copy them now
5. **`make dev`** runs `make backend` and `make frontend` together. `Ctrl+C` stops both

| Open | What |
| --- | --- |
| http://localhost:5173 | the web app: landing page, docs, console at `/app` |
| http://localhost:8000/docs | interactive OpenAPI (Swagger) |
| http://localhost:8000/readyz | readiness of every dependency |

## Path B: everything in Docker

```bash
cp .env.example .env
docker compose up -d --build     # or: make docker-up
docker compose ps                # wait until backend shows (healthy)
```

- **The backend is self-bootstrapping:** on first start it migrates and seeds, under a PostgreSQL advisory lock
- **Sign in** at http://localhost:5173 with the demo owner: `owner@serpflow.dev` / `serpflow-demo-2026`
  - a published, local-only password. Seeding is refused once `ENVIRONMENT` is `staging` or `production`
- **API keys are only printed by the seed script**, not by the startup bootstrap. To get a fresh set:

```bash
docker compose exec backend python scripts/seed.py --reset   # re-creates the demo org, prints its keys
```

- Or create one in the console under **Settings → API keys**

| Open | What |
| --- | --- |
| http://localhost:5173 | the web app (nginx), proxying the API |
| http://localhost:8000/docs | the API directly |

- **Optional profiles:**

```bash
docker compose --profile observability up -d   # + Prometheus :9090, Grafana :3001
docker compose --profile storage up -d         # + MinIO :9000 / console :9001
```

## Verify the install

Run these in order. Each one is a stronger claim than the last.

```bash
curl -s localhost:8000/healthz          # the process is up
curl -s localhost:8000/readyz           # postgres, redis, kafka, storage, catalog all "ok"
make health                             # the same, from the CLI

make test-unit                          # 188 tests, no services needed
make test                               # 216 tests: unit + integration + e2e
make demo                               # prints PROVEN, exits 0
make api-check                          # calls every API operation: 0 failed
make test-ui                            # every public page in Chrome, both themes
```

| Command | Pass looks like |
| --- | --- |
| `/readyz` | `"status":"ok"` and every check `ok`; catalog shows 54 engines, 30 edges |
| `make test` | `216 passed`. Run `pytest -rs` to confirm no integration test skipped for lack of Postgres |
| `make demo` | `PROVEN: cache-aware marginal-cost replanning changed the selected plan.` |
| `make api-check` | `failed 0`, with skips listed and explained |
| `make test-ui` | `All pages render in both themes` and `No horizontal overflow` |

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

- On Windows, replace `.venv/bin/python` with `.venv/Scripts/python.exe`

## Optional: real searches

Not needed for anything above. When you want live SerpApi results:

1. Sign in as the owner, go to **Settings → Credentials**, and add your **SerpApi** key
2. Optionally add a **Groq** key the same way, for model-driven planning
3. Set the project's execution mode to `live` (**Settings → Projects**)
4. Use the `sf_live_...` key that `make seed` printed

- Details: [bring your own key](../security/byok.md) · [execution modes](../product/execution-modes.md)

## Uninstall

```bash
make down                    # stop the containers, keep the data
make docker-down             # stop everything AND delete the volumes
make clean                   # caches and build artefacts
rm -rf backend/.venv frontend/node_modules
```

## If something fails

| Symptom | Fix |
| --- | --- |
| `port is already allocated` | another service holds 5432/6379/9092/8000/5173. Set `POSTGRES_PORT`, `BACKEND_PORT` etc. in `.env` |
| `/readyz` shows kafka `degraded` | wait 20-30 s for the KRaft quorum; Kafka only carries background work |
| `REPLAY_CASSETTE_MISS` | expected in `replay` mode for a new query: use a `test` key, or record the cassette |
| integration tests all `skipped` | Postgres is not reachable from the test process: `make up`, then re-run |
| `make test-ui` cannot launch | install Google Chrome; the script uses Playwright's `chrome` channel |
| Docker Desktop quits mid-run | out of memory: close heavy apps, or raise Docker Desktop's memory limit |

- Everything else: [troubleshooting](../operations/troubleshooting.md)

## Next

- [Local development](local.md): everyday targets, modes and keys
- [Deployment guide](deployment-guide.md): putting it on a server

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Routing benchmark](../product/benchmark.md) | [Docs index](../README.md) | [Local development](../deployment/local.md) |
