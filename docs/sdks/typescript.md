# TypeScript SDK

- **`@serpflow/sdk`: one file, no runtime dependencies**: [`src/index.ts`](../../sdk/typescript/src/index.ts)
- **Uses only `fetch`, `ReadableStream` and `TextDecoder`**, so it runs in Node 18+, Deno, Bun and the browser
- **ES module only.** `package.json` declares `"type": "module"` and an `import` export, with type declarations beside it

**On this page:** [install](#install) · [configure](#configure) · [quick start](#quick-start) · [methods](#methods) · [types](#types) · [streaming](#streaming) · [errors](#errors) · [runtimes](#runtimes) · [recipes](#recipes) · [SerpApi drop-in](#the-serpapi-drop-in) · [limitations](#known-limitations) · [building](#building-from-source)

## Install

**Today, from a checkout.** The package is not on npm yet.

```bash
cd sdk/typescript
npm install && npm run build          # tsc -> dist/
cd /path/to/your-app
npm install /path/to/SerpFlow/sdk/typescript
```

- **Or install a tarball**, which is exactly what npm would serve:

```bash
cd sdk/typescript && npm run build && npm pack      # -> serpflow-sdk-1.0.0.tgz
cd /path/to/your-app && npm install /path/to/serpflow-sdk-1.0.0.tgz
```

- **After the first release:** `npm install @serpflow/sdk` (or `pnpm add`, `yarn add`, `bun add`). See [releasing](releasing.md)

## Configure

```typescript
new SerpFlow({ apiKey, baseUrl?, projectId?, fetch? })
```

| Option | Default | What it does |
| --- | --- | --- |
| `apiKey` | **required** | Sent as `X-API-Key`. Missing or empty throws an `Error` at construction. **No environment fallback** |
| `baseUrl` | `http://localhost:8000` | A trailing `/` is stripped |
| `projectId` | the key's project | Sent as `X-SerpFlow-Project` **and** as `project_id` in plan and search bodies |
| `fetch` | `globalThis.fetch` | Your own `fetch`: for timeouts, proxies, logging or tests. See [recipes](#recipes) |

```typescript
// Node: read the key yourself
const client = new SerpFlow({ apiKey: process.env.SERPFLOW_API_KEY! });
```

## Quick start

```typescript
import { SerpFlow, SerpFlowError } from "@serpflow/sdk";

const client = new SerpFlow({ apiKey: "sf_test_..." });

// Plan only. Calls a language model, not SerpApi: zero credits.
const plan = await client.route("review rings among Koramangala cafes", 20);
console.log(plan.engines.join(" -> "), plan.naiveCost, "->", plan.marginalCost);
if (plan.changedSelection) console.log(plan.explanation);

// Plan with cache-aware replanning, then execute.
const result = await client.search("recent reviews for Ichiran in Seoul", 20);
console.log(result.mode, result.creditsSpent, "spent,", result.creditsSaved, "saved");
for (const item of result.items) console.log(" ", item.title);

// Why did that plan win?
const why = await client.explain(result.runId);
console.log(why.candidates);
```

- **The default export is `SerpFlow`** as well: `import SerpFlow from "@serpflow/sdk"`

## Methods

**Every method returns a `Promise`** and rejects with [`SerpFlowError`](#errors) on a 4xx or 5xx.

| Method | Request | Resolves to |
| --- | --- | --- |
| `route(intent, budget?)` | `POST /v1/plan` | [`PlanView`](#planview). **Spends zero credits** |
| `plan(intent, budget?)` | alias of `route` | |
| `search(intent, budget?)` | `POST /v1/search` | [`SearchResult`](#searchresult) |
| `run(intent, budget?)` | alias of `search` (**not** `POST /v1/run`) | |
| `stream(intent, budget?)` | `POST /v1/search` with `stream: true`, then `GET /v1/runs/{id}/stream` | `AsyncGenerator<RunEvent>` |
| `getRun(runId)` | `GET /v1/runs/{id}` | the Run Inspector payload, as returned |
| `explain(runId)` | `GET /v1/runs/{id}`, reshaped | `runId`, `intent`, `selected`, `naiveCost`, `marginalCost`, `changedSelection`, `explanation`, `candidates`, `rejectedAlternatives` |
| `replay(runId)` | `POST /v1/runs/{id}/replay` | `SearchResult` against **today's** cache state |
| `runs(limit = 25)` | `GET /v1/runs?limit=` | the `items` of one page |
| `catalog(engine?)` | `GET /v1/catalog`, or `/v1/catalog/engines/{engine}` | the catalog, or one engine |
| `budgets()` | `GET /v1/budgets` | budgets and spend |
| `health()` | `GET /readyz` | `status`, `version`, `mode`, `catalog_version`, `checks` |

- **Budgets are positional:** `search(intent, 20)`, where Python uses `budget=20`
- **`intent`** is 3 to 2,000 characters; **`budget`** is 1 to 100,000. Leave `budget` out to use the project's
- **Raw payloads keep the API's `snake_case`.** Only the SDK's own views (`PlanView`, `SearchResult`, `RunEvent`, `explain`) are `camelCase`

## Types

All exported, so you can annotate your own code with them.

### PlanView

| Field | Type | Meaning |
| --- | --- | --- |
| `id`, `intent` | `string` | |
| `engines` | `string[]` | the selected plan's engines, in step order |
| `steps` | `PlanStep[]` | `index`, `engine`, `fan_out`, `freshness_requirement`, `warm`, `cache_state?` |
| `naiveCost` | `number` | credits if every step ran cold |
| `marginalCost` | `number` | credits given what is already warm |
| `savings` | `number` | from the server, else `max(0, naiveCost - marginalCost)` |
| `candidateCount` | `number` | plans considered |
| `confidence` | `number` | |
| `catalogVersion` | `string` | e.g. `v1.0.0` |
| `changedSelection` | `boolean` | **the thesis:** did cache state change which plan won? |
| `explanation` | `string \| null` | why, in a sentence |
| `warmSteps` | `Record<string, unknown>[]` | which steps the cache already satisfies |
| `rejectedAlternatives` | `Record<string, unknown>[]` | every loser, with costs, coverage and reason |
| `budgetReduction` | `Record<string, unknown> \| null` | fan-outs cut to fit the budget |
| `projectedFullScaleCost` | `number \| null` | a projection only; never executed live |
| `raw` | `Record<string, unknown>` | the full plan JSON |

### SearchResult

| Field | Type | Meaning |
| --- | --- | --- |
| `runId` | `string` | |
| `status` | `string` | `succeeded`, `failed`, ... |
| `mode` | `string` | `LIVE`, `MOCK`, `REPLAY` or `RECORD`. **Never present replayed data as live** |
| `creditsSpent`, `creditsSaved` | `number` | |
| `plan` | `PlanView` | the plan that ran |
| `results` | `Record<string, unknown>` | the results payload |
| `items` | `Record<string, unknown>[]` | `results.summary.items`, or `[]` |
| `raw` | `Record<string, unknown>` | the full response |

### RunEvent

| Field | Type | Meaning |
| --- | --- | --- |
| `stage` | `string` | `queued`, `analyzing_intent`, ..., `complete` |
| `status` | `string` | `running`, `complete`, `step_complete`, `failed`, ... |
| `elapsedMs` | `number` | since the run started |
| `detail` | `Record<string, unknown>` | stage-specific; an `error` frame carries `code` and `message` |
| `type` | `"stage" \| "complete" \| "error" \| "heartbeat"` | heartbeats are never yielded |

- Also exported: `SerpFlowOptions`, `PlanStep`, `SerpFlowError`, `SerpApiCompat`

## Streaming

```typescript
for await (const event of client.stream("bakeries in Koramangala", 20)) {
  console.log(event.stage.padEnd(24), event.status.padEnd(14), Math.round(event.elapsedMs) + "ms");
  if (event.type === "error") console.error(event.detail.code, event.detail.message);
}
```

- **One frame per real backend stage transition.** No timer anywhere in this path
- **The generator returns by itself** after the `complete` or `error` frame, and cancels the underlying reader
- **Breaking out of the loop early does not cancel the HTTP stream.** The connection stays open until the run finishes server-side. The run itself carries on either way
- **A failed run arrives as an `error` frame, not a rejection.** Only a failure to start the run rejects
- The frame contract: [streaming](../api/streaming.md)

## Errors

```typescript
import { SerpFlowError } from "@serpflow/sdk";

try {
  await client.search("flights from Hyderabad to Da Nang in late November", 5);
} catch (error) {
  if (error instanceof SerpFlowError) {
    console.error(error.code, error.status, error.message, error.requestId);
    if (error.remedy) console.error("Fix:", error.remedy);
  } else {
    throw error;   // a network failure: fetch's own TypeError
  }
}
```

| Property | Meaning |
| --- | --- |
| `code` | the stable machine code, or `HTTP_<status>` for a non-JSON body |
| `status` | the HTTP status |
| `message` | human-readable, safe to show |
| `requestId` | quote it when reporting a problem |
| `remedy` | what to do, for four codes; `null` otherwise |

| Code | `remedy` |
| --- | --- |
| `BUDGET_EXHAUSTED` | raise the SerpFlow budget. Your cap, not the SerpApi quota |
| `UPSTREAM_QUOTA_EXHAUSTED` | the SerpApi account is out of searches |
| `NO_UPSTREAM_CREDENTIAL` | attach a SerpApi credential, or use a test key |
| `REPLAY_CASSETTE_MISS` | record one with `SERPFLOW_MODE=record` |

- **Branch on `code`, never on `message`.** Every code: [API errors](../api/overview.md#errors)
- **Network failures are not wrapped.** They reject with whatever your `fetch` throws

## Runtimes

| Runtime | Notes |
| --- | --- |
| **Node 18+** | global `fetch` and web streams are built in |
| **Deno** | `import { SerpFlow } from "npm:@serpflow/sdk"` once published; a local path import of `dist/index.js` today |
| **Bun** | works as in Node |
| **Browser** | works, **with two conditions below** |

**In the browser:**

- **The API must allow your origin.** Add it to `CORS_ORIGINS` on the server. See [`app/core/config.py`](../../backend/app/core/config.py)
- **Never ship a live key to a browser.** Anyone can read it out of the page. Use a `sf_test_...` key for demos, or call SerpFlow from your own backend and keep the key there
- **CommonJS needs a dynamic import:** `const { SerpFlow } = await import("@serpflow/sdk")`

## Recipes

**A timeout.** There is no timeout option; wrap `fetch`:

```typescript
const client = new SerpFlow({
  apiKey: process.env.SERPFLOW_API_KEY!,
  fetch: (input, init) => fetch(input, { ...init, signal: AbortSignal.timeout(60_000) }),
});
```

- **Leave streams out of a short timeout.** The same `fetch` carries the SSE request, which stays open for the whole run

**Another project**

```typescript
const market = new SerpFlow({ apiKey, projectId: "prj_01M3..." });
```

**A fake server in tests**

```typescript
const client = new SerpFlow({
  apiKey: "sf_test_x",
  fetch: async () => new Response(JSON.stringify({ items: [] }), { status: 200 }),
});
await client.runs();   // []
```

- **Or run the real stack** with a `sf_test_...` key: deterministic results, zero credits

## The SerpApi drop-in

```typescript
import { SerpApiCompat } from "@serpflow/sdk";

const search = new SerpApiCompat(
  { engine: "google_maps", q: "cafes in Koramangala", api_key: "sf_test_..." },
  "http://localhost:8000",            // optional base URL
);
const results = await search.getJson();
console.log(results.search_metadata);
```

- **The call keeps SerpApi's shape:** a params object in, `getJson()` out, `search_metadata` and `search_parameters` in the result
- **What it sends:** `q` (or `query`) becomes the intent of a `POST /v1/search`. **SerpFlow's planner then picks the engines**
- **`engine` and every other parameter are not forwarded.** They are echoed back in `search_parameters` and `search_metadata.engine`
- **`search_metadata` gains** `serpflow_mode`, `serpflow_credits_spent` and `serpflow_credits_saved`
- **`api_key` is required here too**; there is no environment fallback

## Known limitations

- **`runs()` takes only `limit`.** For the `status`, `engine` and `changed_selection` filters, call `GET /v1/runs` yourself. The Python SDK passes them through
- **`stream()` does not check the stream response's status.** A 4xx on `GET /v1/runs/{id}/stream` ends the generator with no frames
- **`RunEvent` drops `run_id` and `sequence`** from each frame
- **Leaving a `stream()` loop early leaves the connection open** until the run ends
- **`plan` and `run` are instance properties**, not prototype methods. Call them on the client; a destructured `const { plan } = client` loses `this`
- **No automatic retries**
- **The drop-in ignores `engine`**, as described [above](#the-serpapi-drop-in)

## Building from source

```bash
cd sdk/typescript
npm install
npm run typecheck     # tsc --noEmit
npm run build         # tsc -> dist/index.js + dist/index.d.ts
```

- **Compiler settings:** ES2022 target, `strict`, `declaration`, no unused locals or parameters. See [`tsconfig.json`](../../sdk/typescript/tsconfig.json)
- **`dist/` is not committed.** It is built before every publish: see [releasing](releasing.md#before-the-first-typescript-release)

## Related

- [SDKs and tools](overview.md) · [Python SDK](python.md) · [Releasing](releasing.md)
- [The npm README](../../sdk/typescript/README.md), which is what npmjs.com shows
- [API overview](../api/overview.md) · [Streaming](../api/streaming.md)
