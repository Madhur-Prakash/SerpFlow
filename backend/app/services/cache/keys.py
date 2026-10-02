"""Cache key normalisation and partitioning (sections 17, 37).

Normalisation is what makes the exact layer actually hit: whitespace collapsed,
casing folded, parameters in a stable order, and non-semantic parameters
stripped before hashing. ``api_key``, ``output`` and ``no_cache`` never change
the result, so they must never change the key.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.core.text import normalize

# Parameters that do not affect the result set.
NON_SEMANTIC = frozenset(
    {
        "api_key",
        "output",
        "no_cache",
        "async",
        "zero_trace",
        "json_restrictor",
        "device_id",
        "_limit",
    }
)

# Parameters that partition the cache. These go into the WHERE clause *before*
# any vector distance is evaluated.
PARTITION_PARAMS = ("gl", "hl", "location")


def normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [normalize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_value(v) for k, v in sorted(value.items())}
    if value is None:
        return None
    return normalize(str(value))


def normalize_request(engine: str, params: dict[str, Any]) -> dict[str, Any]:
    """Strip, normalise and stably order a request for hashing."""
    clean: dict[str, Any] = {}
    for key in sorted(params):
        if key in NON_SEMANTIC or key == "engine":
            continue
        value = params[key]
        if value is None or value == "":
            continue
        clean[key] = normalize_value(value)
    clean["engine"] = engine
    return clean


def request_hash(engine: str, params: dict[str, Any]) -> str:
    normalized = normalize_request(engine, params)
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def partition_key(project_id: str, org_id: str, *, scope: str = "project") -> str:
    """Project-level isolation by default (section 37).

    Organization-level sharing is opt-in and crosses a billing and data
    boundary, which the UI states explicitly at the point of enabling it.
    """
    if scope == "organization":
        return "org:" + org_id
    return "project:" + project_id


@dataclass(frozen=True, slots=True)
class CacheKey:
    engine: str
    partition: str
    request_hash: str
    gl: str
    hl: str
    location: str
    query_text: str
    normalized: dict[str, Any]

    @property
    def redis_key(self) -> str:
        return "sf:cache:" + self.partition + ":" + self.engine + ":" + self.request_hash

    @property
    def redis_meta_key(self) -> str:
        return self.redis_key + ":meta"

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "partition": self.partition,
            "request_hash": self.request_hash,
            "gl": self.gl,
            "hl": self.hl,
            "location": self.location,
            "query_text": self.query_text,
        }


def build_key(
    engine: str,
    params: dict[str, Any],
    *,
    project_id: str,
    org_id: str,
    scope: str = "project",
) -> CacheKey:
    normalized = normalize_request(engine, params)
    return CacheKey(
        engine=engine,
        partition=partition_key(project_id, org_id, scope=scope),
        request_hash=request_hash(engine, params),
        gl=str(normalized.get("gl", "") or ""),
        hl=str(normalized.get("hl", "") or ""),
        location=str(normalized.get("location", "") or "")[:160],
        query_text=query_text_for(engine, params),
        normalized=normalized,
    )


# Each engine names its free-text query parameter differently. The semantic
# layer embeds that value, so it must be found reliably.
QUERY_PARAMS = (
    "q",
    "query",
    "text",
    "search_query",
    "term",
    "p",
    "k",
    "_nkw",
    "mauthors",
    "find_desc",
    "keyword",
)

# Identifier parameters. A step keyed on one of these is an identity lookup,
# never a fuzzy one, so the semantic layer must not be consulted for it.
IDENTIFIER_PARAMS = (
    "data_id",
    "place_id",
    "contributor_id",
    "product_id",
    "us_item_id",
    "author_id",
    "patent_id",
    "page_token",
    "next_page_token",
    "departure_token",
    "property_token",
    "result_id",
    "citation_id",
    "asin",
    "id",
)


def query_text_for(engine: str, params: dict[str, Any]) -> str:
    """The human-meaningful query string for this request, if any."""
    for name in QUERY_PARAMS:
        value = params.get(name)
        if isinstance(value, str) and value.strip():
            parts = [value.strip()]
            location = params.get("location") or params.get("find_loc")
            if isinstance(location, str) and location.strip():
                parts.append(location.strip())
            return " ".join(parts)
    return ""


def is_identifier_lookup(engine: str, params: dict[str, Any]) -> bool:
    """True when the request is addressed by an opaque identifier.

    ``google_maps_reviews?data_id=0x...`` has no meaningful semantic
    neighbourhood: a "similar" data_id is a different place, so a semantic hit
    would be a correctness bug rather than a saving.
    """
    _ = engine
    if query_text_for(engine, params):
        return False
    return any(params.get(name) for name in IDENTIFIER_PARAMS)


__all__ = [
    "IDENTIFIER_PARAMS",
    "NON_SEMANTIC",
    "PARTITION_PARAMS",
    "QUERY_PARAMS",
    "CacheKey",
    "build_key",
    "is_identifier_lookup",
    "normalize_request",
    "normalize_value",
    "partition_key",
    "query_text_for",
    "request_hash",
]
