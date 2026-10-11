# Kafka

<p>
  <a href="../operations/README.md"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="Kafka: 4.0 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <a href="../../backend/app/workers"><img alt="source: app/workers" src="https://img.shields.io/badge/source-app%2Fworkers-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [Operations](../operations/README.md) › **Kafka** · page 48 of 50

- **Kafka 4.x in KRaft mode**: the compose service runs `apache/kafka:4.0.0` as a single combined broker and controller ([Docker: Kafka](../deployment/docker.md#kafka))
- **No ZooKeeper, and there will not be one:** ZooKeeper is removed in Kafka 4
- Implementation: [`app/workers/`](../../backend/app/workers): the client and topic names in [`kafka.py`](../../backend/app/workers/kafka.py), typed producers in [`producers/`](../../backend/app/workers/producers/__init__.py), handlers in [`consumers/handlers.py`](../../backend/app/workers/consumers/handlers.py)

## What goes through it, and what does not

**This is the distinction that matters most.**

```
Kafka            scheduled runs, bulk runs, retries, webhook-triggered runs,
                 cache refresh, credential validation, quota reconciliation,
                 analytics rollups, alert fan-out, catalog reload

Not Kafka        interactive POST /v1/search
```

- **Interactive search executes in-process**, including the [streaming](../api/streaming.md) variant ([plan and execute](../api/overview.md#plan-and-execute))
- **A broker in that path would add latency and a failure mode for nothing:**
  - the caller is already waiting on the response
  - the SSE stream is served from the same process doing the work
- **Putting a synchronous user-facing request through a queue to look event-driven is a common mistake.** Kafka is here for work that genuinely is asynchronous.

**What actually publishes at HEAD** is narrower than what the topics are for:

| Publisher | Topic |
| --- | --- |
| `POST /v1/credentials/reconcile-quota` | `serpflow.quota.reconcile` |
| `POST /v1/credentials/revalidate` | `serpflow.credentials.validate` |
| the `serpflow.alerts` consumer, after storing an alert | `serpflow.webhooks` |

- **Both endpoints answer `ok: false`** with "Kafka is unavailable; ... was not queued." when the broker is down ([`app/api/v1/credentials.py`](../../backend/app/api/v1/credentials.py), [identity and access endpoints](../api/overview.md#identity-and-access))
- **The other topics have consumers and typed producers** (`queue_run`, `queue_cache_refresh`, `queue_alert`, `queue_analytics_rollup`, `queue_catalog_reload` in [`producers/`](../../backend/app/workers/producers/__init__.py)), **but nothing in the request path calls them yet.** There is no scheduler in the repository
- **So in-app alerts are not routed through Kafka today.** Budget threshold and exhaustion alerts are written straight to the [`alerts` table](../database/schema.md#governance) by the budget service ([`app/services/budgets/service.py`](../../backend/app/services/budgets/service.py)), and so never reach a notification channel

## Topics

**Eight, three partitions each**, named in [`app/workers/kafka.py`](../../backend/app/workers/kafka.py) (`ALL_TOPICS`) and created by [`app/workers/topics.py`](../../backend/app/workers/topics.py) (`make kafka-topics`):

| Topic | Carries | What the consumer does |
| --- | --- | --- |
| `serpflow.runs.execute` | scheduled, bulk, retried, webhook-triggered runs | `execute_background_run` for a `run_id` still `pending`, `queued` or `planning` |
| `serpflow.cache.refresh` | a fresh result for a cached entry | [adaptive TTL](../architecture/caching.md#adaptive-ttl): compares top results, rewrites the entry's TTL and expiry, writes a `ttl_observations` row, observes `serpflow_adaptive_ttl_seconds` |
| `serpflow.credentials.validate` | background credential validation | validates one credential, or every unrevoked one; a failure opens a `credential.validation_failed` alert |
| `serpflow.quota.reconcile` | upstream SerpApi quota reconciliation | snapshots each credential's quota, sets the two quota gauges, opens an `upstream.quota_divergence` alert past 5 credits of divergence |
| `serpflow.analytics` | rollups | logs `analytics.rollup` with a one-day dashboard snapshot; writes nothing |
| `serpflow.alerts` | alerts | stores an `alerts` row unless an open one has the same `dedupe_key`, then republishes to `serpflow.webhooks` |
| `serpflow.webhooks` | outbound delivery | for each enabled channel whose `events` match: an HMAC-signed POST for `webhook` and `slack`, an [email](email.md#audiences) for `email`; one `webhook_deliveries` row each, **one attempt, no retry** |
| `serpflow.catalog` | catalog version changes | `reload_catalog()` in the one process that receives it |

- **Webhook signatures:** `x-serpflow-signature` is HMAC-SHA256 of the body, keyed by the channel's stored secret hash, and `x-serpflow-event` names the event. The POST times out after 10 s
- **A catalog reload reaches one process, not every worker.** Every consumer of a topic shares one group, so Kafka hands each message to a single member. Restart the API and workers to change the catalog everywhere ([catalog versioning](../architecture/catalog.md#versioning))

```bash
make kafka-topics                                   # from the host
docker compose exec backend python -m app.workers.topics   # in a container
```

```
  bootstrap servers  localhost:9092
  status             ok
  serpflow.runs.execute              created
  serpflow.cache.refresh             created
  ...
```

- **Creation is idempotent:** an existing topic is left alone. The script exits 1 if the broker cannot be reached
- **Replication factor is hard-coded to 1** in `ensure_topics`, which suits the single-node compose broker and nothing else (see [production](#production))
- **Auto-creation is on in the compose broker** as a safety net, but topics are created explicitly so partition counts are **intentional**, not defaulted

## Running consumers

```bash
make worker        # python -m app.workers.runner
```

- **The runner ensures topics**, then starts one consumer loop per topic from the `HANDLERS` map in [`consumers/handlers.py`](../../backend/app/workers/consumers/handlers.py) ([`runner.py`](../../backend/app/workers/runner.py))
  - if the topics cannot be ensured it logs `worker.kafka_unreachable` and exits 1
- **The API runs the same consumers in-process** when `KAFKA_ENABLED` is true, started in the lifespan after the [startup bootstrap](bootstrap.md#what-happens). A failure to start logs `app.kafka_unavailable` and the API serves on
- **Each topic has its own consumer group, `serpflow-workers.<topic>`** (`KAFKA_CONSUMER_GROUP` plus the topic name), so scaling out distributes that topic's partitions across processes, the API's in-process consumers included
- **Offsets are committed by hand, after the handler returns:**
  - a process that dies mid-message replays it on restart
  - a handler that **raises** is logged as `kafka.handler_failed`, counted as an error, and its offset is committed anyway: the message is **not** retried
- **A lost broker connection** logs `kafka.consumer_error` and that topic's loop reconnects after 5 s
- **New groups start from `earliest`**, so a first worker consumes whatever the topics already hold
- **Scale the workers independently of the API.** Different workloads:
  - the API is latency-sensitive and bursty
  - the workers are throughput-oriented and steady
- **There is no switch that turns off only the API's consumers.** The runner's docstring suggests `KAFKA_ENABLED=false` on the API, but that flag also disables the API's producer, so the two credential endpoints above would stop queueing

## Degradation

- **If the producer cannot start, it logs `kafka.degraded` once and `publish` returns `False`**
  - it does not raise
  - it does not retry in a loop of its own
  - it does not log the same failure per message
  - the message is **dropped**, and `serpflow_kafka_messages_total{direction="produce", status="skipped"}` counts it

```python
except Exception as exc:
    if not _degraded:
        log.warning("kafka producer unavailable, background events will be dropped",
                    extra={"event": "kafka.degraded", ...})
        _degraded = True
    return None
```

- **A send that fails once the producer is up** is different: it logs `kafka.publish_failed` per message, with the topic, and counts `status="error"`
- **The producer is idempotent with `acks=all`** and a 10 s request timeout
- **The synchronous path is unaffected**, because nothing user-facing depends on the broker
- **`/readyz` reports Kafka as degraded**, not 503: a broker outage should not take the API down when the API does not need it to serve a search ([health](observability.md#health))
- **`KAFKA_ENABLED=false`** turns the whole thing off cleanly; the test suite uses it. `/readyz` then reports Kafka as degraded too
- **Recovery is automatic but silent:** every later `publish` tries to start the producer again, and the first that succeeds clears `_degraded`. No "recovered" line is logged

## Listeners

The compose broker advertises **two client listeners**, and this is the detail that costs people an afternoon:

```yaml
KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,INTERNAL://0.0.0.0:19092
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092,INTERNAL://kafka:19092
KAFKA_INTER_BROKER_LISTENER_NAME: INTERNAL
```

| Listener | Advertises | For |
| --- | --- | --- |
| `PLAINTEXT` | `localhost:9092` | a process on the host: `make worker`, the test suite, `kafka-console-consumer` |
| `INTERNAL` | `kafka:19092` | containers on the compose network |

- **One listener cannot advertise an address that is correct from both sides**
- **The failure mode is nasty:** the connection succeeds, metadata returns an address the client cannot reach, and the producer hangs until its timeout with no useful error
- **Use `KAFKA_BOOTSTRAP_SERVERS=localhost:9092` from the host, `kafka:19092` from a container.** `docker-compose.yml` already sets the latter for the backend ([troubleshooting: producer hangs](troubleshooting.md#producer-hangs-with-no-error))

## Inspecting

```bash
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --describe --topic serpflow.runs.execute

docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --all-groups

docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group serpflow-workers.serpflow.webhooks

docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic serpflow.alerts --from-beginning
```

- **Reach for the consumer-group description first:** growing `LAG` means the workers are not keeping up, or not running at all
- **There is no group called plain `serpflow-workers`.** Describe `--all-groups`, or one `serpflow-workers.<topic>` group

## Metrics

```
serpflow_kafka_messages_total{topic, direction, status}
```

- `direction` is `produce` or `consume`; `status` is `ok`, `error` or `skipped` (produce only: no producer, so the message was dropped)
- **A `produce` count that keeps climbing with no matching `consume` count means the consumers are down**
- **`skipped` climbing means the broker is unreachable** and background work is being dropped
- Full metric list: [observability: HTTP and Kafka](observability.md#http-and-kafka)

## Production

**The compose broker is a single KRaft node with replication factor 1:** a demo topology, not a production one. For a real deployment:

- **At least three brokers**, replication factor **3** on every topic, with `min.insync.replicas=2`
- **Create the topics yourself** at that replication factor: `make kafka-topics` always asks for 1
- **Separate the controller quorum** from the broker role on larger clusters
- **Size partitions for consumer parallelism:** three is the floor, and a topic cannot be consumed by more processes in one group than it has partitions
- **Set retention per topic:** `serpflow.analytics` can be short; `serpflow.runs.execute` should outlive a worker outage
- **TLS and SASL** between clients and brokers. The client sets neither today: `KAFKA_BOOTSTRAP_SERVERS` and `KAFKA_CLIENT_ID` are its only connection settings
- More on running it alongside the API: [production: Kafka](../deployment/production.md#kafka)

## Related

- [Docker](../deployment/docker.md#kafka): the KRaft service and its two listeners
- [Production](../deployment/production.md#kafka): brokers, replication and worker scaling for a real deployment
- [Architecture overview](../architecture/overview.md#data-stores-and-what-each-is-for): where Kafka sits among the data stores
- [Caching](../architecture/caching.md#adaptive-ttl): the TTL controller the `serpflow.cache.refresh` consumer runs
- [Email](email.md#audiences): how the webhooks consumer renders notification email
- [Observability](observability.md#http-and-kafka): `serpflow_kafka_messages_total` and the other metrics
- [Troubleshooting](troubleshooting.md#kafka): a hanging producer, `kafka.degraded`, consumer lag

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Observability](../operations/observability.md) | [Docs index](../README.md) · [Operations index](../operations/README.md) | [Redis](../operations/redis.md) |
