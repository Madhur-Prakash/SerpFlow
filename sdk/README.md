# SDKs

<p>
  <a href="typescript"><img alt="TypeScript SDK: @serpflow/sdk" src="https://img.shields.io/badge/TypeScript-%40serpflow%2Fsdk-3178C6?logo=typescript&logoColor=white"></a>
  <a href="../backend/app/sdk"><img alt="Python SDK: serpflow" src="https://img.shields.io/badge/Python-serpflow-3776AB?logo=python&logoColor=white"></a>
  <img alt="runtime dependencies: none (TypeScript), httpx (Python)" src="https://img.shields.io/badge/runtime%20deps-none%20%C2%B7%20httpx-3fcf8e">
  <img alt="registries: not yet published" src="https://img.shields.io/badge/npm%20%C2%B7%20PyPI-not%20yet%20published-555555">
  <img alt="SerpApi drop-in: yes" src="https://img.shields.io/badge/SerpApi%20drop--in-yes-2F6BFF">
  <a href="../LICENSE"><img alt="licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-D22128"></a>
</p>

[README](../README.md) › **SDKs** · [TypeScript SDK](typescript/README.md) · [Docs index](../docs/README.md) · [SDK docs](../docs/sdks/overview.md)

---

**Two client libraries, each with a SerpApi-shaped drop-in.** The full documentation lives in [`docs/sdks/`](../docs/sdks/overview.md): this page is the map.

| SDK | Lives in | Package name | Reference |
| --- | --- | --- | --- |
| TypeScript | [`sdk/typescript/`](typescript) | `@serpflow/sdk` on npm | [TypeScript SDK](../docs/sdks/typescript.md) |
| Python | [`backend/app/sdk/`](../backend/app/sdk) | `serpflow` on PyPI | [Python SDK](../docs/sdks/python.md) |

- **Neither is on a registry yet.** Both install from a checkout today, and both names were still free on 2026-10-11. How to publish them: [releasing](../docs/sdks/releasing.md)
- **The CLI and the MCP server** ship with the Python package: [CLI](../docs/sdks/cli.md), [MCP server](../docs/sdks/mcp.md)
- **Both SDKs talk to a SerpFlow server you run yourself.** SerpFlow is self-hosted for now, by the author's decision; the author will host it on demand, once enough people ask in a public GitHub issue: [hosting](../README.md#hosting)

## Why they are in different places

- **The TypeScript SDK is a standalone npm package**
  - its own `package.json` and `tsconfig.json`
  - no runtime dependencies
  - versioned and published independently of the backend
- **The Python SDK lives inside the backend package**, in [`app/sdk/__init__.py`](../backend/app/sdk/__init__.py)
  - it is self-contained: it imports only the standard library and `httpx`, nothing else from the backend
  - [`backend/serpflow.py`](../backend/serpflow.py) re-exports it under the public name, `from serpflow import SerpFlow`
  - that import works with the **editable** install (`make install-backend`), which puts `backend/` on `sys.path`. A regular wheel of the backend does not contain `serpflow.py` yet
  - because it is self-contained, it can move into its own distribution here, beside the TypeScript one. That is the recommended path before the first PyPI release: [releasing, option B](../docs/sdks/releasing.md#option-b-recommended-a-standalone-sdk-package)

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

- **`AsyncSerpFlow` covers `route`, `search` and `stream`.** The inspection calls are on the sync client
- Every method, type and error: [Python SDK](../docs/sdks/python.md)

## TypeScript

```typescript
import { SerpFlow, SerpFlowError } from "@serpflow/sdk";

const client = new SerpFlow({ apiKey: "sf_test_..." });

const plan = await client.route("review rings among Koramangala cafes", 20);
console.log(plan.engines.join(" -> "), plan.naiveCost, "->", plan.marginalCost);
if (plan.changedSelection) console.log(plan.explanation);

for await (const event of client.stream("bakeries in Koramangala")) {
  console.log(event.stage, event.status);
}
```

- **No runtime dependencies.** Runs in Node 18+, Deno, Bun and the browser
- Building it from source:

```bash
cd sdk/typescript
npm install
npm run typecheck
npm run build        # tsc -> dist/
```

- Every method, type and option: [TypeScript SDK](../docs/sdks/typescript.md). The package's own README, which npm shows: [`sdk/typescript/README.md`](typescript/README.md)

## The SerpApi drop-in

- **Both SDKs ship a compatibility client that keeps SerpApi's call shape:** a params dict in, `get_dict()` / `get_json()` (Python) or `getJson()` (TypeScript) out
- **Change the base URL and the API key**, and the request goes through SerpFlow's cache layers, budget enforcement and provenance

```python
from serpflow import SerpApiCompat

search = SerpApiCompat({"engine": "google_maps", "q": "cafes in Koramangala",
                        "api_key": "sf_test_..."})
results = search.get_dict()
print(results["search_metadata"]["serpflow_credits_saved"])
```

- **What it sends:** `q` (or `query`) becomes the intent of a `POST /v1/search`, so **SerpFlow's planner chooses the engines**
- **`engine` and the other SerpApi parameters are not forwarded.** They are echoed back in `search_parameters` and `search_metadata`, so code that reads them keeps working

## Releasing

- **Step by step, including the one-time fixes each package needs first:** [releasing the SDKs](../docs/sdks/releasing.md)

## Related

- [SDKs and tools](../docs/sdks/overview.md): the four surfaces side by side, and what each can do
- [API examples](../docs/api/examples.md): the same calls as `curl`
- [API overview](../docs/api/overview.md): authentication, every operation, every error code
- [Streaming](../docs/api/streaming.md): the frame contract behind `stream()`

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [README](../README.md) | [Docs index](../docs/README.md) | [TypeScript SDK](typescript/README.md) |
