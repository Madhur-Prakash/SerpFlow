# 0007. Interactive search does not go through Kafka

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/workers/kafka.py"><img alt="source: workers/kafka.py" src="https://img.shields.io/badge/source-workers%2Fkafka.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0007. Interactive search does not go through Kafka** · page 50 of 57

**Status** Accepted

## Context

- **The stack includes [Kafka](../operations/kafka.md), and there is a strong pull to route everything through it:**
  - a request arrives, a message is produced
  - a worker consumes it, executes the run, publishes progress
  - the client subscribes to the progress stream
- **It looks event-driven and scalable**, and it is how a lot of systems with a broker end up working

## Decision

**[`POST /v1/search`](../api/overview.md#plan-and-execute) executes in-process**, including the streaming variant.

```
Kafka          scheduled runs, bulk runs, retries, webhook-triggered runs,
               cache refresh, credential validation, quota reconciliation,
               analytics rollups, alert fan-out, catalog reload

Not Kafka      interactive POST /v1/search
```

- **The background side is 8 topics** ([topics](../operations/kafka.md#topics), declared in [`app/workers/kafka.py`](../../backend/app/workers/kafka.py)); none of them carries an interactive search
- **With `"stream": true`**, the endpoint returns `202` and a `stream_url`, then runs the plan **in the same process** (an `asyncio` task in [`app/api/v1/search.py`](../../backend/app/api/v1/search.py)) and emits [SSE frames](../api/streaming.md#starting-a-run-you-can-stream) from it
- The client tails `GET /v1/runs/{id}/stream`

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Produce to Kafka, consume in a worker, stream from Redis pub/sub** | Adds a broker round trip, a consumer scheduling delay and a pub/sub hop to a request whose caller is already blocked waiting. Introduces a failure mode (broker down) for a path that otherwise has none. And buys nothing: the work is not deferrable, not batchable, and not retryable in a way the caller would not rather know about immediately |
| **Everything through Kafka, for architectural consistency** | Consistency is not a benefit when the workloads genuinely differ. A synchronous user-facing request and a nightly bulk job have different latency budgets, failure semantics and retry behaviour |

## Cost

- **Two execution paths to maintain**
- **The SSE buffer has to work across workers**, because the client may reconnect to a different process
  - handled: the frame buffer is mirrored into [Redis](../operations/redis.md#what-lives-in-it), and [`Last-Event-ID` resumption](../api/streaming.md#reconnecting) works across a reconnect that lands elsewhere
  - real complexity, accepted in exchange for keeping a broker **out of the latency path** of the main endpoint
- **A consequence that is a benefit:** nothing user-facing depends on Kafka, so a broker outage **[degrades rather than fails](../operations/kafka.md#degradation)**
  - the producer logs `kafka.degraded` once and returns
  - [`/readyz`](../operations/observability.md#health) reports degraded, not 503
  - search keeps working

## See also

- [Kafka: what goes through it, and what does not](../operations/kafka.md#what-goes-through-it-and-what-does-not): the split this decision draws, topic by topic
- [Streaming: reconnecting](../api/streaming.md#reconnecting): the Redis-mirrored buffer that makes in-process streaming survive a reconnect elsewhere
- [Architecture overview: the shape of a request](../architecture/overview.md#the-shape-of-a-request): the synchronous path a search takes end to end
- [Backend: degradation](../architecture/backend.md#degradation): what each dependency's outage does to the API
- [`test_api.py`](../../backend/tests/integration/test_api.py): `test_sse_stream_replays_real_stage_events` checks the in-process stream emits real stages
- [Troubleshooting: `kafka.degraded` in the logs](../operations/troubleshooting.md#kafkadegraded-in-the-logs): why search keeps working, and what stops
- [Production: Kafka](../deployment/production.md#kafka): the broker topology the background side needs once it carries real work

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0006: The credential field is absent from sche…](../adr/0006-no-credential-field-in-schemas.md) | [Docs index](../README.md) | [ADR 0008: Rank on coverage before price](../adr/0008-coverage-before-price.md) |
