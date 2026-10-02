"""Run event bus backing Server-Sent Events (sections 42, 69).

Every event the UI pipeline animates comes from here, and every event here is
emitted by a real backend stage transition. Nothing is synthesised on a timer.

Two paths, because a client can attach at any moment:

* a buffer per run, so a client attaching mid-flight (or after completion)
  replays everything it missed before tailing live events
* an in-process fan-out queue per subscriber for live delivery

The buffer is mirrored into Redis when it is available, so a client can attach
to a run started by a different worker process.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.services.cache.redis_client import STREAM_PREFIX, get_redis

log = get_logger("serpflow.stream")

BUFFER_LIMIT = 400
BUFFER_TTL_SECONDS = 900
HEARTBEAT_SECONDS = 15.0


@dataclass(slots=True)
class RunEvent:
    """One SSE frame. Section 42 requires at minimum stage, status, elapsed_ms
    and detail."""

    stage: str
    status: str
    elapsed_ms: float
    detail: dict[str, Any] = field(default_factory=dict)
    sequence: int = 0
    run_id: str = ""
    event_type: str = "stage"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "detail": self.detail,
            "sequence": self.sequence,
            "run_id": self.run_id,
            "type": self.event_type,
        }

    def to_sse(self) -> dict[str, str]:
        return {
            "event": self.event_type,
            "id": str(self.sequence),
            "data": json.dumps(self.to_dict(), default=str),
        }


class RunEventBus:
    def __init__(self) -> None:
        self._buffers: dict[str, deque[RunEvent]] = defaultdict(lambda: deque(maxlen=BUFFER_LIMIT))
        self._subscribers: dict[str, list[asyncio.Queue[RunEvent | None]]] = defaultdict(list)
        self._sequence: dict[str, int] = defaultdict(int)
        self._finished: dict[str, float] = {}
        self._started: dict[str, float] = {}

    def start(self, run_id: str) -> None:
        self._started[run_id] = time.perf_counter()
        self._buffers[run_id].clear()
        self._sequence[run_id] = 0
        self._finished.pop(run_id, None)

    async def publish(
        self,
        run_id: str,
        stage: str,
        status: str,
        detail: dict[str, Any] | None = None,
        *,
        event_type: str = "stage",
    ) -> RunEvent:
        started = self._started.get(run_id)
        elapsed = (time.perf_counter() - started) * 1000.0 if started else 0.0
        if detail and "elapsed_ms" in detail:
            with contextlib.suppress(TypeError, ValueError):
                elapsed = float(detail["elapsed_ms"])

        self._sequence[run_id] += 1
        event = RunEvent(
            stage=stage,
            status=status,
            elapsed_ms=elapsed,
            detail=detail or {},
            sequence=self._sequence[run_id],
            run_id=run_id,
            event_type=event_type,
        )
        self._buffers[run_id].append(event)

        for queue in list(self._subscribers.get(run_id, [])):
            # A slow consumer must never stall the executor.
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

        await self._mirror(run_id, event)
        return event

    async def _mirror(self, run_id: str, event: RunEvent) -> None:
        # Redis is optional for streaming; the in-process buffer still works
        # for a single-worker deployment.
        with contextlib.suppress(Exception):
            client = get_redis()
            key = STREAM_PREFIX + run_id
            await client.rpush(key, json.dumps(event.to_dict(), default=str))
            await client.ltrim(key, -BUFFER_LIMIT, -1)
            await client.expire(key, BUFFER_TTL_SECONDS)

    async def finish(self, run_id: str, detail: dict[str, Any] | None = None) -> None:
        await self.publish(run_id, "complete", "complete", detail or {}, event_type="complete")
        self._finished[run_id] = time.time()
        for queue in list(self._subscribers.get(run_id, [])):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    async def fail(self, run_id: str, code: str, message: str) -> None:
        await self.publish(
            run_id,
            "error",
            "failed",
            {"code": code, "message": message},
            event_type="error",
        )
        self._finished[run_id] = time.time()
        for queue in list(self._subscribers.get(run_id, [])):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    def is_finished(self, run_id: str) -> bool:
        return run_id in self._finished

    async def history(self, run_id: str) -> list[RunEvent]:
        buffered = list(self._buffers.get(run_id, []))
        if buffered:
            return buffered
        try:
            raw = await get_redis().lrange(STREAM_PREFIX + run_id, 0, -1)
        except Exception:
            return []
        out: list[RunEvent] = []
        for item in raw:
            try:
                payload = json.loads(item)
            except ValueError:
                continue
            out.append(
                RunEvent(
                    stage=payload.get("stage", ""),
                    status=payload.get("status", ""),
                    elapsed_ms=float(payload.get("elapsed_ms", 0.0)),
                    detail=payload.get("detail") or {},
                    sequence=int(payload.get("sequence", 0)),
                    run_id=run_id,
                    event_type=payload.get("type", "stage"),
                )
            )
        return out

    async def subscribe(self, run_id: str, *, last_event_id: int = 0) -> AsyncIterator[RunEvent]:
        """Replay what was missed, then tail live events."""
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue(maxsize=512)
        self._subscribers[run_id].append(queue)
        try:
            for event in await self.history(run_id):
                if event.sequence > last_event_id:
                    yield event
                    if event.event_type in ("complete", "error"):
                        return

            if self.is_finished(run_id):
                return

            while True:
                pending: Awaitable[RunEvent | None] = queue.get()
                try:
                    received = await asyncio.wait_for(pending, timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield RunEvent(
                        stage="heartbeat",
                        status="running",
                        elapsed_ms=0.0,
                        run_id=run_id,
                        event_type="heartbeat",
                    )
                    continue
                if received is None:
                    return
                yield received
                if received.event_type in ("complete", "error"):
                    return
        finally:
            subscribers = self._subscribers.get(run_id, [])
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers:
                self._subscribers.pop(run_id, None)

    def cleanup(self, older_than_seconds: int = BUFFER_TTL_SECONDS) -> int:
        cutoff = time.time() - older_than_seconds
        stale = [run_id for run_id, at in self._finished.items() if at < cutoff]
        for run_id in stale:
            self._finished.pop(run_id, None)
            self._buffers.pop(run_id, None)
            self._sequence.pop(run_id, None)
            self._started.pop(run_id, None)
        return len(stale)


bus = RunEventBus()


def progress_for(run_id: str):
    """Adapter matching the planner and executor ``ProgressFn`` signature."""

    async def _progress(stage: str, status: str, detail: dict[str, Any]) -> None:
        await bus.publish(run_id, stage, status, detail)

    return _progress


__all__ = ["BUFFER_LIMIT", "HEARTBEAT_SECONDS", "RunEvent", "RunEventBus", "bus", "progress_for"]
