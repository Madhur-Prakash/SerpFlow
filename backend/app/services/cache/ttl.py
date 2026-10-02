"""Adaptive TTL (section 20).

Start from the engine's ``volatility_prior``; on refresh, move:

    top-10 unchanged      -> TTL x 1.5
    significant churn     -> TTL x 0.5

Learning is keyed per query class, not only per engine. A stable engine can
still carry a volatile query - ``google`` is a 24h prior, but
``google?q=current gold price`` is not - and a per-engine-only controller would
average those together and be wrong for both.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.text import classify_query
from app.services.catalog.schema import VOLATILITY_SECONDS

EXTEND_FACTOR = 1.5
SHRINK_FACTOR = 0.5
CHURN_THRESHOLD = 0.3  # 3 of the top 10 moved counts as significant churn

TTL_SOURCE_PRIOR = "volatility_prior"
TTL_SOURCE_LEARNED = "learned"
TTL_SOURCE_OVERRIDE = "project_override"
TTL_SOURCE_FRESHNESS = "freshness_capped"


@dataclass(frozen=True, slots=True)
class TTLDecision:
    ttl_seconds: int
    source: str
    reason: str
    previous: int | None = None
    direction: str = "unchanged"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ttl_seconds": self.ttl_seconds,
            "ttl_source": self.source,
            "reason": self.reason,
            "previous_ttl_seconds": self.previous,
            "direction": self.direction,
        }


def clamp(ttl: int) -> int:
    return max(settings.adaptive_ttl_min_seconds, min(settings.adaptive_ttl_max_seconds, int(ttl)))


def query_class_key(engine: str, query_text: str) -> str:
    """Stable per-engine, per-query-class learning key."""
    return engine + ":" + classify_query(query_text or "")


def top_results_digest(payload: dict[str, Any], *, depth: int = 10) -> str:
    """Fingerprint of the top N results, used to detect churn on refresh."""
    rows: list[Any] = []
    for key in (
        "organic_results",
        "local_results",
        "news_results",
        "shopping_results",
        "video_results",
        "image_results",
        "images_results",
        "reviews",
        "products",
        "jobs_results",
        "events_results",
        "properties",
        "best_flights",
    ):
        value = payload.get(key)
        if isinstance(value, list) and value:
            rows = value[:depth]
            break
    if not rows:
        return ""
    material: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            material.append(str(row)[:80])
            continue
        for field in (
            "link",
            "data_id",
            "place_id",
            "product_id",
            "title",
            "patent_id",
            "us_item_id",
            "contributor_id",
        ):
            value = row.get(field)
            if value:
                material.append(str(value))
                break
    return hashlib.sha256("|".join(material).encode("utf-8")).hexdigest()[:32]


def churn_ratio(previous_digest: str | None, new_digest: str) -> float:
    """0.0 when the top-10 is unchanged, 1.0 when it is entirely different.

    Digests are opaque, so this is binary by construction; the richer
    positional comparison lives in ``compare_top_results``.
    """
    if not previous_digest:
        return 0.0
    return 0.0 if previous_digest == new_digest else 1.0


def compare_top_results(previous: list[str], current: list[str]) -> tuple[float, bool]:
    """Positional comparison of two top-N identifier lists.

    Returns ``(churn_ratio, top10_unchanged)``. Overlap alone is not enough -
    a reordered top ten is churn even when the membership is identical.
    """
    if not previous:
        return 0.0, True
    depth = min(len(previous), len(current), 10)
    if depth == 0:
        return 1.0, False
    moved = sum(1 for i in range(depth) if previous[i] != current[i])
    ratio = moved / depth
    return ratio, ratio == 0.0


def initial_ttl(
    volatility_prior: str,
    *,
    freshness: str | None = None,
    override_seconds: int | None = None,
) -> TTLDecision:
    """First TTL for a brand-new entry."""
    if override_seconds:
        return TTLDecision(
            ttl_seconds=clamp(override_seconds),
            source=TTL_SOURCE_OVERRIDE,
            reason="Project TTL override applied.",
        )
    base = VOLATILITY_SECONDS.get(volatility_prior, VOLATILITY_SECONDS["7d"])
    decision = TTLDecision(
        ttl_seconds=clamp(base),
        source=TTL_SOURCE_PRIOR,
        reason="Seeded from the engine volatility_prior of " + volatility_prior + ".",
    )
    if freshness:
        return cap_for_freshness(decision, freshness)
    return decision


def cap_for_freshness(decision: TTLDecision, freshness: str) -> TTLDecision:
    """A TTL may never outlive the step's freshness requirement.

    Storing a 30-day entry for a ``realtime`` step would make it *available*
    long after it stopped being *acceptable*, which is exactly the distinction
    section 14 turns on.
    """
    from app.integrations.llm.base import freshness_max_age_seconds

    bound = freshness_max_age_seconds(freshness)
    if decision.ttl_seconds <= bound:
        return decision
    return TTLDecision(
        ttl_seconds=clamp(bound),
        source=TTL_SOURCE_FRESHNESS,
        reason=(
            "Capped to the "
            + freshness
            + " freshness bound; the engine prior would have allowed "
            + str(decision.ttl_seconds)
            + "s."
        ),
        previous=decision.ttl_seconds,
        direction="shortened",
    )


def adapt(
    previous_ttl: int,
    *,
    churn: float,
    top10_unchanged: bool,
    observed_interval_seconds: int | None = None,
) -> TTLDecision:
    """Move the TTL in response to observed churn."""
    if top10_unchanged and churn == 0.0:
        new_ttl = clamp(int(previous_ttl * EXTEND_FACTOR))
        return TTLDecision(
            ttl_seconds=new_ttl,
            source=TTL_SOURCE_LEARNED,
            reason=(
                "Top-10 unchanged on refresh, so the TTL was extended by "
                + str(EXTEND_FACTOR)
                + "x."
            ),
            previous=previous_ttl,
            direction="extended" if new_ttl > previous_ttl else "unchanged",
        )

    if churn >= CHURN_THRESHOLD:
        new_ttl = clamp(int(previous_ttl * SHRINK_FACTOR))
        return TTLDecision(
            ttl_seconds=new_ttl,
            source=TTL_SOURCE_LEARNED,
            reason=(
                "Significant churn ("
                + str(round(churn * 100))
                + "% of the top-10 moved), so the TTL was halved."
            ),
            previous=previous_ttl,
            direction="shortened" if new_ttl < previous_ttl else "unchanged",
        )

    reason = "Minor churn (" + str(round(churn * 100)) + "%); TTL held."
    if observed_interval_seconds:
        reason += " Measured refresh interval " + str(observed_interval_seconds) + "s."
    return TTLDecision(
        ttl_seconds=clamp(previous_ttl),
        source=TTL_SOURCE_LEARNED,
        reason=reason,
        previous=previous_ttl,
        direction="unchanged",
    )


__all__ = [
    "CHURN_THRESHOLD",
    "EXTEND_FACTOR",
    "SHRINK_FACTOR",
    "TTL_SOURCE_FRESHNESS",
    "TTL_SOURCE_LEARNED",
    "TTL_SOURCE_OVERRIDE",
    "TTL_SOURCE_PRIOR",
    "TTLDecision",
    "adapt",
    "cap_for_freshness",
    "churn_ratio",
    "clamp",
    "compare_top_results",
    "initial_ttl",
    "query_class_key",
    "top_results_digest",
]
