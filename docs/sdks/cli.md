# CLI

<p>
  <a href="../sdks/README.md"><img alt="docs: SDKs" src="https://img.shields.io/badge/docs-SDKs-8250DF?logo=readthedocs&logoColor=white"></a>
  <img alt="commands: 14" src="https://img.shields.io/badge/commands-14-8250DF">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <a href="../../backend/app/cli/main.py"><img alt="source: cli/main.py" src="https://img.shields.io/badge/source-cli%2Fmain.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [SDKs](../sdks/README.md) › **CLI** · page 31 of 50

- **`serpflow`: fourteen commands** for planning, searching, inspecting runs, exploring the catalog, the cache and the benchmark: [`app/cli/main.py`](../../backend/app/cli/main.py)
- **Built on [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/)**, so plans render as tables and errors as panels
- **Installed with the backend** as a console script, next to `serpflow-mcp`

**On this page:** [install](#install) · [what each command needs](#what-each-command-needs) · [options](#options-shared-by-api-commands) · [plan](#serpflow-plan) · [search](#serpflow-search) · [runs](#serpflow-runs) · [replay](#serpflow-replay) · [catalog](#serpflow-catalog) · [cache](#serpflow-cache) · [benchmark](#serpflow-benchmark) · [health](#serpflow-health) · [version](#serpflow-version) · [exit codes](#exit-codes) · [scripting](#scripting)

## Install

```bash
make install-backend                  # uv venv + editable install of backend/
source backend/.venv/bin/activate     # Windows: backend\.venv\Scripts\activate
serpflow --help
```

- **Without activating:** `.venv/bin/serpflow` inside `backend/` (Windows: `.venv\Scripts\serpflow.exe`), or `python -m app.cli.main` from `backend/`, which is what the Makefile uses
- **Or through uv**, from anywhere: `uv --directory backend run --no-sync serpflow ...`
- **No shell completion is installed** (`add_completion=False`)

```bash
export SERPFLOW_API_KEY=sf_test_...   # make seed prints one
serpflow health
```

## What each command needs

| Command | Needs the API running | Needs an API key | Runs |
| --- | :---: | :---: | --- |
| `plan`, `search`, `runs`, `replay` | ✓ | ✓ | over HTTP |
| `cache stats`, `cache invalidate` | ✓ | ✓ | over HTTP |
| `health` | ✓ | | over HTTP, unauthenticated `/readyz` |
| `catalog explore`, `list`, `paths`, `validate` | | | **in-process**, on the committed catalog YAML |
| `benchmark run`, `compare` | | | **in-process**, against the configured language model |
| `version` | | | in-process |

- **The in-process commands need an installed backend**, but no database, Redis or server

## Options shared by API commands

| Option | Environment | Default |
| --- | --- | --- |
| `--api-key` | `SERPFLOW_API_KEY` | none: exits `2` with a hint |
| `--base-url` | `SERPFLOW_BASE_URL` | `http://localhost:8000` |

- **Options belong to each command**, not to `serpflow` itself: `serpflow plan --base-url https://... "..."`, not `serpflow --base-url ... plan`
- **The HTTP timeout is 120 seconds**

## serpflow plan

```bash
serpflow plan [--budget N] [--project ID] [--json] "INTENT"
```

- **Plans without executing. Spends zero SerpApi credits**
- **Prints:** the steps with fan-out, freshness and cache layer; naive, marginal and saved credits; any full-scale projection; candidate count, catalog version and confidence
- **Then, when they apply:** the single-candidate reason, the marginal-replanning panel when cache state changed the winner, up to six rejected alternatives with their reasons, and every budget reduction with its impact note
- `--json` prints the raw `POST /v1/plan` response instead

```bash
serpflow plan --budget 20 "review rings among Koramangala cafes"
```

## serpflow search

```bash
serpflow search [--budget N] [--project ID] [--json] "INTENT"
```

- **Plans with cache-aware replanning, then executes**
- **Prints:** the intent with a mode badge (`LIVE`, `MOCK`, `REPLAY`, `RECORD`) and the reason for that mode, the plan as above, then the run id, status, credits spent and saved, and up to eight result rows
- `--json` prints the raw `POST /v1/search` response

## serpflow runs

```bash
serpflow runs [--limit 20]
```

- **Recent runs** in the key's project: id, status, mode, naive and marginal cost, credits spent, intent

## serpflow replay

```bash
serpflow replay RUN_ID
```

- **Re-runs a recorded intent against today's cache state**, and prints the new plan with its mode badge

## serpflow catalog

```bash
serpflow catalog list [--tag TAG]
serpflow catalog explore ENGINE
serpflow catalog paths ENGINE [--params q,location]
serpflow catalog validate
```

| Command | Prints |
| --- | --- |
| `list` | every engine, or those with one capability tag: cost, volatility, PII risk, tags, purpose |
| `explore` | one engine: purpose and docs URL, cost, latency, volatility, PII risk, tags, required parameters and what satisfies them, what it produces and feeds, substitutes with their trade-offs, dependencies |
| `paths` | every valid dependency chain that reaches `ENGINE` from the parameters you have, with its cold cost |
| `validate` | catalog stats, then every lint problem. **Exits `1` if there are any** (`make catalog-validate`) |

- **`paths` adds the common query aliases for you** (`q`, `query`, `text`, ...), and `find_loc` and `l` when you pass `location`
- **`explore` exits `1` for an unknown engine; `paths` exits `1` when no path reaches it**

```bash
serpflow catalog paths google_maps_contributor_reviews --params q,location
```

- More: [catalog architecture](../architecture/catalog.md)

## serpflow cache

```bash
serpflow cache stats
serpflow cache invalidate [--engine ENGINE]
```

- **`stats`:** hit rate, entry count, bytes stored, lookups per layer, and entity/numeral guard rejections by reason
- **`invalidate`:** drops the active project's entries, or only one engine's. See [caching](../architecture/caching.md)

## serpflow benchmark

```bash
serpflow benchmark run [--system serpflow|unaided_llm|embedding_only] [--limit N] [--no-write]
serpflow benchmark compare [--limit N]
```

- **Runs the 120 labelled routing tasks** in-process, against the language model the backend is configured with
- **The default, `LLM_PROVIDER=mock`, is the deterministic adapter**, and needs no key
- **With `LLM_PROVIDER=groq` and `GROQ_API_KEY` set, it makes real model calls.** That is why it is on demand only, and not in CI
- **`run`** prints accuracy (overall, engines, parameters, freshness), a per-category table and the failure modes, then writes a report under `backend/fixtures/benchmark/results/` unless you pass `--no-write`
- **`compare`** runs all three systems and **always** writes all three reports (`make benchmark`)
- More: [benchmark](../product/benchmark.md)

## serpflow health

```bash
serpflow health [--base-url URL]
```

- **Calls `GET /readyz`** and prints `OK`, `DEGRADED` or `ERROR`, the version, the execution mode, the catalog version, and each dependency check
- **Exits `1` on `ERROR`** or when the API is unreachable, so it works as a deploy gate (`make health`)

## serpflow version

```bash
serpflow version      # serpflow 1.0.0   catalog v1.0.0
```

- **Prints `app.__version__`** and the version of the catalog this install would load

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | success |
| `1` | the API returned an error (printed as a panel with its code and `request_id`), an unknown engine, no path to an engine, a catalog lint failure, or `health` found an error |
| `2` | no API key, or a usage error from Typer |

## Scripting

```bash
# The plan as JSON, piped into jq
serpflow plan --json --budget 20 "bakeries in Koramangala" | jq '.marginal_cost'

# Fail a CI step when the catalog does not lint
serpflow catalog validate || exit 1
```

- **`--json` is on `plan` and `search` only.** Every other command prints for people
- **Rich writes ANSI colour to a terminal and plain text to a pipe**

## Related

- [SDKs and tools](overview.md#configuration): the environment variables the CLI shares with the SDKs
- [MCP server](mcp.md): the same service layer, for agents instead of terminals
- [Local development](../deployment/local.md#everyday-targets): the Make targets that wrap these commands
- [Catalog](../architecture/catalog.md): what `catalog explore` and `catalog paths` are reading
- [Benchmark](../product/benchmark.md): what `benchmark compare` measures, and the latest results
- [Troubleshooting](../operations/troubleshooting.md): when `serpflow health` says something is wrong
- [Glossary](../product/glossary.md): every term in these pages, defined and linked

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [TypeScript SDK](../sdks/typescript.md) | [Docs index](../README.md) · [SDKs index](../sdks/README.md) | [MCP server](../sdks/mcp.md) |
