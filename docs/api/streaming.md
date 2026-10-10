# Streaming

<p>
  <a href="../README.md#api"><img alt="docs: API" src="https://img.shields.io/badge/docs-API-009688?logo=readthedocs&logoColor=white"></a>
  <img alt="stages: 11" src="https://img.shields.io/badge/stages-11-009688">
  <img alt="SSE: streaming" src="https://img.shields.io/badge/SSE-streaming-555555">
  <img alt="FastAPI: 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [API](../README.md#api) › **Streaming** · page 20 of 50

```http
GET /v1/runs/{run_id}/stream
Accept: text/event-stream
```

- **One frame per real backend stage transition**
- **No timer anywhere in this path:** if the planner spends two seconds inspecting cache state, the stream is silent for two seconds

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

- **The run executes in-process**, on the same service
- **It is not handed to Kafka:** interactive search never is. A broker would add latency and a failure mode for no benefit
- The Kafka topic exists for scheduled, bulk, retried and webhook-triggered runs. See [ADR 0007](../adr/0007-interactive-search-bypasses-kafka.md)

## Frame shape

```
event: stage
id: 14
data: {"stage":"inspecting_cache","status":"complete","elapsed_ms":147.2,
       "detail":{"warm_steps_found":3,"per_candidate":[...]},
       "sequence":14,"run_id":"run_01M3...","type":"stage"}
```

- **Every frame carries at least** `stage`, `status`, `elapsed_ms` and `detail`

| `type` | Meaning |
| --- | --- |
| `stage` | A planner or executor stage changed state |
| `complete` | The run finished; the frame carries the summary |
| `error` | The run failed; the frame carries `code` and `message` |
| `heartbeat` | Sent after every 15 seconds of silence, to keep the connection open |

- **`status`** is one of `running`, `complete`, `step_complete` or `failed`

## The stage sequence

Eleven stages, then `complete`:

```
analyzing_intent             reading the request and normalising it
finding_candidates           retrieval, then the selector
synthesizing_parameters      dates, locale, entities, parameter binding
inferring_freshness          how fresh each step must be
finding_paths                walking typed dependency edges
generating_candidates        multiple competing plans
inspecting_cache             all four layers, every step of every candidate
calculating_marginal_cost    only steps needing a live call count
reranking_plans              cold ranking against marginal ranking
checking_budget              what fits, and what reduction costs
executing                    exact, semantic, archive, live
complete
```

- **`executing` emits one frame per step started and one per step finished**, so a fan-out of eighty calls reports progress instead of going quiet

## What `detail` carries

Each stage reports **what it actually produced**:

```jsonc
// finding_candidates
{ "count": 12, "engines": [...], "from_substitution": ["yelp_reviews"],
  "chosen": ["google_maps_contributor_reviews"], "rejected_count": 9,
  "provider": "mock", "model": "deterministic-v1" }

// inferring_freshness
{ "freshness": "recent",
  "signals": ["temporal language: recent", "engine volatility_prior: 7d"],
  "per_engine": { "google_maps": "recent", ... } }

// generating_candidates
{ "candidate_count": 8,
  "candidates": [{ "label": "google_maps>google_maps_reviews>...",
                   "strategy": "primary", "cold_cost": 101 }],
  "single_candidate_reason": null }

// calculating_marginal_cost
{ "candidates": [{ "plan": "google_maps>...", "naive_cost": 101,
                   "marginal_cost": 0 }] }

// reranking_plans
{ "cold_winner": "google_local>...", "selected": "google_maps>...",
  "changed_selection": true, "explanation": "Cache-aware replanning ..." }

// checking_budget
{ "budget": 20, "applied": true, "selected_plan_cost": 0,
  "reductions": [{ "engine": "google_maps_contributor_reviews",
                   "original": 80, "reduced": 12,
                   "impact_note": "Contributor sampling reduced; ..." }] }

// executing
{ "step": 2, "engine": "google_maps_contributor_reviews", "fan_out": 80,
  "cache_layer": "exact", "credits": 0, "latency_ms": 41.2 }
```

- **That is the data the UI pipeline renders.** It is not a progress bar with labels on it

## Reconnecting

- **The server buffers the last 400 frames per run, for 15 minutes**
- **Mirrored into Redis**, so a client can attach to a run started by a different worker process
- **On reconnect, send the last sequence you saw:**

```http
GET /v1/runs/{id}/stream
Last-Event-ID: 14
```

- Frames up to and including 14 are skipped
- **Attaching to a run that already finished** replays the whole buffer and then closes, so a late client still sees the complete history

## Authentication

`EventSource` cannot set headers, so this endpoint accepts a **short-lived access token** as a query parameter:

```js
new EventSource("/v1/runs/" + runId + "/stream?access_token=" + accessToken);
```

- **Only an access token.** Never an API key, never a refresh token
- **Non-browser clients** should use the `X-API-Key` header as normal

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

## Behind a proxy

**Buffering must be off**, or frames are held until the response ends and the whole point is lost. The bundled nginx config does this:

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

## Related

- [API overview](overview.md)
- [Frontend: the pipeline animation](../architecture/frontend.md#the-pipeline-animation)
- [Production: behind a reverse proxy](../deployment/production.md#behind-a-reverse-proxy)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [API overview](../api/overview.md) | [Docs index](../README.md) | [Worked examples](../api/examples.md) |
