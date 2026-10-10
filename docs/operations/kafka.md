# Kafka

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="Kafka: 4.0 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <a href="../../backend/app/workers"><img alt="source: app/workers" src="https://img.shields.io/badge/source-app%2Fworkers-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Kafka** · page 33 of 50

- **Kafka 4.x in KRaft mode**
- **No ZooKeeper, and there will not be one:** ZooKeeper is removed in Kafka 4
- Implementation: [`app/workers/`](../../backend/app/workers)

## What goes through it, and what does not

**This is the distinction that matters most.**

```
Kafka            scheduled runs, bulk runs, retries, webhook-triggered runs,
                 cache refresh, credential validation, quota reconciliation,
                 analytics rollups, alert fan-out, catalog reload

Not Kafka        interactive POST /v1/search
```

- **Interactive search executes in-process**, including the streaming variant
- **A broker in that path would add latency and a failure mode for nothing:**
  - the caller is already waiting on the response
  - the SSE stream is served from the same process doing the work
- **Putting a synchronous user-facing request through a queue to look event-driven is a common mistake.** Kafka is here for work that genuinely is asynchronous. See [ADR 0007](../adr/0007-interactive-search-bypasses-kafka.md)

## Topics

**Eight, three partitions each**, defined in `app/workers/kafka.py` and created by `make kafka-topics`:

| Topic | Carries |
| --- | --- |
| `serpflow.runs.execute` | scheduled, bulk, retried, webhook-triggered runs |
| `serpflow.cache.refresh` | proactive refresh of entries about to expire |
| `serpflow.credentials.validate` | background credential validation |
| `serpflow.quota.reconcile` | upstream SerpApi quota reconciliation |
| `serpflow.analytics` | rollups feeding the dashboard |
| `serpflow.alerts` | budget, quota and false-hit alerts |
| `serpflow.webhooks` | outbound delivery with retry |
| `serpflow.catalog` | catalog version reload across workers |

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

- **Creation is idempotent:** an existing topic is left alone
- **Auto-creation is on in the compose broker** as a safety net, but topics are created explicitly so partition counts are **intentional**, not defaulted

## Running consumers

```bash
make worker        # python -m app.workers.runner
```

- **The runner ensures topics**, then starts one consumer loop per topic from the `HANDLERS` map in [`consumers/handlers.py`](../../backend/app/workers/consumers/handlers.py)
- **All eight consumers share the `serpflow-workers` group**, so scaling out distributes partitions across processes
- **Scale the workers independently of the API.** Different workloads:
  - the API is latency-sensitive and bursty
  - the workers are throughput-oriented and steady

## Degradation

- **If the broker is unreachable, the producer logs `kafka.degraded` once and returns**
  - it does not raise
  - it does not retry in a tight loop
  - it does not log the same failure per message

```python
except Exception as exc:
    if not _degraded:
        log.warning("kafka degraded", extra={"event": "kafka.degraded", ...})
        _degraded = True
```

- **The synchronous path is unaffected**, because nothing user-facing depends on the broker
- **`/readyz` reports Kafka as degraded**, not 503: a broker outage should not take the API down when the API does not need it to serve a search
- **`KAFKA_ENABLED=false`** turns the whole thing off cleanly; the test suite uses it
- **Recovery is automatic:** the next successful send clears `_degraded` and logs that it recovered

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
- **Use `KAFKA_BOOTSTRAP_SERVERS=localhost:9092` from the host, `kafka:19092` from a container.** `docker-compose.yml` already sets the latter for the backend

## Inspecting

```bash
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --describe --topic serpflow.runs.execute

docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group serpflow-workers

docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic serpflow.alerts --from-beginning
```

- **Reach for the consumer-group description first:** growing `LAG` means the workers are not keeping up, or not running at all

## Metrics

```
serpflow_kafka_messages_total{topic, direction, status}
```

- `direction` is `produced` or `consumed`; `status` is `ok` or `error`
- **A produced count that keeps climbing with no matching consumed count means the workers are down**

## Production

**The compose broker is a single KRaft node with replication factor 1:** a demo topology, not a production one. For a real deployment:

- **At least three brokers**, replication factor **3** on every topic, with `min.insync.replicas=2`
- **Separate the controller quorum** from the broker role on larger clusters
- **Size partitions for consumer parallelism:** three is the floor, and a topic cannot be consumed by more processes in one group than it has partitions
- **Set retention per topic:** `serpflow.analytics` can be short; `serpflow.runs.execute` should outlive a worker outage
- **TLS and SASL** between clients and brokers

## Related

- [Docker](../deployment/docker.md)
- [Production](../deployment/production.md)
- [Observability](observability.md)
- [Troubleshooting](troubleshooting.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Observability](../operations/observability.md) | [Docs index](../README.md) | [Redis](../operations/redis.md) |
