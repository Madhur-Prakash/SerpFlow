"""Kafka 4.x in KRaft mode - no ZooKeeper (section 43).

Kafka carries background work only: scheduled jobs, bulk operations, retries,
webhook-triggered execution, cache refresh, credential validation, analytics
aggregation, alerts, catalog updates and upstream quota reconciliation.

Interactive search does NOT go through Kafka (section 42). ``POST /v1/search``
executes synchronously and streams stage progress over SSE, because routing an
interactive request through a broker adds latency and a failure mode for no
benefit.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from app.core import metrics
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("serpflow.kafka")

TOPIC_RUNS_EXECUTE = "serpflow.runs.execute"
TOPIC_CACHE_REFRESH = "serpflow.cache.refresh"
TOPIC_CREDENTIALS_VALIDATE = "serpflow.credentials.validate"
TOPIC_ANALYTICS = "serpflow.analytics"
TOPIC_ALERTS = "serpflow.alerts"
TOPIC_WEBHOOKS = "serpflow.webhooks"
TOPIC_CATALOG = "serpflow.catalog"
TOPIC_QUOTA_RECONCILE = "serpflow.quota.reconcile"

ALL_TOPICS = (
    TOPIC_RUNS_EXECUTE,
    TOPIC_CACHE_REFRESH,
    TOPIC_CREDENTIALS_VALIDATE,
    TOPIC_ANALYTICS,
    TOPIC_ALERTS,
    TOPIC_WEBHOOKS,
    TOPIC_CATALOG,
    TOPIC_QUOTA_RECONCILE,
)

Handler = Callable[[dict[str, Any]], Awaitable[None]]

_producer: Any = None
_producer_lock = asyncio.Lock()
_degraded = False


async def get_producer() -> Any:
    """Lazily start the producer. Returns None when Kafka is unavailable."""
    global _producer, _degraded
    if not settings.kafka_enabled:
        return None
    if _producer is not None:
        return _producer
    async with _producer_lock:
        if _producer is not None:
            return _producer
        try:
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                client_id=settings.kafka_client_id,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda v: v.encode("utf-8") if v else None,
                enable_idempotence=True,
                acks="all",
                request_timeout_ms=10000,
            )
            await producer.start()
            _producer = producer
            _degraded = False
        except Exception as exc:
            if not _degraded:
                # Background delivery degrades; the synchronous path is
                # unaffected, which is exactly why it is not routed here.
                log.warning(
                    "kafka producer unavailable, background events will be dropped",
                    extra={"event": "kafka.degraded", "error": type(exc).__name__},
                )
                _degraded = True
            return None
    return _producer


async def publish(topic: str, payload: dict[str, Any], *, key: str | None = None) -> bool:
    producer = await get_producer()
    if producer is None:
        metrics.kafka_messages_total.labels(
            topic=topic, direction="produce", status="skipped"
        ).inc()
        return False
    try:
        await producer.send_and_wait(topic, payload, key=key)
        metrics.kafka_messages_total.labels(topic=topic, direction="produce", status="ok").inc()
        return True
    except Exception as exc:
        metrics.kafka_messages_total.labels(topic=topic, direction="produce", status="error").inc()
        log.warning(
            "kafka publish failed",
            extra={"event": "kafka.publish_failed", "topic": topic, "error": type(exc).__name__},
        )
        return False


async def stop_producer() -> None:
    global _producer
    if _producer is not None:
        # Shutdown is best effort: a broker that is already gone must not keep
        # the process from exiting.
        with contextlib.suppress(Exception):
            await _producer.stop()
    _producer = None


async def ping() -> bool:
    if not settings.kafka_enabled:
        return False
    return await get_producer() is not None


class KafkaConsumerRunner:
    """One consumer per topic, each with its own handler."""

    def __init__(self, handlers: Mapping[str, Handler], *, group_id: str | None = None) -> None:
        self.handlers = handlers
        self.group_id = group_id or settings.kafka_consumer_group
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        for topic, handler in self.handlers.items():
            self._tasks.append(asyncio.create_task(self._consume(topic, handler)))

    async def _consume(self, topic: str, handler: Handler) -> None:
        from aiokafka import AIOKafkaConsumer

        while not self._stopping.is_set():
            consumer = None
            try:
                consumer = AIOKafkaConsumer(
                    topic,
                    bootstrap_servers=settings.kafka_bootstrap_servers,
                    group_id=self.group_id + "." + topic,
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                    enable_auto_commit=False,
                    auto_offset_reset="earliest",
                )
                await consumer.start()
                log.info(
                    "kafka consumer started",
                    extra={"event": "kafka.consumer_started", "topic": topic},
                )
                async for message in consumer:
                    if self._stopping.is_set():
                        break
                    try:
                        await handler(message.value)
                        metrics.kafka_messages_total.labels(
                            topic=topic, direction="consume", status="ok"
                        ).inc()
                    except Exception as exc:
                        metrics.kafka_messages_total.labels(
                            topic=topic, direction="consume", status="error"
                        ).inc()
                        log.error(
                            "kafka handler failed",
                            extra={
                                "event": "kafka.handler_failed",
                                "topic": topic,
                                "error": type(exc).__name__,
                            },
                        )
                    # Commit after the handler so a crash replays the message
                    # rather than losing it.
                    await consumer.commit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "kafka consumer error, retrying",
                    extra={
                        "event": "kafka.consumer_error",
                        "topic": topic,
                        "error": type(exc).__name__,
                    },
                )
                await asyncio.sleep(5)
            finally:
                if consumer is not None:
                    with contextlib.suppress(Exception):
                        await consumer.stop()

    async def stop(self) -> None:
        self._stopping.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()


async def ensure_topics() -> dict[str, Any]:
    """Create every topic if it does not exist. Backs ``make kafka-topics``."""
    try:
        from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    except ImportError:
        return {"status": "unavailable", "detail": "aiokafka admin client not installed"}

    admin = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_bootstrap_servers, client_id=settings.kafka_client_id
    )
    created: list[str] = []
    try:
        await admin.start()
        existing = set(await admin.list_topics())
        pending = [
            NewTopic(name=t, num_partitions=3, replication_factor=1)
            for t in ALL_TOPICS
            if t not in existing
        ]
        if pending:
            await admin.create_topics(pending)
            created = [t.name for t in pending]
        return {"status": "ok", "created": created, "existing": sorted(existing & set(ALL_TOPICS))}
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}
    finally:
        with contextlib.suppress(Exception):
            await admin.close()


__all__ = [
    "ALL_TOPICS",
    "TOPIC_ALERTS",
    "TOPIC_ANALYTICS",
    "TOPIC_CACHE_REFRESH",
    "TOPIC_CATALOG",
    "TOPIC_CREDENTIALS_VALIDATE",
    "TOPIC_QUOTA_RECONCILE",
    "TOPIC_RUNS_EXECUTE",
    "TOPIC_WEBHOOKS",
    "Handler",
    "KafkaConsumerRunner",
    "ensure_topics",
    "get_producer",
    "ping",
    "publish",
    "stop_producer",
]
