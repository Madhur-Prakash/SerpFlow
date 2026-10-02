"""Four-layer cache: exact (Redis), semantic (pgvector), archive, live."""

from app.services.cache.guard import GuardVerdict, check, check_against_stored
from app.services.cache.keys import CacheKey, build_key, partition_key, request_hash
from app.services.cache.service import (
    LAYER_ARCHIVE,
    LAYER_EXACT,
    LAYER_LIVE,
    LAYER_MISS,
    LAYER_SEMANTIC,
    CacheHit,
    CacheService,
    CacheState,
)
from app.services.cache.ttl import TTLDecision, adapt, cap_for_freshness, initial_ttl

__all__ = [
    "LAYER_ARCHIVE",
    "LAYER_EXACT",
    "LAYER_LIVE",
    "LAYER_MISS",
    "LAYER_SEMANTIC",
    "CacheHit",
    "CacheKey",
    "CacheService",
    "CacheState",
    "GuardVerdict",
    "TTLDecision",
    "adapt",
    "build_key",
    "cap_for_freshness",
    "check",
    "check_against_stored",
    "initial_ttl",
    "partition_key",
    "request_hash",
]
