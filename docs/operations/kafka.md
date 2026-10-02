# Kafka

Kafka 4.x in **KRaft mode**. No ZooKeeper, and there will not be one: ZooKeeper
is removed in Kafka 4.

Implementation: [`app/workers/`](../../backend/app/workers).

## What goes through it, and what does not

This is the distinction that matters most.

```
Kafka            scheduled runs, bulk runs, retries, webhook-triggered runs,
                 cache refresh, credential validation, quota reconciliation,
                 analytics rollups, alert fan-out, catalog reload

Not Kafka        interactive POST /v1/search
```

Interactive search executes **in-process**, including the streaming variant. A
broker in that path would add latency and a failure mode in exchange for
nothing: the caller is already waiting on the response, and the SSE stream is
served from the same process that is doing the work.

Putting a synchronous user-facing request through a queue to look
event-driven is a common mistake. Kafka is here for the work that genuinely is
asynchronous.

## Topics

Eight, three partitions each, created by `make kafka-topics`:

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

Creation is idempotent; an existing topic is left alone.

```bash
make kafka-topics
```

```
  bootstrap servers  localhost:9092
  status             ok
  serpflow.runs.execute              created
  serpflow.cache.refresh             created
  ...
```

Auto-creation is on in the compose broker as a safety net, but topics are
created explicitly so partition counts are intentional rather than defaulted.

## Running consumers

```bash
make worker        # python -m app.workers.runner
```

The runner ensures topics, then starts one consumer loop per topic from the
`HANDLERS` map in
[`consumers/handlers.py`](../../backend/app/workers/consumers/handlers.py).
All eight consumers share the `serpflow-workers` group, so scaling out
distributes partitions across processes.

Scale the workers independently of the API. They are different workloads: the
API is latency-sensitive and bursty, the workers are throughput-oriented and
steady.

## Degradation

If the broker is unreachable, the producer logs `kafka.degraded` **once** and
returns. It does not raise, does not retry in a tight loop, and does not log
the same failure per message.

```python
except Exception as exc:
    if not _degraded:
        log.warning("kafka degraded", extra={"event": "kafka.degraded", ...})
        _degraded = True
```

The synchronous path is unaffected, because nothing user-facing depends on the
broker. `/readyz` reports Kafka as degraded rather than returning 503, for the
same reason: a broker outage should not take the API down when the API does not
need the broker to serve a search.

`KAFKA_ENABLED=false` turns the whole thing off cleanly, which is what the test
suite uses.

Recovery is automatic: the next successful send clears `_degraded` and logs
that it recovered.

## Listeners

The compose broker advertises two client listeners, and this is the detail that
costs people an afternoon:

```yaml
KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,INTERNAL://0.0.0.0:19092
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092,INTERNAL://kafka:19092
KAFKA_INTER_BROKER_LISTENER_NAME: INTERNAL
```

`PLAINTEXT` advertises `localhost:9092` for a process on the host — `make
worker`, the test suite, `kafka-console-consumer`. `INTERNAL` advertises
`kafka:19092` for containers on the compose network.

One listener cannot advertise an address that is correct from both sides. The
failure mode when it is wrong is nasty: the connection succeeds, metadata
returns an address the client cannot reach, and the producer hangs until its
timeout with no useful error.

Use `KAFKA_BOOTSTRAP_SERVERS=localhost:9092` from the host and
`kafka:19092` from a container. `docker-compose.yml` already sets the latter
for the backend service.

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

The consumer-group description is the one to reach for first. Growing `LAG`
means the workers are not keeping up or are not running at all.

## Metrics

```
serpflow_kafka_messages_total{topic, direction, status}
```

`direction` is `produced` or `consumed`; `status` is `ok` or `error`. A
produced count that keeps climbing with no matching consumed count means the
workers are down.

## Production

The compose broker is a single KRaft node with replication factor 1. That is a
demo topology, not a production one.

For a real deployment:

- At least three brokers, and raise the replication factor on every topic to 3
  with `min.insync.replicas=2`.
- Separate the controller quorum from the broker role on larger clusters.
- Size partitions for consumer parallelism: three is the floor, and a topic
  cannot be consumed by more processes in one group than it has partitions.
- Set retention per topic. `serpflow.analytics` can be short;
  `serpflow.runs.execute` should outlive a worker outage.
- TLS and SASL between clients and brokers.

## Related

- [Docker](../deployment/docker.md)
- [Production](../deployment/production.md)
- [Observability](observability.md)
- [Troubleshooting](troubleshooting.md)
