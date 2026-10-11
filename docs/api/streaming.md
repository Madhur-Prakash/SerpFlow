# Streaming

<p>
  <a href="../README.md#api"><img alt="docs: API" src="https://img.shields.io/badge/docs-API-009688?logo=readthedocs&logoColor=white"></a>
  <img alt="stages: 11" src="https://img.shields.io/badge/stages-11-009688">
  <img alt="SSE: streaming" src="https://img.shields.io/badge/SSE-streaming-555555">
  <img alt="FastAPI: 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <a href="../../backend/app/services/stream.py"><img alt="source: services/stream.py" src="https://img.shields.io/badge/source-services%2Fstream.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [API](../README.md#api) › **Streaming** · page 21 of 57

```http
GET /v1/runs/{run_id}/stream
Accept: text/event-stream
```

- **One frame per real backend stage transition**, published by the [planner](../architecture/planner.md) and the [executor](../architecture/executor.md) through one event bus ([`app/services/stream.py`](../../backend/app/services/stream.py))
- **No simulated progression in this path:** if the planner spends two seconds inspecting cache state, the stream is silent for two seconds
- **The console paces what it shows, and only that:** `usePacedRun` holds each stage as running for at least 320 ms (600 ms for `executing`) so fast stages stay readable, but never shows a stage complete before its frame has arrived and never runs ahead of the backend ([`frontend/src/hooks/useRunStream.ts`](../../frontend/src/hooks/useRunStream.ts), [the pipeline animation](../architecture/frontend.md#the-pipeline-animation))
- **Needs `run:read`**, like the rest of the [runs routes](overview.md#runs)

## Starting a run you can stream

`POST /v1/search` is synchronous by default and returns the finished result. To watch it happen, ask for the streaming variant:

```http
POST /v1/search
{ "intent": "find coordinated review rings among Koramangala cafes",
  "budget": 20, "stream": true }
```

```json
{
  "run_id": "run_01M3WT4FZXT9S2HYR4WZG91C0T",
  "stream_url": "/v1/runs/run_01M3WT4FZXT9S2HYR4WZG91C0T/stream",
  "mode": { "mode": "mock", "label": "MOCK", "credited": false, "reason": "..." },
  "status": "running"
}
```

- **`202 Accepted`**, with `X-SerpFlow-Run-Id` and `X-SerpFlow-Mode` set ([`app/api/v1/search.py`](../../backend/app/api/v1/search.py))
- **The run executes in-process**, on the same service
- **It is not handed to Kafka:** interactive search never is. A broker would add latency and a failure mode for no benefit
- The Kafka topic exists for scheduled, bulk, retried and webhook-triggered runs. See [ADR 0007](../adr/0007-interactive-search-bypasses-kafka.md) and [Kafka](../operations/kafka.md#what-goes-through-it-and-what-does-not)
- **Every run publishes frames, not only streamed ones.** A synchronous search or a replay goes through the same service layer ([`app/services/runs.py`](../../backend/app/services/runs.py)), so its stream can be replayed afterwards from the [buffer](#reconnecting)

## Frame shape

```
event: stage
id: 14
data: {"stage":"inspecting_cache","status":"complete","elapsed_ms":147.2,
       "detail":{"warm_steps_found":3,"per_candidate":[...],"elapsed_ms":147.2},
       "sequence":14,"run_id":"run_01M3...","type":"stage"}
```

- **Every frame carries** `stage`, `status`, `elapsed_ms`, `detail`, `sequence`, `run_id` and `type`
- **The SSE `event:` is the frame's `type`; the SSE `id:` is its `sequence`**, which is what `Last-Event-ID` refers to
- **`elapsed_ms`** is milliseconds since the run started. Planner frames measure it from the start of planning and also copy it into `detail.elapsed_ms`

| `type` | Meaning |
| --- | --- |
| `stage` | A planner or executor stage changed state |
| `complete` | The run finished; `detail` carries the summary |
| `error` | The run failed; `detail` carries `code` and `message`, as in the [API errors](overview.md#errors) |
| `heartbeat` | Sent after 15 seconds with no frame, to keep the connection open. `sequence` is 0 and it is not buffered |

- **`status`** is one of `running`, `complete`, `step_complete` or `failed`
- **Two keep-alives, in fact:** the bus sends the `heartbeat` frame, and the SSE layer also writes a `: ping` comment every 15 seconds, which clients ignore
- **The stream closes itself** after a `complete` or `error` frame

## The stage sequence

Eleven stages, then `complete`, in this order ([`app/services/planner/service.py`](../../backend/app/services/planner/service.py) `STAGES`):

| Stage | Frames | What it is | Produced by |
| --- | --- | --- | --- |
| `analyzing_intent` | running, complete | reading the request and retrieving catalog candidates | [Stage A: retrieve](../architecture/planner.md#stage-a-retrieve) |
| `finding_candidates` | running, complete | the retrieval summary, then the selector's choice | [Stage B: select](../architecture/planner.md#stage-b-select) |
| `synthesizing_parameters` | running, complete | dates, locale, entities, parameter binding | [Stage C: synthesize](../architecture/planner.md#stage-c-synthesize) |
| `inferring_freshness` | running, complete | how fresh each step must be | [Freshness inference](../architecture/planner.md#freshness-inference) |
| `finding_paths` | running, complete | walking typed dependency edges | [Stage D: path-find](../architecture/planner.md#stage-d-path-find-and-generate-candidates), [the catalog](../architecture/catalog.md) |
| `generating_candidates` | running, complete | multiple competing plans | [Candidate plurality](../architecture/planner.md#candidate-plurality-is-a-hard-requirement) |
| `inspecting_cache` | running, complete | all four layers, every step of every candidate | [Caching: two entry points](../architecture/caching.md#two-entry-points) |
| `calculating_marginal_cost` | complete only | only steps needing a live call count | [Costing a step](../architecture/marginal-replanning.md#costing-a-step) |
| `reranking_plans` | complete only | cold ranking against marginal ranking | [Ranking](../architecture/marginal-replanning.md#ranking) |
| `checking_budget` | running, complete | what fits, and what reduction costs | [Budget-aware reduction](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking) |
| `executing` | running and step_complete, per step | exact, semantic, archive, live | [The executor](../architecture/executor.md#per-step-record) |

- **`executing` emits one frame per step started and one per step finished**, so a three-step chain reports each step as it goes instead of going quiet. A step's fan-out is inside one pair: eighty contributor calls are one `running` and one `step_complete` frame ([`app/services/executor/service.py`](../../backend/app/services/executor/service.py))
- **`calculating_marginal_cost` and `reranking_plans` have no `running` frame**: both are computed inside the cache inspection and reported straight after it
- **A streamed search starts with a `queued` frame** (status `running`, `detail.intent`) when the run row is allocated. Planning then restarts the buffer and the sequence at 1, so a client that attaches later does not see it
- **A failure ends the stream with an `error` frame** (stage `error`, status `failed`) in place of `complete`
- **`POST /v1/plan` publishes no frames:** it has no run to attach them to. Its `stage_trace` carries the same records in the response

## What `detail` carries

Each stage reports **what it actually produced**:

```jsonc
// finding_candidates, complete (the running frame carries the first five keys)
{ "count": 8, "engines": [...], "from_substitution": [], "from_dependency": [],
  "top_score": 0.5299, "chosen": ["google_maps_contributor_reviews"],
  "rejected_count": 7, "provider": "mock", "model": "deterministic-v1" }

// synthesizing_parameters
{ "parameters": { "q": "...", "location": "Koramangala cafes", "gl": "in", "hl": "en" },
  "locale": { "gl": "in", "hl": "en", "matched": "koramangala" },
  "entities": ["koramangala"], "query_class": "local" }

// inferring_freshness
{ "freshness": "recent",
  "signals": ["temporal language: recent", "engine volatility_prior: 7d"],
  "per_engine": { "google_maps": "recent", ... } }

// finding_paths
{ "paths": ["google_maps>google_maps_reviews>google_maps_contributor_reviews", ...] }

// generating_candidates
{ "candidate_count": 8,
  "candidates": [{ "label": "google_maps>google_maps_reviews>...",
                   "strategy": "primary", "engines": [...], "cold_cost": 101 }],
  "single_candidate_reason": null }

// inspecting_cache
{ "warm_steps_found": 3,
  "per_candidate": [{ "plan": "google_maps>...", "warm_steps": [0, 1, 2] }] }

// calculating_marginal_cost
{ "candidates": [{ "plan": "google_maps>...", "naive_cost": 101,
                   "marginal_cost": 0 }] }

// reranking_plans
{ "cold_winner": "google_local>...", "selected": "google_maps>...",
  "changed_selection": true, "explanation": "Cache-aware replanning ..." }

// checking_budget
{ "budget": 20, "applied": true, "selected_plan_cost": 0, "note": "...",
  "reductions": [{ "type": "sampling", "step": 2,
                   "engine": "google_maps_contributor_reviews",
                   "original": 80, "reduced": 12,
                   "impact_note": "Contributor sampling reduced; ..." }] }

// executing, running
{ "step": 2, "engine": "google_maps_contributor_reviews", "fan_out": 80 }

// executing, step_complete
{ "step": 2, "engine": "google_maps_contributor_reviews", "cache_layer": "exact",
  "credits": 0, "latency_ms": 41.2, "status": "succeeded" }

// complete
{ "run_id": "run_01M3...", "plan_id": "plan_01M3...", "status": "succeeded",
  "credits_spent": 0, "credits_saved": 101, "naive_cost": 101, "marginal_cost": 0,
  "cache_summary": { "exact": 101, ... }, "mode": "mock", "changed_selection": true,
  "summary": { "result_key": "reviews", "count": 20, "items": [...] } }

// error
{ "code": "BUDGET_EXHAUSTED", "message": "The configured SerpFlow budget ..." }
```

- **That is the data the UI pipeline renders.** It is not a progress bar with labels on it
- **`complete.summary`** is the same result summary `POST /v1/search` returns, including `notice` when a billed search found nothing ([plan and execute](overview.md#plan-and-execute))
- Field meanings: [reductions and impact notes](../architecture/marginal-replanning.md#every-reduction-carries-an-impact-note), [`changed_selection`](../architecture/marginal-replanning.md#what-changed_selection-means), [cache layers](../architecture/caching.md)

## Reconnecting

- **The server buffers the last 400 frames per run** in process
- **Mirrored into [Redis](../operations/redis.md#what-lives-in-it)** under `sf:stream:<run_id>`, where the copy expires 15 minutes after the run's last frame, so a client can attach to a run started by a different worker process
- **On reconnect, send the last sequence you saw:**

```http
GET /v1/runs/{id}/stream
Last-Event-ID: 14
```

- Frames up to and including 14 are skipped
- **Attaching to a run that already finished** replays the whole buffer and then closes, so a late client still sees the complete history
- Duplicate frames after a reconnect: [troubleshooting](../operations/troubleshooting.md#reconnect-replays-frames-i-already-saw)

## Authentication

`EventSource` cannot set headers, so this endpoint accepts a **short-lived access token** as a query parameter:

```js
new EventSource("/v1/runs/" + runId + "/stream?access_token=" + accessToken);
```

- **Only an access token.** Never an API key, never a refresh token ([`app/api/deps.py`](../../backend/app/api/deps.py))
- **Access tokens live 15 minutes**, which is long enough to open a stream; an open stream is not cut when the token expires
- **Non-browser clients** should use the `X-API-Key` header as normal. Every credential shape: [authentication](overview.md#authentication)
- A 401 from the browser: [troubleshooting](../operations/troubleshooting.md#eventsource-gets-a-401)

## Clients

```python
from serpflow import SerpFlow

client = SerpFlow(api_key="sf_test_...")
for event in client.stream("review rings among Koramangala cafes", budget=20):
    print(event.stage, event.status, round(event.elapsed_ms), "ms")
```

```typescript
import { SerpFlow } from "@serpflow/sdk";

const client = new SerpFlow({ apiKey: "sf_test_..." });
for await (const event of client.stream("review rings among Koramangala cafes", 20)) {
  console.log(event.stage, event.status);
}
```

```bash
curl -N -H "X-API-Key: $SERPFLOW_API_KEY" \
  http://localhost:8000/v1/runs/run_01M3.../stream
```

- **Neither SDK is published yet.** Install them from a checkout: [Python](../sdks/python.md#install), [TypeScript](../sdks/typescript.md#install)
- **Both skip heartbeats and return after `complete` or `error`.** A failed run arrives as an `error` event, not an exception. See [Python streaming](../sdks/python.md#streaming) and [TypeScript streaming](../sdks/typescript.md#streaming)
- **The console** uses `useRunStream`, which opens an `EventSource` with `?access_token=` and drops heartbeats ([`frontend/src/hooks/useRunStream.ts`](../../frontend/src/hooks/useRunStream.ts))

## Behind a proxy

**Buffering must be off**, or frames are held until the response ends and the whole point is lost. The bundled nginx config does this ([`frontend/nginx.conf`](../../frontend/nginx.conf)):

```nginx
location ~ ^/v1/runs/[^/]+/stream$ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding off;
    proxy_read_timeout 10m;
}
```

- **The response also sends `X-Accel-Buffering: no` and `Cache-Control: no-store`**, which nginx honours even without the rule above
- **Behind Caddy**, use `flush_interval -1`. See [put TLS in front](../deployment/deployment-guide.md#9-put-tls-in-front)
- Frames arriving all at once: [troubleshooting](../operations/troubleshooting.md#the-stream-arrives-all-at-once-at-the-end)

## Related

- [API overview](overview.md#runs): the other runs routes, and the permissions they need
- [Worked examples](examples.md#watch-it-happen): starting a streamed search with `curl` and tailing it
- [Frontend: the pipeline animation](../architecture/frontend.md#the-pipeline-animation): how the console paces and renders these frames
- [The planner](../architecture/planner.md): the four stages that emit the first ten frames
- [ADR 0007](../adr/0007-interactive-search-bypasses-kafka.md): why a streamed search runs in-process, not through Kafka
- [Production: behind a reverse proxy](../deployment/production.md#behind-a-reverse-proxy): proxy settings for a deployment
- [Troubleshooting: streaming](../operations/troubleshooting.md#streaming): buffering, 401s and duplicate frames
- [Redis](../operations/redis.md#what-lives-in-it): the frame mirror that lets another worker replay a run
- [Architecture overview](../architecture/overview.md#request-lifecycle): the request lifecycle these frames narrate

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [API overview](../api/overview.md) | [Docs index](../README.md) | [Worked examples](../api/examples.md) |
