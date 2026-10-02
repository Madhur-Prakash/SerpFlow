"""Redis connection and the hot cache layer (section 18).

Redis is the hot layer and is explicitly NOT the source of truth. On restart it
repopulates lazily from the durable PostgreSQL index; no credits are lost and
no durable state is destroyed.

It also backs the 60-second API principal cache (section 33), which is what
keeps key verification off PostgreSQL on every request.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("serpflow.redis")

_pool: aioredis.Redis | None = None

PRINCIPAL_PREFIX = "sf:principal:"
RATE_PREFIX = "sf:rate:"
STREAM_PREFIX = "sf:stream:"


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
            health_check_interval=30,
            max_connections=64,
        )
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None


async def ping() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


# --------------------------------------------------------------------------
# hot cache
# --------------------------------------------------------------------------
async def hot_get(key: str) -> dict[str, Any] | None:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:
        # A Redis outage degrades to a PostgreSQL lookup. It is never fatal,
        # because Redis is not the source of truth.
        log.warning(
            "redis get failed", extra={"event": "redis.degraded", "error": type(exc).__name__}
        )
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


async def hot_set(key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=max(1, ttl_seconds))
        return True
    except Exception as exc:
        log.warning(
            "redis set failed", extra={"event": "redis.degraded", "error": type(exc).__name__}
        )
        return False


async def hot_ttl(key: str) -> int | None:
    try:
        ttl = await get_redis().ttl(key)
    except Exception:
        return None
    return ttl if ttl and ttl > 0 else None


async def hot_delete(*keys: str) -> int:
    if not keys:
        return 0
    try:
        return int(await get_redis().delete(*keys))
    except Exception:
        return 0


async def hot_delete_pattern(pattern: str) -> int:
    """Manual invalidation from the Cache Dashboard (section 50)."""
    removed = 0
    try:
        client = get_redis()
        async for key in client.scan_iter(match=pattern, count=500):
            removed += int(await client.delete(key))
    except Exception as exc:
        log.warning(
            "redis scan failed", extra={"event": "redis.degraded", "error": type(exc).__name__}
        )
    return removed


async def hot_stats() -> dict[str, Any]:
    try:
        client = get_redis()
        info = await client.info("memory")
        keyspace = await client.info("keyspace")
        db_key = "db" + settings.redis_url.rsplit("/", 1)[-1]
        entry = keyspace.get(db_key) or {}
        return {
            "status": "ok",
            "used_memory_bytes": info.get("used_memory"),
            "used_memory_human": info.get("used_memory_human"),
            "keys": entry.get("keys", 0) if isinstance(entry, dict) else 0,
        }
    except Exception as exc:
        return {"status": "unavailable", "detail": type(exc).__name__}


# --------------------------------------------------------------------------
# API principal cache (section 33)
# --------------------------------------------------------------------------
async def cache_principal(key_hash: str, principal: dict[str, Any]) -> None:
    await hot_set(PRINCIPAL_PREFIX + key_hash, principal, settings.redis_principal_cache_ttl)


async def get_cached_principal(key_hash: str) -> dict[str, Any] | None:
    return await hot_get(PRINCIPAL_PREFIX + key_hash)


async def invalidate_principal(key_hash: str) -> None:
    """Called on revoke so a revoked key stops working immediately rather than
    after the 60-second TTL."""
    await hot_delete(PRINCIPAL_PREFIX + key_hash)


async def invalidate_project_principals(project_prefix: str) -> int:
    return await hot_delete_pattern(PRINCIPAL_PREFIX + "*" + project_prefix + "*")


# --------------------------------------------------------------------------
# rate limiting (section 67)
# --------------------------------------------------------------------------
async def incr_rate(bucket: str, window_seconds: int = 60) -> int:
    key = RATE_PREFIX + bucket
    try:
        client = get_redis()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        results = await pipe.execute()
        return int(results[0])
    except Exception:
        # Fail open: a Redis outage must not take the API down.
        return 0


__all__ = [
    "PRINCIPAL_PREFIX",
    "RATE_PREFIX",
    "STREAM_PREFIX",
    "cache_principal",
    "close_redis",
    "get_cached_principal",
    "get_redis",
    "hot_delete",
    "hot_delete_pattern",
    "hot_get",
    "hot_set",
    "hot_stats",
    "hot_ttl",
    "incr_rate",
    "invalidate_principal",
    "invalidate_project_principals",
    "ping",
]
