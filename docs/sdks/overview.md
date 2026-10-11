# SDKs and tools

<p>
  <a href="../sdks/README.md"><img alt="docs: SDKs" src="https://img.shields.io/badge/docs-SDKs-8250DF?logo=readthedocs&logoColor=white"></a>
  <img alt="surfaces: Python · TypeScript · CLI · MCP" src="https://img.shields.io/badge/surfaces-Python%20%C2%B7%20TypeScript%20%C2%B7%20CLI%20%C2%B7%20MCP-8250DF">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="TypeScript: 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="MCP: server" src="https://img.shields.io/badge/MCP-server-555555">
  <a href="../../backend/app/sdk/__init__.py"><img alt="source: sdk/__init__.py" src="https://img.shields.io/badge/source-sdk%2F____init____.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [SDKs](../sdks/README.md) › **SDKs and tools** · page 28 of 57

- **Four ways to drive SerpFlow from code**, besides calling the [REST API](../api/overview.md) yourself
- **Two of them speak HTTP to a running API.** The CLI mostly does. **The MCP server does not:** it runs the service layer in its own process, against the database
- **All four are version 1.0.0** and live in this repository. **The SDKs are not released yet:** they will be published to npm and PyPI when the author decides to host SerpFlow. If you self-host, install them from a checkout and use them on your own infrastructure ([why](releasing.md#first-who-runs-the-server))
- **SerpFlow is self-hosted, for now, by the author's decision.** There is no public hosted server: every surface here talks to **your own** instance. **The author will host it on demand**, once enough people ask for it in a public GitHub issue: [hosting](../../README.md#hosting)

**On this page:** [the four surfaces](#the-four-surfaces) · [how they connect](#how-they-connect) · [configuration](#configuration) · [test keys](#test-keys) · [which one to use](#which-one-to-use) · [what each can do](#what-each-can-do) · [versions](#versions)

## The four surfaces

| Surface | Start it with | Talks to | Source | Reference |
| --- | --- | --- | --- | --- |
| **Python SDK** | `from serpflow import SerpFlow` | the REST API, over HTTP ([httpx](https://www.python-httpx.org/)) | [`app/sdk/__init__.py`](../../backend/app/sdk/__init__.py) | [Python SDK](python.md) |
| **TypeScript SDK** | `import { SerpFlow } from "@serpflow/sdk"` | the REST API, over `fetch` | [`src/index.ts`](../../sdk/typescript/src/index.ts) | [TypeScript SDK](typescript.md) |
| **CLI** | `serpflow` | the REST API for runs and the cache; the committed catalog and the benchmark harness in-process | [`app/cli/main.py`](../../backend/app/cli/main.py) | [CLI](cli.md) |
| **MCP server** | `serpflow-mcp` | **the database, in-process.** It is not an HTTP client | [`app/mcp/server.py`](../../backend/app/mcp/server.py) | [MCP server](mcp.md) |

- **The Python SDK, the CLI and the MCP server ship together**, in the backend package ([`backend/pyproject.toml`](../../backend/pyproject.toml)). Installing the backend puts `serpflow` and `serpflow-mcp` on the venv's `PATH`
- **The TypeScript SDK is its own npm package**, `@serpflow/sdk`, with no runtime dependencies ([`sdk/typescript/package.json`](../../sdk/typescript/package.json))
- **None of them duplicates planner or executor logic.** The SDKs and the CLI call the API. The MCP server calls [`app/services/runs.py`](../../backend/app/services/runs.py), the same function the API's handlers call

## How they connect

```
 Python SDK ─┐
 TypeScript ─┼── HTTP ──▶  SerpFlow API (:8000) ──▶ services/runs.py ──▶ PostgreSQL, Redis, SerpApi
 CLI ────────┘   X-API-Key                                ▲
   └── catalog, benchmark, version: in-process            │
                                                           │
 MCP client ── stdio ──▶  serpflow-mcp ───────────────────┘
 (Claude, an agent)        same settings as the API, no HTTP hop
```

- **The SDKs and the CLI need the API running** at `SERPFLOW_BASE_URL`
- **The MCP server needs the API's database instead:** the same `DATABASE_URL`, the same `API_KEY_PEPPER`, and a migrated, seeded schema. The API process itself does not have to be up
  - why: an API key is checked by recomputing its HMAC under the pepper. A different pepper means every key is `INVALID_API_KEY`. See [API keys](../security/api-keys.md)

## Configuration

**Variables read from the shell**, not from `.env`. They are listed in [`.env.example`](../../.env.example) so every variable lives in one place, but nothing loads that file into your shell for you.

| Variable | Python SDK | TypeScript SDK | CLI | MCP server | Default |
| --- | :---: | :---: | :---: | :---: | --- |
| `SERPFLOW_API_KEY` | ✓ fallback when `api_key=` is not passed | ✗ pass `apiKey` | ✓ fallback for `--api-key` | ✓ **required** | none |
| `SERPFLOW_BASE_URL` | ✓ read once, **at import** | ✗ pass `baseUrl` | ✓ fallback for `--base-url` | ✗ ignored | `http://localhost:8000` |
| `SERPFLOW_MCP_SESSION` | | | | ✓ names the service session to resume | none |

- **The TypeScript SDK reads no environment at all.** It has to run in a browser, where there is none
- **The MCP server also reads every API setting** (`DATABASE_URL`, `REDIS_URL`, `API_KEY_PEPPER`, `SERPFLOW_MODE` and the rest) the way the API does: from the environment, then `.env` in the working directory, then `../.env`. See [`app/core/config.py`](../../backend/app/core/config.py) and [MCP: configuration](mcp.md#configuration)

```bash
export SERPFLOW_API_KEY=sf_test_...              # make seed prints one
export SERPFLOW_BASE_URL=http://localhost:8000   # only if it is not the default
```

```powershell
$env:SERPFLOW_API_KEY = "sf_test_..."
```

## Test keys

- **A `sf_test_...` key always routes to the deterministic mock**, whatever `SERPFLOW_MODE` says
  - it needs no SerpApi credential
  - it spends zero SerpApi credits
  - the same intent returns the same results, so it is safe in CI
- `make seed` prints four keys. **Use the `test` one** with the SDKs and the CLI, and the `service` one with the MCP server. See [local development](../deployment/local.md#first-run)
- **A `sf_live_...` key honours the project's execution mode** and needs a SerpApi credential in the vault: [bring your own key](../security/byok.md), [execution modes](../product/execution-modes.md)

## Which one to use

| You are | Use | Because |
| --- | --- | --- |
| A Python service or notebook | [Python SDK](python.md) | sync and async clients, typed results |
| A Node, Deno, Bun or browser app | [TypeScript SDK](typescript.md) | no dependencies, streams with `for await` |
| Already calling SerpApi from code | the [SerpApi drop-in](python.md#the-serpapi-drop-in) in either SDK | the call keeps its shape: `get_dict()` / `getJson()` |
| At a terminal | [CLI](cli.md) | rendered plans, rejections and budget reductions |
| An LLM agent (Claude Desktop, Claude Code, any MCP client) | [MCP server](mcp.md) | four tools, and a budget identity of the agent's own |
| Anything else (Go, Rust; a shell script the [CLI](cli.md#scripting) cannot cover) | the [REST API](../api/overview.md) | every surface above is a thin layer over it |

## What each can do

| Capability | Python `SerpFlow` | Python `AsyncSerpFlow` | TypeScript `SerpFlow` | CLI | MCP |
| --- | :---: | :---: | :---: | :---: | :---: |
| Plan only, zero credits | `route` / `plan` | `route` / `plan` | `route` / `plan` | `plan` | `plan` |
| Plan and execute | `search` / `run` | `search` / `run` | `search` / `run` | `search` | `search` |
| Stream stage frames | `stream` | `stream` | `stream` | | |
| Fetch a run | `get_run` | | `getRun` | | |
| Explain a run | `explain` | | `explain` | | `explain` |
| Replay a run | `replay` | | `replay` | `replay` | |
| List runs | `runs(limit, **filters)` | | `runs(limit)` | `runs --limit` | |
| Catalog | `catalog(engine?)` | | `catalog(engine?)` | `catalog explore / list / paths / validate` | `catalog(engine?)` |
| Budgets | `budgets` | | `budgets` | | |
| Cache stats and invalidation | | | | `cache stats / invalidate` | |
| Readiness | `health` | | `health` | `health` | |
| Scope to a project | `project_id=` | `project_id=` | `projectId` | `--project` on `plan` and `search` | the key's project |
| SerpApi drop-in | `SerpApiCompat` | | `SerpApiCompat` | | |
| Error remedies | | | `error.remedy` | printed panel | error text |

- **`AsyncSerpFlow` covers planning, execution and streaming only.** For the inspection calls, use the sync client, or the REST endpoints with your own `httpx.AsyncClient`
- **No surface exposes the per-request `mode` override.** Send `"mode": "live" | "record" | "replay"` to `POST /v1/search` directly; it needs the `run:mode_override` permission. See [execution modes](../product/execution-modes.md)
- **`run` is an alias of `search` in both SDKs.** It calls `POST /v1/search`, not `POST /v1/run`

## Versions

| Surface | Version | Where it is set |
| --- | --- | --- |
| Python SDK, CLI, MCP server | 1.0.0 | `version` in [`backend/pyproject.toml`](../../backend/pyproject.toml) **and** `__version__` in [`app/__init__.py`](../../backend/app/__init__.py) |
| TypeScript SDK | 1.0.0 | `version` in [`sdk/typescript/package.json`](../../sdk/typescript/package.json) |

- **All of them target `/v1` of the API.** A server release that only adds fields needs no SDK release: both SDKs read optional fields with defaults and keep the full payload in `raw`
- **How to cut a release of either SDK:** [releasing](releasing.md)

## Related

- [Python SDK](python.md#install): installing, configuring and calling the Python clients
- [TypeScript SDK](typescript.md#install): the same for Node, Deno, Bun and the browser
- [CLI](cli.md): every `serpflow` command, and which ones need the API running
- [MCP server](mcp.md#connect-a-client): wiring the four tools into Claude Code or Claude Desktop
- [Releasing](releasing.md): publishing both SDKs to npm and PyPI
- [API overview](../api/overview.md#authentication): the HTTP surface every SDK wraps
- [API keys](../security/api-keys.md#test-keys): why a `sf_test_...` key spends nothing
- [SDKs in the repository](../../sdk/README.md): where the source of each SDK lives
- [Glossary](../product/glossary.md): every term in these pages, defined and linked

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [SDKs index](../sdks/README.md) | [Docs index](../README.md) · [SDKs index](../sdks/README.md) | [Python SDK](../sdks/python.md) |
