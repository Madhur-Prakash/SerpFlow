"""Content-addressable payload storage (section 56).

Large SERP payloads do not belong in PostgreSQL. They go to S3-compatible
object storage (MinIO locally), and PostgreSQL holds only ``payload_ref``.
Keys are the SHA-256 of the body, so two identical responses - which is common
once engines are cached and replayed - deduplicate to one object.

Two backends: ``filesystem`` (zero-dependency default, so ``make dev`` works
without MinIO) and ``s3``.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import content_address

log = get_logger("serpflow.storage")


class ObjectStore(Protocol):
    backend: str

    async def put_json(self, payload: dict[str, Any]) -> tuple[str, int]:
        """Store a payload. Returns ``(payload_ref, byte_length)``."""
        ...

    async def get_json(self, ref: str) -> dict[str, Any] | None: ...

    async def delete(self, ref: str) -> bool: ...

    async def health(self) -> dict[str, Any]: ...


def _encode(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
    return gzip.compress(raw, compresslevel=6)


def _decode(blob: bytes) -> dict[str, Any]:
    try:
        raw = gzip.decompress(blob)
    except (OSError, gzip.BadGzipFile):
        raw = blob
    return json.loads(raw.decode("utf-8"))


def _ref_to_path(ref: str) -> str:
    digest = ref.split(":", 1)[-1]
    return digest[:2] + "/" + digest[2:4] + "/" + digest + ".json.gz"


class FilesystemObjectStore:
    backend = "filesystem"

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.storage_local_path)

    def _path(self, ref: str) -> Path:
        return self.root / _ref_to_path(ref)

    async def put_json(self, payload: dict[str, Any]) -> tuple[str, int]:
        blob = _encode(payload)
        ref = content_address(blob)
        path = self._path(ref)
        if path.exists():
            # Content-addressable: an identical body is already stored.
            return ref, path.stat().st_size
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, blob)
        return ref, len(blob)

    async def get_json(self, ref: str) -> dict[str, Any] | None:
        path = self._path(ref)
        if not path.exists():
            return None
        blob = await asyncio.to_thread(path.read_bytes)
        return _decode(blob)

    async def delete(self, ref: str) -> bool:
        path = self._path(ref)
        if not path.exists():
            return False
        await asyncio.to_thread(path.unlink)
        return True

    async def health(self) -> dict[str, Any]:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            objects = sum(1 for _ in self.root.rglob("*.json.gz")) if self.root.exists() else 0
            return {
                "backend": self.backend,
                "status": "ok",
                "root": str(self.root),
                "objects": objects,
            }
        except OSError as exc:
            return {"backend": self.backend, "status": "error", "detail": str(exc)}


class S3ObjectStore:
    backend = "s3"

    def __init__(self) -> None:
        import boto3

        self.bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self.bucket)
            except Exception as exc:  # pragma: no cover - surfaced in /readyz
                log.warning(
                    "object storage bucket unavailable",
                    extra={"event": "storage.bucket_error", "detail": type(exc).__name__},
                )

    async def put_json(self, payload: dict[str, Any]) -> tuple[str, int]:
        blob = _encode(payload)
        ref = content_address(blob)
        key = _ref_to_path(ref)

        def _put() -> None:
            # Content-addressed: if the object is already there it is byte
            # identical, so a failed head is the only signal we need.
            with contextlib.suppress(Exception):
                self._client.head_object(Bucket=self.bucket, Key=key)
                return
            self._client.put_object(
                Bucket=self.bucket, Key=key, Body=blob, ContentType="application/gzip"
            )

        await asyncio.to_thread(_put)
        return ref, len(blob)

    async def get_json(self, ref: str) -> dict[str, Any] | None:
        key = _ref_to_path(ref)

        def _get() -> bytes | None:
            try:
                response = self._client.get_object(Bucket=self.bucket, Key=key)
                return response["Body"].read()
            except Exception:
                return None

        blob = await asyncio.to_thread(_get)
        return _decode(blob) if blob else None

    async def delete(self, ref: str) -> bool:
        key = _ref_to_path(ref)

        def _delete() -> bool:
            try:
                self._client.delete_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_delete)

    async def health(self) -> dict[str, Any]:
        def _check() -> dict[str, Any]:
            try:
                self._client.head_bucket(Bucket=self.bucket)
                return {"backend": self.backend, "status": "ok", "bucket": self.bucket}
            except Exception as exc:
                return {"backend": self.backend, "status": "error", "detail": type(exc).__name__}

        return await asyncio.to_thread(_check)


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    if settings.storage_backend == "s3":
        try:
            return S3ObjectStore()
        except Exception as exc:
            log.warning(
                "falling back to filesystem object storage",
                extra={"event": "storage.fallback", "detail": type(exc).__name__},
            )
    return FilesystemObjectStore()


def reset_object_store() -> None:
    get_object_store.cache_clear()


__all__ = [
    "FilesystemObjectStore",
    "ObjectStore",
    "S3ObjectStore",
    "get_object_store",
    "reset_object_store",
]
