# Worked examples

<p>
  <a href="../api/README.md"><img alt="docs: API" src="https://img.shields.io/badge/docs-API-009688?logo=readthedocs&logoColor=white"></a>
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="TypeScript: 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="MCP: server" src="https://img.shields.io/badge/MCP-server-555555">
  <a href="../../backend/app/core/text.py"><img alt="source: core/text.py" src="https://img.shields.io/badge/source-core%2Ftext.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [API](../api/README.md) › **Worked examples** · page 26 of 50

- **Every example runs against the deterministic mock** with a `test` API key ([test keys](../security/api-keys.md#test-keys))
- **Each one spends zero SerpApi credits.** [A search that found nothing](#a-search-that-found-nothing) also shows what a live key gets back

```bash
make seed            # prints a test key when it creates the demo organization
export SERPFLOW_API_KEY=sf_test_...
```

- **Keys are printed once.** If the API already seeded itself on startup, `make seed ARGS=--reset` recreates the demo organization with fresh keys ([first run](../deployment/local.md#first-run))
- **Every route, permission and error code used here:** [API overview](overview.md)

**On this page:** [plan](#plan-without-spending) · [execute](#execute) · [nothing found](#a-search-that-found-nothing) · [stream](#watch-it-happen) · [explain](#explain-a-run) · [false hit](#report-a-bad-semantic-hit) · [catalog](#explore-the-catalog) · [Python](#python-sdk) · [TypeScript](#typescript-sdk) · [SerpApi drop-in](#the-serpapi-drop-in) · [CLI](#cli) · [MCP](#mcp)

## Plan without spending

```bash
curl -s -X POST http://localhost:8000/v1/plan \
  -H "X-API-Key: $SERPFLOW_API_KEY" -H "content-type: application/json" \
  -d '{"intent":"find coordinated review rings among Koramangala cafes","budget":20}'
```

```jsonc
{
  "id": "plan_01M3WQ...",
  "intent": "find coordinated review rings among Koramangala cafes",
  "steps": [
    { "index": 0, "engine": "google_maps", "fan_out": 1,
      "freshness_requirement": "recent", "warm": true,
      "cache_state": { "layer": "exact", "age_seconds": 92, "warm": true } },
    { "index": 1, "engine": "google_maps_reviews", "fan_out": 20,
      "depends_on": [0], "warm": true },
    { "index": 2, "engine": "google_maps_contributor_reviews", "fan_out": 80,
      "depends_on": [1], "warm": true }
  ],
  "naive_cost": 101,
  "marginal_cost": 0,
  "savings": 101,
  "candidate_count": 8,
  "catalog_version": "v1.0.0",
  "marginal_replan_changed_selection": true,
  "replan_explanation": "Cache-aware replanning changed the selected plan. Ranked on cold cost alone, google_local>... would have won at 51 credits. google_maps>... costs 101 credits cold, but 3 of its 3 steps are already warm ...",
  "rejected_alternatives": [
    { "plan": "google_local>google_maps_reviews>google_maps_contributor_reviews",
      "naive_cost": 51, "marginal_cost": 1, "coverage": "full",
      "reason": "Marginal cost 1 against 0 for the selected plan (2 warm steps against 3)." },
    { "plan": "yelp>yelp_reviews", "naive_cost": 11, "marginal_cost": 11,
      "coverage": "narrow",
      "trade_off_note": "Yelp exposes reviewer display names but no stable contributor identity ...",
      "reason": "..." }
  ]
}
```

**The whole thesis is visible in one response:**

- what it would have cost cold, and what it costs now
- which plan the cold ranking would have chosen
- why each loser lost

It needs only `plan:create`, so an `analyst` can run it ([plan without executing](overview.md#plan-without-executing)). Every field: [what the Plan stores](../architecture/planner.md#what-the-plan-stores). These numbers, step by step: [the worked example](../architecture/marginal-replanning.md#worked-example-the-reference-demo).

## Execute

```bash
curl -s -D- -X POST http://localhost:8000/v1/search \
  -H "X-API-Key: $SERPFLOW_API_KEY" -H "content-type: application/json" \
  -d '{"intent":"recent reviews for a ramen shop in Seoul called Ichiran","budget":20}'
```

```
X-SerpFlow-Mode: MOCK
X-SerpFlow-Cache: exact
X-SerpFlow-Run-Id: run_01M3WT...
X-SerpFlow-Budget-Remaining: 60
X-SerpFlow-Catalog-Version: v1.0.0
```

```jsonc
{
  "run":  { "id": "run_01M3WT...", "status": "succeeded", "credits_spent": 0,
            "steps": [...], ... },
  "plan": { "parameter_bindings": { "q": "...", "gl": "kr", "hl": "ko", ... },
            "steps": [...], ... },
  "results": {
    "summary": { "result_key": "...", "count": 5, "items": [{ "title": "...", ... }] },
    "payload_ref": "...", "terminal_engine": "...", "steps": [...],
    "catalog_version": "v1.0.0"
  },
  "mode": { "mode": "mock", "label": "MOCK", "credited": false, "reason": "..." },
  "provenance": { "budget_remaining": 60, "cache_summary": { ... }, ... }
}
```

- **`plan.parameter_bindings` contains `gl: kr` and `hl: ko`:** Seoul implies a Korean locale ([stage C: synthesize](../architecture/planner.md#stage-c-synthesize))
- Getting that wrong would **silently** return a different result set
- **`X-SerpFlow-Cache` reads `mock` when the mock answered**, and `exact` when the same request was already warm. Every header: [provenance headers](overview.md#provenance-headers)

## A search that found nothing

```bash
curl -s -X POST http://localhost:8000/v1/search \
  -H "X-API-Key: $SERPFLOW_API_KEY" -H "content-type: application/json" \
  -d '{"intent":"what is nvidia trading at right now"}'
```

- **Google Finance gets a ticker, not the sentence:** the planner selects `google_finance` and binds `q` to `NVDA:NASDAQ` in `plan.steps[0].parameters` ([`app/core/text.py`](../../backend/app/core/text.py) `adapt_query`). `plan.parameter_bindings` keeps the synthesized query
- **With a live key**, when SerpApi runs a search and finds nothing, it still answers with an `error` field, but `search_metadata.status` is `Success` (or the message says it "hasn't returned any results"). SerpFlow reads that as a result, not a failure ([`app/integrations/serpapi/client.py`](../../backend/app/integrations/serpapi/client.py) `is_empty_result`):

```jsonc
// results.summary
{ "result_key": null, "count": 0, "items": [],
  "notice": "Google Finance hasn't returned any results for this query." }
```

- **The run succeeded and the credit is recorded**, because SerpApi billed the search
- **The empty answer is cached** like any other, so asking again is free until it expires
- **`notice` is SerpApi's own message**, at most 300 characters, set only when the summary has no items ([`app/services/executor/service.py`](../../backend/app/services/executor/service.py)). The console's result panel shows it
- A test key never produces this: the mock never answers with SerpApi's `error` field ([`app/integrations/serpapi/mock.py`](../../backend/app/integrations/serpapi/mock.py))

## Watch it happen

```bash
RUN=$(curl -s -X POST http://localhost:8000/v1/search \
  -H "X-API-Key: $SERPFLOW_API_KEY" -H "content-type: application/json" \
  -d '{"intent":"bakeries in Koramangala","budget":20,"stream":true}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['run_id'])")

curl -N -H "X-API-Key: $SERPFLOW_API_KEY" \
  "http://localhost:8000/v1/runs/$RUN/stream"
```

```
event: stage
id: 1
data: {"stage":"analyzing_intent","status":"running","elapsed_ms":0.0,...}

event: stage
id: 4
data: {"stage":"finding_candidates","status":"complete","elapsed_ms":10.4,...}

event: stage
id: 14
data: {"stage":"inspecting_cache","status":"complete","elapsed_ms":147.0,...}

event: stage
id: 16
data: {"stage":"reranking_plans","status":"complete","elapsed_ms":152.4,...}

event: stage
id: 20
data: {"stage":"executing","status":"step_complete","elapsed_ms":227.1,...}

event: complete
id: 21
data: {"stage":"complete","status":"complete","elapsed_ms":399.3,...}
```

- **Abridged:** every stage sends a `running` and a `complete` frame (`executing` a `running` and a `step_complete` per step), except `calculating_marginal_cost` and `reranking_plans`, which send only `complete`
- The full contract, and what each `detail` carries: [streaming](streaming.md#the-stage-sequence)

## Explain a run

```bash
curl -s -H "X-API-Key: $SERPFLOW_API_KEY" \
  http://localhost:8000/v1/runs/$RUN | python -m json.tool
```

Returns the **Run Inspector payload**:

- every step, with the cache layer that served it
- the matched query and similarity, for semantic hits
- entry age, TTL source, credits and latency
- the whole plan, with every candidate
- each step's `payload_ref` only when the key holds `payload:read`; the raw payload is `GET /v1/runs/{id}/steps/{step_id}/payload` ([runs](overview.md#runs))

## Report a bad semantic hit

```bash
curl -s -X POST http://localhost:8000/v1/runs/$RUN/report-false-hit \
  -H "X-API-Key: $SERPFLOW_API_KEY" -H "content-type: application/json" \
  -d '{"note":"cached entry was for a different neighbourhood","invalidate_entry":true}'
```

```json
{ "ok": true, "message": "Report filed. The cache entry was invalidated." }
```

- **Records the report**, against `step_id` if given, else the run's first semantic step (or its first step)
- **Increments** [`serpflow_semantic_false_hit_reports_total`](../operations/observability.md#metrics)
- **Invalidates the offending entry**, so it cannot be served again. The message says `Report filed.` alone when no matching entry was found
- Why a wrong hit is evidence, not noise: [rejections are evidence](../architecture/caching.md#rejections-are-evidence) and [ADR 0002](../adr/0002-deterministic-semantic-guard.md)

## Explore the catalog

```bash
curl -s -H "X-API-Key: $SERPFLOW_API_KEY" \
  "http://localhost:8000/v1/catalog/engines/google_maps_contributor_reviews/paths?params=q,location"
```

```jsonc
{
  "engine": "google_maps_contributor_reviews",
  "catalog_version": "v1.0.0",
  "available_params": ["_nkw", "find_desc", "k", "location", "mauthors", "p", "q", ...],
  "path_count": 2,
  "paths": [
    { "engines": ["google_local","google_maps_reviews","google_maps_contributor_reviews"],
      "hops": 3, "naive_cost": 51, "steps": [...] },
    { "engines": ["google_maps","google_maps_reviews","google_maps_contributor_reviews"],
      "hops": 3, "naive_cost": 101, "steps": [...] }
  ]
}
```

- **The typed graph, answering directly:** every way to reach reviewer identity from an ordinary query and a location
- **Each path's `steps`** carry their bindings: which field of which earlier step fills each parameter. See [the engine catalog](../architecture/catalog.md#the-reference-demo-chain)

## Python SDK

**Not released yet:** it will be published when the author decides to host SerpFlow. If you self-host, install it from a checkout ([install](../sdks/python.md#install)).

```python
from serpflow import SerpFlow

with SerpFlow(api_key="sf_test_...") as client:
    # Plan only. No SerpApi call, so zero credits (a model is called only if Groq is configured).
    plan = client.route("review rings among Koramangala cafes", budget=20)
    print(plan.engines, plan.naive_cost, "->", plan.marginal_cost)

    result = client.search("recent reviews for Ichiran in Seoul", budget=20)
    print(result.mode, result.credits_spent, "spent,", result.credits_saved, "saved")
    for item in result.items:
        print(" ", item.get("title"))
```

- **`api_key` falls back to `SERPFLOW_API_KEY`**, and the base URL to `SERPFLOW_BASE_URL`, both read from the shell ([configuration](../sdks/overview.md#configuration))
- Streaming, `explain()`, the async client and every method: [Python SDK](../sdks/python.md)

## TypeScript SDK

**Not released yet:** it will be published when the author decides to host SerpFlow. If you self-host, build and install it from a checkout ([install](../sdks/typescript.md#install)).

```typescript
import { SerpFlow, SerpFlowError } from "@serpflow/sdk";

const client = new SerpFlow({ apiKey: "sf_test_..." });

try {
  const plan = await client.route("review rings among Koramangala cafes", 20);
  console.log(plan.engines.join(" -> "), plan.naiveCost, "->", plan.marginalCost);
} catch (error) {
  if (error instanceof SerpFlowError) {
    console.error(error.code, error.message);
    if (error.remedy) console.error("Fix:", error.remedy);
  }
}
```

- **No runtime dependencies.** Runs in Node 18+, Deno, Bun and the browser
- **`remedy`** is the TypeScript SDK's own hint, for four codes: `BUDGET_EXHAUSTED`, `UPSTREAM_QUOTA_EXHAUSTED`, `NO_UPSTREAM_CREDENTIAL` and `REPLAY_CASSETTE_MISS`
- Streaming, the types and every method: [TypeScript SDK](../sdks/typescript.md)

## The SerpApi drop-in

- **Existing SerpApi code keeps its shape:** a params dict in, `get_dict()` / `getJson()` out
- Swap the class for `SerpApiCompat` and the key for a SerpFlow one, and the request now goes through SerpFlow's planner, cache layers and budget enforcement

```python
from serpflow import SerpApiCompat

search = SerpApiCompat({
    "engine": "google_maps",
    "q": "cafes in Koramangala",
    "api_key": "sf_test_...",
})
results = search.get_dict()

print(results["search_metadata"]["serpflow_mode"])
print(results["search_metadata"]["serpflow_credits_saved"])
```

```typescript
import { SerpApiCompat } from "@serpflow/sdk";

const search = new SerpApiCompat({
  engine: "google_maps",
  q: "cafes in Koramangala",
  api_key: "sf_test_...",
});
const results = await search.getJson();
```

- **This path re-routes.** Only `q` (or `query`) is sent, as the intent of a `POST /v1/search`; SerpFlow's planner picks the engines ([`app/sdk/__init__.py`](../../backend/app/sdk/__init__.py), [`sdk/typescript/src/index.ts`](../../sdk/typescript/src/index.ts))
- **`engine` and every other parameter are echoed, not sent:** they come back in `search_parameters` and `search_metadata.engine`, so code that reads them keeps working, but they do not constrain the plan
- **The body is SerpFlow's `results`**, not SerpApi's raw keys: read `summary.items`, not `local_results`. `search_metadata` adds `serpflow_mode`, `serpflow_credits_spent` and `serpflow_credits_saved`
- **What you gain:** routing, caching, budget enforcement and provenance on code you have not rewritten
- **Adopt `client.search()`** when you want the plan, the run and the full result
- Details and limits: [Python drop-in](../sdks/python.md#the-serpapi-drop-in), [TypeScript drop-in](../sdks/typescript.md#the-serpapi-drop-in)

## CLI

```bash
serpflow plan --budget 20 "review rings among Koramangala cafes"
serpflow search "flights from Hyderabad to Da Nang in late November"
serpflow runs --limit 10
serpflow catalog paths google_maps_reviews --params q,location
serpflow health
```

- **`serpflow plan` prints:** the cost comparison, the candidate set, every rejection reason, and any budget reduction with its impact note
- **Reads `SERPFLOW_API_KEY` and `SERPFLOW_BASE_URL` from the shell**, not from `.env`
- Install, every command, `--json` and exit codes: [CLI](../sdks/cli.md)

## MCP

```jsonc
// claude_desktop_config.json
{
  "mcpServers": {
    "serpflow": {
      "command": "uv",
      "args": ["--directory", "/abs/path/to/SerpFlow/backend", "run", "--no-sync", "serpflow-mcp"],
      "env": { "SERPFLOW_API_KEY": "sf_test_...",
               "SERPFLOW_MCP_SESSION": "claude-desktop" }
    }
  }
}
```

- **The server runs the services in-process** against the API's database, so `SERPFLOW_BASE_URL` is ignored ([`app/mcp/server.py`](../../backend/app/mcp/server.py))
- **`uv --directory` starts it in `backend/`**, so it loads the repository's `.env` and its [`API_KEY_PEPPER`](../security/secrets.md#pepper) matches the API's. The `serpflow-mcp` script is declared in [`backend/pyproject.toml`](../../backend/pyproject.toml)
- **Tools:** `plan`, `search`, `explain`, `catalog`
- **A service key, or any key with a session cap, runs every call under a service session** with its own cap, so an agent is **budgeted like any other caller**, not treated as a human with a shared key
- **`SERPFLOW_MCP_SESSION` names that session**, and the same name resumes it, across restarts too. Without it, every tool call opens a fresh session, and the cap limits single calls rather than the agent's total
- Claude Code, other clients and every tool's return shape: [MCP server](../sdks/mcp.md#connect-a-client)

## Related

- [API overview](overview.md): every route, permission, header and error code these examples use
- [Streaming](streaming.md): the frame contract behind [watch it happen](#watch-it-happen)
- [SDKs and tools](../sdks/overview.md): the four clients compared, and which one to use
- [Execution modes](../product/execution-modes.md#who-chooses-and-precedence): why every example here is `MOCK` and spends nothing
- [Marginal-cost replanning](../architecture/marginal-replanning.md#worked-example-the-reference-demo): the numbers in the plan example, derived
- [The reference demo](../product/demo.md): the same plan going from cold to warm across three phases
- [Troubleshooting](../operations/troubleshooting.md#results-look-wrong-but-the-request-succeeded): when a request succeeds but the results look wrong

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Streaming](../api/streaming.md) | [Docs index](../README.md) · [API index](../api/README.md) | [SDKs index](../sdks/README.md) |
