"""Standalone Kafka consumer process (``make worker``).

The API also starts these consumers in-process, which is convenient for
development. In production you run the API without them
(``KAFKA_ENABLED=false`` on the API, true here) so background work scales
independently of request traffic.

Only background work flows through here: scheduled jobs, bulk operations,
retries, webhook-triggered execution, cache refresh, credential validation,
analytics rollups, alerts, catalog reloads and upstream quota reconciliation.
Interactive search is never routed through Kafka (section 42).
"""

from __future__ import annotations

import asyncio
import signal

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.session import dispose_engine
from app.services.cache.redis_client import close_redis
from app.workers.consumers.handlers import HANDLERS
from app.workers.kafka import KafkaConsumerRunner, ensure_topics, stop_producer

log = get_logger("serpflow.worker")


async def run() -> int:
    setup_logging()
    log.info(
        "worker starting",
        extra={
            "event": "worker.startup",
            "bootstrap_servers": settings.kafka_bootstrap_servers,
            "topics": sorted(HANDLERS),
        },
    )

    topics = await ensure_topics()
    log.info("topics ensured", extra={"event": "worker.topics", **topics})
    if topics.get("status") == "error":
        log.error(
            "kafka is unreachable; the worker has nothing to consume",
            extra={"event": "worker.kafka_unreachable", "detail": topics.get("detail")},
        )
        return 1

    runner = KafkaConsumerRunner(HANDLERS)
    await runner.start()

    stopping = asyncio.Event()

    def _request_stop(*_: object) -> None:
        stopping.set()

    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows does not support add_signal_handler for every signal.
            signal.signal(sig, _request_stop)

    try:
        await stopping.wait()
    finally:
        log.info("worker stopping", extra={"event": "worker.shutdown"})
        await runner.stop()
        await stop_producer()
        await close_redis()
        await dispose_engine()
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
