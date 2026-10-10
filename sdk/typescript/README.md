# @serpflow/sdk

<p>
  <img alt="TypeScript 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="runtime dependencies: none" src="https://img.shields.io/badge/runtime%20deps-none-3fcf8e">
  <img alt="Node 18+" src="https://img.shields.io/badge/Node-18%2B-5FA04E?logo=nodedotjs&logoColor=white">
  <img alt="Deno" src="https://img.shields.io/badge/Deno-supported-000000?logo=deno&logoColor=white">
  <img alt="Bun" src="https://img.shields.io/badge/Bun-supported-000000?logo=bun&logoColor=white">
  <img alt="browser" src="https://img.shields.io/badge/browser-supported-4285F4?logo=googlechrome&logoColor=white">
  <img alt="licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-D22128">
</p>

[README](../../README.md) › [SDKs](../README.md) › **TypeScript SDK** · [Docs index](../../docs/README.md) · [API examples](../../docs/api/examples.md)

---

**TypeScript client for [SerpFlow](https://github.com/serpflow/serpflow)**, a search control plane for SerpApi.

- **No runtime dependencies**
- Runs in **Node 18+, Deno, Bun and the browser**

```bash
npm install @serpflow/sdk
```

## Use

```typescript
import { SerpFlow, SerpFlowError } from "@serpflow/sdk";

const client = new SerpFlow({ apiKey: "sf_test_..." });
```

### Plan without spending

- **Planning calls a language model, not SerpApi**, so it spends zero credits

```typescript
const plan = await client.route("review rings among Koramangala cafes", 20);

console.log(plan.engines.join(" -> "));   // google_maps -> google_maps_reviews -> ...
console.log(plan.naiveCost, "->", plan.marginalCost);   // 101 -> 0

if (plan.marginalReplanChangedSelection) {
  console.log(plan.replanExplanation);
}
```

### Execute

```typescript
const result = await client.search("recent reviews for Ichiran in Seoul", 20);
console.log(result.mode, result.creditsSpent, result.creditsSaved);
```

- **`result.mode` is always present.** Mocked or replayed data is never presented as live

### Stream

- **One frame per real backend stage transition.** No timer anywhere in this path

```typescript
for await (const event of client.stream("bakeries in Koramangala")) {
  console.log(event.stage, event.status, Math.round(event.elapsedMs) + "ms");
}
```

- The frame contract: [streaming](../../docs/api/streaming.md)

### Errors

```typescript
try {
  await client.search("...", 20);
} catch (error) {
  if (error instanceof SerpFlowError) {
    console.error(error.code, error.message);
    if (error.remedy) console.error("Fix:", error.remedy);
  }
}
```

- **Codes are stable**, and each carries a `remedy`
- `BUDGET_EXHAUSTED` (your SerpFlow cap) and `UPSTREAM_QUOTA_EXHAUSTED` (SerpApi's) are **never conflated**
- The full list: [API errors](../../docs/api/overview.md#errors)

## The SerpApi drop-in

- **Existing SerpApi code keeps its shape**
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

- **This path does not re-route:** you asked for an engine, you get that engine
- **Adopt `client.search()`** when you want routing as well

## Test keys

- **A `sf_test_...` key routes to the deterministic mock** and spends zero SerpApi credits, whatever the server's mode is
- `make seed` prints one. See [API keys](../../docs/security/api-keys.md#test-keys)

## Build

```bash
npm install
npm run build        # tsc -> dist/
npm run typecheck
```

## License

[Apache-2.0](../../LICENSE).

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [SDKs](../README.md) | [Docs index](../../docs/README.md) | [Backend package](../../backend/README.md) |
