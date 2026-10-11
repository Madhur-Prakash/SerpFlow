# MCP server

- **`serpflow-mcp` gives an LLM agent four tools:** `plan`, `search`, `explain` and `catalog`: [`app/mcp/server.py`](../../backend/app/mcp/server.py)
- **Stdio transport**, on the official [`mcp`](https://pypi.org/project/mcp/) Python package. It works with 1.x (`FastMCP`) and 2.x (`MCPServer`)
- **It is not an HTTP client of the API.** It runs the same service layer in its own process, against the same database, so it needs the API's settings, not its URL

**On this page:** [how it runs](#how-it-runs) · [configuration](#configuration) · [run it](#run-it) · [connect a client](#connect-a-client) · [tools](#tools) · [sessions and budgets](#sessions-and-budgets) · [errors](#errors) · [logging](#logging) · [troubleshooting](#troubleshooting)

## How it runs

```
 MCP client ── stdio ──▶ serpflow-mcp
                          ├─ resolve SERPFLOW_API_KEY ──▶ PostgreSQL (api_keys, under RLS)
                          ├─ open or resume a service session
                          └─ services/runs.py ──▶ planner, cache, executor ──▶ SerpApi or the mock
```

- **Every tool call opens its own database session**, resolves the key to a full principal (organization, project, role, budget) and sets the tenant for row-level security
- **No planner or executor logic is duplicated.** `plan` and `search` call [`app/services/runs.py`](../../backend/app/services/runs.py), as the REST handlers do
- **The API process does not have to be running.** The database does, migrated and seeded
- **Runs it creates carry `trigger = "mcp"`**, so they are visible in the console and `GET /v1/runs` like any other run

## Configuration

| Variable | Required | What it does |
| --- | :---: | --- |
| `SERPFLOW_API_KEY` | ✓ | the key every call runs under. `make seed` prints a `service` key for this |
| `SERPFLOW_MCP_SESSION` | recommended | names the service session; see [sessions and budgets](#sessions-and-budgets) |
| `DATABASE_URL` | ✓ | **the API's database** |
| `API_KEY_PEPPER` | ✓ in production | **must equal the API's**, or every key is `INVALID_API_KEY` |
| `CREDENTIAL_KEK`, `CREDENTIAL_KEK_ID` | for live runs | decrypt the SerpApi credential in the vault |
| `REDIS_URL`, `SERPFLOW_MODE`, `LLM_PROVIDER`, ... | as the API | the rest of the API's settings, with the same meaning |

- **`SERPFLOW_BASE_URL` is ignored.** There is no HTTP hop
- **Settings load like the API's:** environment first, then `.env` in the working directory, then `../.env`. See [`app/core/config.py`](../../backend/app/core/config.py)
- **So the working directory matters.** Started from `backend/`, it picks up the repository's `.env` and needs nothing else. Started by a desktop app from somewhere else, it falls back to the built-in local defaults, which only match a local `make up` stack
- The full settings list: [secrets](../security/secrets.md) and [`.env.example`](../../.env.example)

## Run it

```bash
make mcp                                          # python -m app.mcp.server, in backend/
SERPFLOW_API_KEY=sf_test_... serpflow-mcp         # with the venv active
uv --directory backend run --no-sync serpflow-mcp # from anywhere; runs in backend/
```

- **It waits on stdin for a client.** Run by hand, it prints nothing and appears to hang; that is correct
- **Try it interactively** with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector \
  uv --directory /abs/path/to/SerpFlow/backend run --no-sync serpflow-mcp
```

## Connect a client

**Use `uv --directory`, with an absolute path.** It starts the server in `backend/`, so `.env` is found, and uses the backend's own venv.

**Claude Code**

```bash
claude mcp add --transport stdio \
  --env SERPFLOW_API_KEY=sf_test_... \
  --env SERPFLOW_MCP_SESSION=claude-code \
  serpflow -- uv --directory /abs/path/to/SerpFlow/backend run --no-sync serpflow-mcp
```

**Claude Desktop** (`claude_desktop_config.json`)

```jsonc
{
  "mcpServers": {
    "serpflow": {
      "command": "uv",
      "args": ["--directory", "/abs/path/to/SerpFlow/backend", "run", "--no-sync", "serpflow-mcp"],
      "env": {
        "SERPFLOW_API_KEY": "sf_test_...",
        "SERPFLOW_MCP_SESSION": "claude-desktop"
      }
    }
  }
}
```

- **On Windows**, use `C:\\path\\to\\SerpFlow\\backend` (escaped backslashes) in JSON, or forward slashes
- **If the client cannot find `uv`**, give its absolute path as `command` (`which uv`, or `where uv` on Windows)
- **Without uv:** set `command` to the venv's `serpflow-mcp` (`backend/.venv/bin/serpflow-mcp`, or `backend\.venv\Scripts\serpflow-mcp.exe`) and put `DATABASE_URL`, `API_KEY_PEPPER` and the other settings in `env`, because `.env` will not be found
- **Any other MCP client** that launches stdio servers takes the same command, arguments and environment

## Tools

**`plan(intent, budget?)`**: plan without executing. **Zero SerpApi credits**: planning calls a language model, not SerpApi.

- **Returns:** `plan_id`, `intent`, `steps` (`index`, `engine`, `fan_out`, `freshness_requirement`, `warm`), `naive_cost`, `marginal_cost`, `savings`, `projected_full_scale_cost`, `warm_steps`, `candidate_count`, `single_candidate_reason`, `confidence`, `catalog_version`, `marginal_replan_changed_selection`, `replan_explanation`, `budget_reduction`, `rejected_alternatives`, plus `mode` and `remaining_budget`
- **The plan is persisted**, as `POST /v1/plan` does

**`search(intent, budget?)`**: plan with cache-aware replanning, then execute only the steps the cache cannot satisfy.

- **Returns:** `run_id`, `status`, `mode`, `plan` (as above), `credits_spent`, `credits_saved`, `cache_summary`, `remaining_budget`, `session` (`session_id`, `credits_used`, `session_cap`, or `null`), and `results`: the results summary

**`explain(run_id)`**: the Plan Inspector as structured data. **The stored counterfactual, not a recomputation.**

- **Returns:** `run_id`, `intent`, `status`, `mode`, `credits_spent`, `credits_saved`, `cache_summary`, `provenance`, `steps` (each with `cache_layer`, `credits`, `latency_ms`, `matched_query`, `similarity`, `age_seconds`, `ttl_source`), `plan`, and `candidates`, ordered by marginal rank (`label`, `engines`, `strategy`, `coverage`, `naive_cost`, `marginal_cost`, `naive_rank`, `marginal_rank`, `selected`, `rejection_reason`, `trade_off_note`)
- **A run in another organization is `NOT_FOUND`**

**`catalog(engine?)`**: the engine catalog.

- **No argument:** `catalog_version`, every engine with `purpose`, `capability_tags` and `cost`, and the catalog stats
- **One engine:** its `purpose`, `capability_tags`, `requires`, `optional`, `produces`, `cost`, `latency_class`, `volatility_prior`, `pii_risk`, `substitutes`, `depends_on` and `feeds`
- **Reads the committed catalog.** It opens no database session and does not resolve the key

- **The server also sends instructions** telling the model to call `plan` before `search` when it wants to see the cost first, and `explain` to see why a plan won

## Sessions and budgets

- **An agent is not a human holding a shared key.** When the key belongs to a service principal, or carries a session cap, every call runs under a **service session** with its own `session_cap` and `credits_used`
- **The seeded `service` key has a cap of 20 credits**
- **Set `SERPFLOW_MCP_SESSION`.** The name is stored as the session's external reference, and every call that passes the same name resumes the same open session, **across restarts too**
- **Without it, each tool call opens a fresh session.** The cap then limits single calls, not the agent's total, and the project and key budgets are the only cumulative limits
- **When the session reaches its cap, calls fail with `SESSION_CAP_EXCEEDED`**, not the organization's `BUDGET_EXHAUSTED`. Start a fresh session by choosing a new name
- **Budgets still apply at every scope:** organization, project, key and session. The tightest wins. See [API keys: service principal sessions](../security/api-keys.md#service-principal-sessions)

## Errors

- **A failing tool returns an MCP tool error** whose text is SerpFlow's human-readable message
- **The machine code is not in that text.** The message names the problem, and the run, if one was created, is in the console and `GET /v1/runs` with its code
- **The conditions an agent meets**, by the code the API would return:

| Code | Means |
| --- | --- |
| `UNAUTHENTICATED` | `SERPFLOW_API_KEY` is not set |
| `INVALID_API_KEY` | revoked, expired, mistyped, **or `API_KEY_PEPPER` differs from the API's** |
| `SESSION_CAP_EXCEEDED` | the service session's cap is spent |
| `BUDGET_EXHAUSTED` | a project, key or organization budget is spent |
| `NO_UPSTREAM_CREDENTIAL` | a live key with no SerpApi credential in the vault |
| `NOT_FOUND` | an unknown run or engine |

- Every code: [API errors](../api/overview.md#errors)

## Logging

- **Logs go to stderr**, never stdout, so they cannot corrupt the stdio protocol
- **With the default `LOG_OUTPUT=both` they also go to `logs/serpflow.log`**, relative to the working directory: `backend/logs/` when started with `uv --directory backend`
- **Credentials are redacted** by the same filter as the API's. See [observability](../operations/observability.md)

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every call is `INVALID_API_KEY`, though the key works with `curl` | the server loaded different settings from the API | start it in `backend/` (`uv --directory`), or pass the API's `API_KEY_PEPPER` and `DATABASE_URL` in `env` |
| `connection refused` on 5432 | no database | `make up && make upgrade && make seed` |
| The client says the server exited at once | `uv` or the path was not found | absolute paths for `command` and `--directory` |
| The agent never hits its cap | `SERPFLOW_MCP_SESSION` unset | set it; see [sessions](#sessions-and-budgets) |
| Results say `MOCK` | a `sf_test_...` key | expected. Use a live key and a vault credential for real searches |
| `ImportError` mentioning `FastMCP` or `MCPServer` | an old checkout | update; [`app/mcp/server.py`](../../backend/app/mcp/server.py) imports either |

## Related

- [SDKs and tools](overview.md) · [CLI](cli.md)
- [API keys](../security/api-keys.md) · [Threat model](../security/threat-model.md)
- [Model Context Protocol](https://modelcontextprotocol.io/)
