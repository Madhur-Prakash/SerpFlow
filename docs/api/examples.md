# Worked examples

<p>
  <a href="../README.md#api"><img alt="docs: API" src="https://img.shields.io/badge/docs-API-009688?logo=readthedocs&logoColor=white"></a>
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="TypeScript: 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="MCP: server" src="https://img.shields.io/badge/MCP-server-555555">
  <a href="../../sdk/typescript/README.md"><img alt="source: typescript/README.md" src="https://img.shields.io/badge/source-typescript%2FREADME.md-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [API](../README.md#api) › **Worked examples** · page 21 of 50

- **Every example runs against the deterministic mock** with a `test` API key
- **Each one spends zero SerpApi credits**

```bash
make seed            # prints a test key
export SERPFLOW_API_KEY=sf_test_...
```

**On this page:** [plan](#plan-without-spending) · [execute](#execute) · [stream](#watch-it-happen) · [explain](#explain-a-run) · [false hit](#report-a-bad-semantic-hit) · [catalog](#explore-the-catalog) · [Python](#python-sdk) · [TypeScript](#typescript-sdk) · [SerpApi drop-in](#the-serpapi-drop-in) · [CLI](#cli) · [MCP](#mcp)

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

- **`parameter_bindings` will contain `gl: kr` and `hl: ko`:** Seoul implies a Korean locale
- Getting that wrong would **silently** return a different result set

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
data: {"stage":"analyzing_intent","status":"running","elapsed_ms":0.0,...}
data: {"stage":"finding_candidates","status":"complete","elapsed_ms":10.4,...}
data: {"stage":"inferring_freshness","status":"complete","elapsed_ms":20.1,...}
data: {"stage":"generating_candidates","status":"complete","elapsed_ms":30.2,...}
data: {"stage":"inspecting_cache","status":"complete","elapsed_ms":147.0,...}
data: {"stage":"reranking_plans","status":"complete","elapsed_ms":152.4,...}
data: {"stage":"executing","status":"step_complete","elapsed_ms":227.1,...}
data: {"stage":"complete","status":"complete","elapsed_ms":399.3,...}
```

- The full contract: [streaming](streaming.md)

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

## Report a bad semantic hit

```bash
curl -s -X POST http://localhost:8000/v1/runs/$RUN/report-false-hit \
  -H "X-API-Key: $SERPFLOW_API_KEY" -H "content-type: application/json" \
  -d '{"note":"cached entry was for a different neighbourhood","invalidate_entry":true}'
```

- **Records the report**
- **Increments** `serpflow_semantic_false_hit_reports_total`
- **Invalidates the offending entry**, so it cannot be served again

## Explore the catalog

```bash
curl -s -H "X-API-Key: $SERPFLOW_API_KEY" \
  "http://localhost:8000/v1/catalog/engines/google_maps_contributor_reviews/paths?params=q,location"
```

```json
{
  "engine": "google_maps_contributor_reviews",
  "catalog_version": "v1.0.0",
  "path_count": 2,
  "paths": [
    { "engines": ["google_local","google_maps_reviews","google_maps_contributor_reviews"],
      "hops": 3, "naive_cost": 51 },
    { "engines": ["google_maps","google_maps_reviews","google_maps_contributor_reviews"],
      "hops": 3, "naive_cost": 101 }
  ]
}
```

- **The typed graph, answering directly:** every way to reach reviewer identity from an ordinary query and a location

## Python SDK

```python
from serpflow import SerpFlow

with SerpFlow(api_key="sf_test_...") as client:
    # Plan only. Calls a language model, not SerpApi: zero credits.
    plan = client.route("review rings among Koramangala cafes", budget=20)
    print(plan.engines, plan.naive_cost, "->", plan.marginal_cost)
    if plan.marginal_replan_changed_selection:
        print(plan.replan_explanation)

    result = client.search("recent reviews for Ichiran in Seoul", budget=20)
    print(result.mode, result.credits_spent, "spent,", result.credits_saved, "saved")
    for item in result.items:
        print(" ", item.get("title"))

    for event in client.stream("cafes in Koramangala with outdoor seating"):
        print(event.stage, event.status)

    print(client.explain(result.run_id)["candidates"])
```

Async:

```python
from serpflow import AsyncSerpFlow

async with AsyncSerpFlow(api_key="sf_test_...") as client:
    result = await client.search("flights from Hyderabad to Da Nang in late November")
```

## TypeScript SDK

```typescript
import { SerpFlow, SerpFlowError } from "@serpflow/sdk";

const client = new SerpFlow({ apiKey: "sf_test_..." });

try {
  const plan = await client.route("review rings among Koramangala cafes", 20);
  console.log(plan.engines.join(" -> "), plan.naiveCost, "->", plan.marginalCost);

  for await (const event of client.stream("bakeries in Koramangala")) {
    console.log(event.stage, event.status, Math.round(event.elapsedMs) + "ms");
  }
} catch (error) {
  if (error instanceof SerpFlowError) {
    console.error(error.code, error.message);
    if (error.remedy) console.error("Fix:", error.remedy);
  }
}
```

- **No runtime dependencies.** Runs in Node 18+, Deno, Bun and the browser
- More: [`sdk/typescript/README.md`](../../sdk/typescript/README.md)

## The SerpApi drop-in

- **Existing SerpApi code keeps its shape**
- Change the base URL and the API key, and the request now goes through SerpFlow's cache layers and budget enforcement

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

- **This path does not re-route:** you asked for an engine, you get that engine
- **What you gain:** caching, budget enforcement and provenance
- **Adopt `client.search()`** when you want routing as well

## CLI

```bash
serpflow search "flights from Hyderabad to Da Nang in late November"
serpflow plan --budget 20 "review rings among Koramangala cafes"
serpflow runs --limit 10
serpflow replay run_01M3WT...
serpflow catalog explore google_maps_contributor_reviews
serpflow catalog paths google_maps_reviews --params q,location
serpflow catalog list --tag place_reviews
serpflow cache stats
serpflow benchmark compare
serpflow health
```

- **`serpflow plan` prints:** the cost comparison, the candidate set, every rejection reason, and any budget reduction with its impact note

## MCP

```bash
SERPFLOW_API_KEY=sf_test_... serpflow-mcp
```

```jsonc
// claude_desktop_config.json
{
  "mcpServers": {
    "serpflow": {
      "command": "serpflow-mcp",
      "env": { "SERPFLOW_API_KEY": "sf_test_...",
               "SERPFLOW_BASE_URL": "http://localhost:8000" }
    }
  }
}
```

- **Tools:** `plan`, `search`, `explain`, `catalog`
- **Every call resolves a full principal**, including a service session with its own cap
- So an agent is **budgeted like any other caller**, not treated as a human with a shared key

## Related

- [API overview](overview.md)
- [SDKs](../../sdk/README.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Streaming](../api/streaming.md) | [Docs index](../README.md) | [Database schema](../database/schema.md) |
