# SDKs

Two client libraries, and a drop-in replacement for the official SerpApi
client.

| SDK | Lives in | Installed as |
| --- | --- | --- |
| TypeScript | [`sdk/typescript/`](typescript) | `@serpflow/sdk` |
| Python | [`backend/app/sdk/`](../backend/app/sdk) | `serpflow`, from the backend package |

## Why they are in different places

The TypeScript SDK is a standalone npm package: its own `package.json`, its own
`tsconfig.json`, no runtime dependencies, published independently of the
backend. It has to be a directory of its own.

The Python SDK is not published separately. It lives inside the backend package
so it shares the project's own type definitions rather than duplicating them,
and `backend/serpflow.py` re-exports it under the public name:

```python
from serpflow import SerpFlow, AsyncSerpFlow, SerpApiCompat
```

Installing the backend (`uv pip install -e .`) makes that import work. Shipping
it as a separate distribution would mean keeping two copies of every response
shape in step, and they would drift.

## Python

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

    for event in client.stream("cafes in Koramangala with outdoor seating"):
        print(event.stage, event.status)
```

Async:

```python
from serpflow import AsyncSerpFlow

async with AsyncSerpFlow(api_key="sf_test_...") as client:
    result = await client.search("flights from Hyderabad to Da Nang in late November")
```

## TypeScript

```bash
npm install @serpflow/sdk
```

```typescript
import { SerpFlow, SerpFlowError } from "@serpflow/sdk";

const client = new SerpFlow({ apiKey: "sf_test_..." });

const plan = await client.route("review rings among Koramangala cafes", 20);
console.log(plan.engines.join(" -> "), plan.naiveCost, "->", plan.marginalCost);

for await (const event of client.stream("bakeries in Koramangala")) {
  console.log(event.stage, event.status);
}
```

No runtime dependencies. Runs in Node 18+, Deno, Bun and the browser.

```bash
cd sdk/typescript
npm install
npm run build        # tsc -> dist/
npm run typecheck
```

## The SerpApi drop-in

Both SDKs ship a compatibility client that keeps existing SerpApi code's shape.
Change the base URL and the API key, and the request goes through SerpFlow's
cache layers, budget enforcement and provenance.

```python
from serpflow import SerpApiCompat

search = SerpApiCompat({"engine": "google_maps", "q": "cafes in Koramangala",
                        "api_key": "sf_test_..."})
results = search.get_dict()
print(results["search_metadata"]["serpflow_credits_saved"])
```

This path does **not** re-route: you asked for an engine, you get that engine.
Adopt `client.search()` when you want routing as well.

## Related

- [API examples](../docs/api/examples.md) - the full set, including CLI and MCP
- [API overview](../docs/api/overview.md)
- [Streaming](../docs/api/streaming.md)
