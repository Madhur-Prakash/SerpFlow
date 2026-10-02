"""Extract chained values from an upstream payload.

A dependency edge names a field path like
``google_maps.local_results[].data_id``. The executor has to turn that into the
concrete values that parameterise the next hop, including the list expansion
that produces fan-out.
"""

from __future__ import annotations

import re
from typing import Any

_SEGMENT = re.compile(r"([^.\[\]]+)(\[\])?")


def parse_path(field_ref: str) -> list[tuple[str, bool]]:
    """``google_maps.local_results[].data_id`` -> [(local_results, True), (data_id, False)]

    The leading engine name is stripped; it identifies the producer, not a key
    inside the payload.
    """
    ref = field_ref.strip()
    if "." in ref:
        head, rest = ref.split(".", 1)
        if head.replace("_", "").isalnum() and not head.endswith("]"):
            ref = rest
    out: list[tuple[str, bool]] = []
    for match in _SEGMENT.finditer(ref):
        name = match.group(1)
        if not name:
            continue
        out.append((name, bool(match.group(2))))
    return out


def extract(payload: dict[str, Any], field_ref: str, *, limit: int | None = None) -> list[Any]:
    """Every value at ``field_ref``, flattened across list segments."""
    segments = parse_path(field_ref)
    current: list[Any] = [payload]

    for name, is_list in segments:
        nxt: list[Any] = []
        for node in current:
            if not isinstance(node, dict):
                continue
            value = node.get(name)
            if value is None:
                continue
            if is_list or isinstance(value, list):
                if isinstance(value, list):
                    nxt.extend(value)
                else:
                    nxt.append(value)
            else:
                nxt.append(value)
        current = nxt
        if not current:
            return []

    out: list[Any] = []
    seen: set[str] = set()
    for value in current:
        if isinstance(value, (dict, list)):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def extract_first(payload: dict[str, Any], field_ref: str) -> Any | None:
    values = extract(payload, field_ref, limit=1)
    return values[0] if values else None


def summarize_payload(payload: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
    """Compact result summary for the Run Inspector and the SSE result event.

    Raw payloads are permission-gated separately from run visibility
    (section 47), so this summary is what a reader without ``payload:read``
    sees.
    """
    for key in (
        "local_results",
        "organic_results",
        "news_results",
        "shopping_results",
        "reviews",
        "video_results",
        "images_results",
        "products",
        "jobs_results",
        "events_results",
        "properties",
        "best_flights",
        "suggestions",
    ):
        rows = payload.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        items = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                items.append({"value": str(row)[:120]})
                continue
            item: dict[str, Any] = {
                "title": _first(row, "title", "name", "question", "value"),
                "link": _first(row, "link", "url", "apply_link"),
                "rating": row.get("rating"),
                "price": _first(row, "price", "rate_per_night", "extracted_price"),
                "snippet": _truncate(_first(row, "snippet", "description", "text")),
                "date": _first(row, "date", "published_date"),
                "source": _first(row, "source", "displayed_link", "channel"),
            }
            items.append(item)
        return {"result_key": key, "count": len(rows), "items": items}
    return {"result_key": None, "count": 0, "items": []}


def _first(row: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            if isinstance(value, dict):
                return value.get("lowest") or value.get("name") or str(value)[:120]
            return value
    return None


def _truncate(value: Any, length: int = 220) -> Any:
    if isinstance(value, str) and len(value) > length:
        return value[:length] + "..."
    return value


__all__ = ["extract", "extract_first", "parse_path", "summarize_payload"]
