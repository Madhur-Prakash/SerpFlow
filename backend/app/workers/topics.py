"""Create every Kafka topic (``make kafka-topics``).

Idempotent: topics that already exist are left alone.
"""

from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.logging import setup_logging
from app.workers.kafka import ALL_TOPICS, ensure_topics


async def run() -> int:
    setup_logging()
    result = await ensure_topics()
    print("")
    print("  bootstrap servers  " + settings.kafka_bootstrap_servers)
    print("  status             " + str(result.get("status")))
    if result.get("detail"):
        print("  detail             " + str(result["detail"]))
    created = result.get("created") or []
    existing = result.get("existing") or []
    for topic in ALL_TOPICS:
        state = "created" if topic in created else ("exists" if topic in existing else "pending")
        print("  " + topic.ljust(34) + state)
    print("")
    return 0 if result.get("status") == "ok" else 1


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
