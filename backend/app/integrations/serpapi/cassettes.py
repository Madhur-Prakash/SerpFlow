"""Record / replay cassettes (section 21).

Replay mode must NEVER silently reach the network. A miss raises
``ReplayMissError`` naming the exact cassette file that is absent, because a
replay that quietly falls through to a live call is how a demo ends up
spending credits it claimed it would not.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import ReplayMissError
from app.core.logging import get_logger

log = get_logger("serpflow.cassettes")

SKIP_PARAMS = {"api_key", "output", "no_cache"}


def cassette_key(engine: str, params: dict[str, Any]) -> str:
    clean = {k: v for k, v in sorted(params.items()) if k not in SKIP_PARAMS and v is not None}
    material = engine + "|" + json.dumps(clean, sort_keys=True, default=str)
    return hashlib.blake2b(material.encode("utf-8"), digest_size=12).hexdigest()


def cassette_path(engine: str, params: dict[str, Any], *, root: str | None = None) -> Path:
    base = Path(root or settings.cassette_dir)
    return base / engine / (cassette_key(engine, params) + ".json")


class CassetteStore:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.cassette_dir)

    def path_for(self, engine: str, params: dict[str, Any]) -> Path:
        return cassette_path(engine, params, root=str(self.root))

    def exists(self, engine: str, params: dict[str, Any]) -> bool:
        return self.path_for(engine, params).exists()

    def load(self, engine: str, params: dict[str, Any]) -> dict[str, Any]:
        path = self.path_for(engine, params)
        if not path.exists():
            raise ReplayMissError(
                "No cassette recorded for engine "
                + engine
                + " with these parameters. Expected file: "
                + str(path)
                + ". Record it first with SERPFLOW_MODE=record, or switch to mock "
                + "by using a test API key.",
                details={
                    "engine": engine,
                    "expected_cassette": str(path),
                    "cassette_key": cassette_key(engine, params),
                    "parameters": {k: v for k, v in params.items() if k not in SKIP_PARAMS},
                },
            )
        with path.open("r", encoding="utf-8") as handle:
            record = json.load(handle)
        return record.get("payload", record)

    def save(
        self,
        engine: str,
        params: dict[str, Any],
        payload: dict[str, Any],
        *,
        http_status: int = 200,
        latency_ms: float = 0.0,
    ) -> Path:
        path = self.path_for(engine, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "engine": engine,
            "parameters": {k: v for k, v in sorted(params.items()) if k not in SKIP_PARAMS},
            "recorded_at": datetime.now(UTC).isoformat(),
            "http_status": http_status,
            "latency_ms": round(latency_ms, 2),
            "cassette_key": cassette_key(engine, params),
            "payload": payload,
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=False, ensure_ascii=False)
        log.info(
            "cassette recorded",
            extra={"event": "cassette.recorded", "engine": engine, "path": str(path)},
        )
        return path

    def index(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.root.exists():
            return out
        for path in sorted(self.root.rglob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    record = json.load(handle)
            except (OSError, ValueError):
                continue
            out.append(
                {
                    "engine": record.get("engine", path.parent.name),
                    "cassette_key": record.get("cassette_key", path.stem),
                    "recorded_at": record.get("recorded_at"),
                    "parameters": record.get("parameters", {}),
                    "path": str(path),
                    "bytes": path.stat().st_size,
                }
            )
        return out

    def count(self) -> int:
        if not self.root.exists():
            return 0
        return sum(1 for _ in self.root.rglob("*.json"))


__all__ = ["CassetteStore", "cassette_key", "cassette_path"]
