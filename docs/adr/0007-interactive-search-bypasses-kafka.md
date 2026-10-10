# 0007. Interactive search does not go through Kafka

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0007. Interactive search does not go through Kafka** · page 43 of 50

**Status** Accepted

## Context

- **The stack includes Kafka, and there is a strong pull to route everything through it:**
  - a request arrives, a message is produced
  - a worker consumes it, executes the run, publishes progress
  - the client subscribes to the progress stream
- **It looks event-driven and scalable**, and it is how a lot of systems with a broker end up working

## Decision

**`POST /v1/search` executes in-process**, including the streaming variant.

```
Kafka          scheduled runs, bulk runs, retries, webhook-triggered runs,
               cache refresh, credential validation, quota reconciliation,
               analytics rollups, alert fan-out, catalog reload

Not Kafka      interactive POST /v1/search
```

- **With `"stream": true`**, the endpoint returns `202` and a `stream_url`, then runs the plan **in the same process** and emits SSE frames from it
- The client tails `GET /v1/runs/{id}/stream`

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Produce to Kafka, consume in a worker, stream from Redis pub/sub** | Adds a broker round trip, a consumer scheduling delay and a pub/sub hop to a request whose caller is already blocked waiting. Introduces a failure mode (broker down) for a path that otherwise has none. And buys nothing: the work is not deferrable, not batchable, and not retryable in a way the caller would not rather know about immediately |
| **Everything through Kafka, for architectural consistency** | Consistency is not a benefit when the workloads genuinely differ. A synchronous user-facing request and a nightly bulk job have different latency budgets, failure semantics and retry behaviour |

## Cost

- **Two execution paths to maintain**
- **The SSE buffer has to work across workers**, because the client may reconnect to a different process
  - handled: the frame buffer is mirrored into Redis, and `Last-Event-ID` resumption works across a reconnect that lands elsewhere
  - real complexity, accepted in exchange for keeping a broker **out of the latency path** of the main endpoint
- **A consequence that is a benefit:** nothing user-facing depends on Kafka, so a broker outage **degrades rather than fails**
  - the producer logs `kafka.degraded` once and returns
  - `/readyz` reports degraded, not 503
  - search keeps working

## See also

- [Kafka operations](../operations/kafka.md)
- [Streaming](../api/streaming.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0006: The credential field is absent from sche…](../adr/0006-no-credential-field-in-schemas.md) | [Docs index](../README.md) | [ADR 0008: Rank on coverage before price](../adr/0008-coverage-before-price.md) |
