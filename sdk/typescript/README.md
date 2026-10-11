# @serpflow/sdk

<p>
  <img alt="TypeScript 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="runtime dependencies: none" src="https://img.shields.io/badge/runtime%20deps-none-3fcf8e">
  <img alt="Node 18+" src="https://img.shields.io/badge/Node-18%2B-5FA04E?logo=nodedotjs&logoColor=white">
  <img alt="Deno" src="https://img.shields.io/badge/Deno-supported-000000?logo=deno&logoColor=white">
  <img alt="Bun" src="https://img.shields.io/badge/Bun-supported-000000?logo=bun&logoColor=white">
  <img alt="browser" src="https://img.shields.io/badge/browser-supported-4285F4?logo=googlechrome&logoColor=white">
  <img alt="ESM only" src="https://img.shields.io/badge/module-ESM%20only-555555">
  <img alt="licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-D22128">
</p>

[SerpFlow](https://github.com/Madhur-Prakash/SerpFlow) › [SDKs](https://github.com/Madhur-Prakash/SerpFlow/blob/main/sdk/README.md) › **TypeScript SDK** · [Full reference](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/sdks/typescript.md) · [Docs index](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/README.md)

---

**TypeScript client for [SerpFlow](https://github.com/Madhur-Prakash/SerpFlow)**, a search control plane for SerpApi: it routes a natural-language intent to the right SerpApi engines, re-plans around what is already cached, and executes only what is required.

- **No runtime dependencies.** Only `fetch`, `ReadableStream` and `TextDecoder`
- Runs in **Node 18+, Deno, Bun and the browser**
- **ES module only**, with type declarations

```bash
npm install @serpflow/sdk
```

- **Until the first release is on npm**, install from a checkout: [building from source](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/sdks/typescript.md#install)

## Use

```typescript
import { SerpFlow, SerpFlowError } from "@serpflow/sdk";

const client = new SerpFlow({
  apiKey: "sf_test_...",                 // required; there is no environment fallback
  baseUrl: "http://localhost:8000",      // the default
  // projectId: "prj_...",               // optional: the key's project otherwise
  // fetch: myFetch,                     // optional: timeouts, proxies, tests
});
```

### Plan without spending

- **Planning calls a language model, not SerpApi**, so it spends zero credits

```typescript
const plan = await client.route("review rings among Koramangala cafes", 20);

console.log(plan.engines.join(" -> "));             // google_maps -> google_maps_reviews -> ...
console.log(plan.naiveCost, "->", plan.marginalCost);   // 101 -> 0

if (plan.changedSelection) {
  console.log(plan.explanation);                    // why cache state changed the winner
}
```

### Execute

```typescript
const result = await client.search("recent reviews for Ichiran in Seoul", 20);
console.log(result.mode, result.creditsSpent, result.creditsSaved);
for (const item of result.items) console.log(item.title);
```

- **`result.mode` is always present:** `LIVE`, `MOCK`, `REPLAY` or `RECORD`. Mocked or replayed data is never presented as live

### Stream

- **One frame per real backend stage transition.** No timer anywhere in this path

```typescript
for await (const event of client.stream("bakeries in Koramangala")) {
  console.log(event.stage, event.status, Math.round(event.elapsedMs) + "ms");
}
```

- The frame contract: [streaming](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/api/streaming.md)

### Inspect

```typescript
const why = await client.explain(result.runId);   // every candidate, and why the winner won
const again = await client.replay(result.runId);   // the same intent, against today's cache
const recent = await client.runs(10);
const engine = await client.catalog("google_maps_reviews");
```

### Errors

```typescript
try {
  await client.search("...", 20);
} catch (error) {
  if (error instanceof SerpFlowError) {
    console.error(error.code, error.status, error.message, error.requestId);
    if (error.remedy) console.error("Fix:", error.remedy);
  }
}
```

- **Codes are stable.** Four of them carry a `remedy`
- `BUDGET_EXHAUSTED` (your SerpFlow cap) and `UPSTREAM_QUOTA_EXHAUSTED` (SerpApi's) are **never conflated**
- Every code: [API errors](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/api/overview.md#errors)

## The SerpApi drop-in

- **Existing SerpApi code keeps its shape:** a params object in, `getJson()` out
- What you gain: caching, budget enforcement and provenance

```typescript
import { SerpApiCompat } from "@serpflow/sdk";

const search = new SerpApiCompat({
  engine: "google_maps",
  q: "cafes in Koramangala",
  api_key: "sf_test_...",
});
const results = await search.getJson();
```

- **`q` becomes the intent, and SerpFlow's planner picks the engines.** `engine` and the other parameters are echoed back in `search_parameters`, not forwarded

## Test keys

- **A `sf_test_...` key routes to the deterministic mock** and spends zero SerpApi credits, whatever the server's mode is
- A local SerpFlow's `make seed` prints one. See [API keys](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/security/api-keys.md#test-keys)

## In the browser

- **The SerpFlow API must allow your origin** in `CORS_ORIGINS`
- **Never ship a live key to a browser.** Use a test key for demos, or call SerpFlow from your own server

## More

- [Full reference](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/sdks/typescript.md): every method, type, option and known limitation
- [All the SDKs and tools](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/sdks/overview.md): Python, the CLI and the MCP server
- [Releasing this package](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/sdks/releasing.md)

## Build

```bash
npm install
npm run typecheck
npm run build        # tsc -> dist/
```

## License

[Apache-2.0](https://github.com/Madhur-Prakash/SerpFlow/blob/main/LICENSE).

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [SDKs](https://github.com/Madhur-Prakash/SerpFlow/blob/main/sdk/README.md) | [Docs index](https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/README.md) | [Backend package](https://github.com/Madhur-Prakash/SerpFlow/blob/main/backend/README.md) |
