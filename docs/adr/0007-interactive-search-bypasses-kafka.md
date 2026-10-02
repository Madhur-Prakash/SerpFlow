# 0007. Interactive search does not go through Kafka

**Status** Accepted

## Context

The stack includes Kafka, and there is a strong pull to route everything
through it. A request arrives, a message is produced, a worker consumes it,
executes the run and publishes progress; the client subscribes to the progress
stream. It looks event-driven, it looks scalable, and it is how a lot of
systems with a broker in them end up working.

## Decision

`POST /v1/search` executes **in-process**, including the streaming variant.

```
Kafka          scheduled runs, bulk runs, retries, webhook-triggered runs,
               cache refresh, credential validation, quota reconciliation,
               analytics rollups, alert fan-out, catalog reload

Not Kafka      interactive POST /v1/search
```

With `"stream": true` the endpoint returns `202` and a `stream_url`, then runs
the plan in the same process and emits SSE frames from it. The client tails
`GET /v1/runs/{id}/stream`.

## Alternatives rejected

**Produce to Kafka, consume in a worker, stream from Redis pub/sub.** Adds a
broker round trip, a consumer scheduling delay and a pub/sub hop to a request
whose caller is already blocked waiting. It introduces a failure mode — broker
unavailable — for a path that does not otherwise have one. And it buys nothing:
the work is not deferrable, not batchable, and not retryable in a way the
caller would not rather know about immediately.

**Everything through Kafka for architectural consistency.** Consistency is not
a benefit when the two workloads are genuinely different. A synchronous
user-facing request and a nightly bulk job have different latency budgets,
different failure semantics and different retry behaviour.

## Cost

Two execution paths to maintain, and the SSE buffer has to work across workers
because the run may not be on the process the client reconnects to.

That is handled: the frame buffer is mirrored into Redis, and `Last-Event-ID`
resumption works across a reconnect that lands on a different worker. It is
real complexity, accepted in exchange for not putting a broker in the latency
path of the product's main endpoint.

A second consequence, which is a benefit: because nothing user-facing depends
on Kafka, a broker outage degrades rather than fails. The producer logs
`kafka.degraded` once and returns, `/readyz` reports degraded rather than 503,
and search keeps working.

## See also

- [Kafka operations](../operations/kafka.md)
- [Streaming](../api/streaming.md)
