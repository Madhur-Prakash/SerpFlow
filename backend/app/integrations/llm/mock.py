"""Deterministic LLM adapter (section 41).

``make dev`` and ``make seed`` must work with no API keys at all, so this
adapter covers every seeded demo intent without a network call. It is not a
stub that returns canned nonsense: selection runs a real lexical and capability
scoring pass over the retrieved shortlist, and synthesis reuses exactly the
same deterministic inference rules that the Groq adapter validates its output
against. Identical input always yields identical output, which is also what
makes the unit tests meaningful.
"""

from __future__ import annotations

import re

import time
from typing import Any

from app.core.routes import resolve_route
from app.core.text import (
    classify_query,
    extract_entities,
    extract_location_phrase,
    infer_freshness,
    infer_locale,
    normalize,
    normalize_dates,
    words,
)
from app.integrations.llm.base import EngineChoice, SelectionResult, SynthesisResult
from app.services.catalog.vocabulary import tag_scores

# The capability vocabulary lives with the catalog it describes, so stage A
# retrieval and this selector agree on what a word means.

# Phrases meaning "go one level deeper than the obvious engine".
#
# Without a signal like these, an engine that can only be addressed through
# another engine's identifier is the wrong target: "the patent covering X"
# wants the patent search, not the full claim record, while "show me the full
# claim set" wants exactly that record.
DRILL_DOWN_SIGNALS = (
    "full",
    "detail",
    "details",
    "complete",
    "claim set",
    "claims",
    "every",
    "each",
    "per ",
    "history",
    "all the",
    "breakdown",
    "cited by",
    "citations",
    "what buyers",
    "buyers said",
    "who reviewed",
    "reviewer",
    "reviewers",
    "specification",
    "specs",
    "offers",
    "sellers",
    "listing for",
)

DRILL_DOWN_PENALTY = 3.0

# Locale-specific engine preferences the mock applies as an explicit rule.
LOCALE_PREFERENCE: dict[str, dict[str, str]] = {
    "kr": {"web_search": "naver"},
    "ru": {"web_search": "yandex"},
    "cn": {"web_search": "baidu"},
}

# The converse rule: a regional engine is not a contender outside its market.
# Naver's catalog entry mentions "blogs and cafes", which used to win "cafes in
# Koramangala" - a Bangalore neighbourhood - for a Korean search engine. The
# penalty is lifted when the intent names the engine, or is written in the
# market's own script.
REGIONAL_ENGINES: dict[str, tuple[frozenset[str], str]] = {
    "naver": (frozenset({"kr"}), r"[\uac00-\ud7a3]"),
    "baidu": (frozenset({"cn"}), r"[\u4e00-\u9fff]"),
    "yandex": (frozenset({"ru", "by", "kz"}), r"[\u0400-\u04ff]"),
    "yandex_images": (frozenset({"ru", "by", "kz"}), r"[\u0400-\u04ff]"),
}
REGIONAL_PENALTY = 4.0


def _is_addressable(candidate: dict[str, Any]) -> bool:
    """True when the caller can supply at least one required parameter."""
    requires = candidate.get("requires") or {}
    if not requires:
        return True
    return any(not (spec or {}).get("satisfied_by") for spec in requires.values())


def _is_redundant_drill_down(candidate: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
    if _is_addressable(candidate):
        return False
    tags = set(candidate.get("capability_tags") or [])
    if not tags:
        return True
    for other in candidates:
        if other is candidate or not _is_addressable(other):
            continue
        if tags <= set(other.get("capability_tags") or []):
            return True
    return False


def _wants_drill_down(intent: str) -> bool:
    haystack = " " + normalize(intent) + " "
    return any(signal in haystack for signal in DRILL_DOWN_SIGNALS)


class MockLLMAdapter:
    """Deterministic adapter. Resolved mode is reported as MOCK everywhere."""

    name = "mock"
    model = "deterministic-v1"

    async def select_engines(
        self,
        intent: str,
        candidates: list[dict[str, Any]],
        *,
        max_select: int = 3,
    ) -> SelectionResult:
        started = time.perf_counter()
        # Score the de-imperatived query, so "find X" and "X" score alike.
        query = _query_text(intent)
        scores = tag_scores(query)
        drill_down = _wants_drill_down(query)
        locale, _ = infer_locale(intent)
        intent_words = set(words(normalize(intent)))

        scored: list[tuple[float, dict[str, Any], list[str]]] = []
        for candidate in candidates:
            score = 0.0
            reasons: list[str] = []

            matched_tags = [t for t in candidate.get("capability_tags", []) if t in scores]
            for tag in matched_tags:
                score += scores[tag] * 2.0
            if matched_tags:
                reasons.append("capability match: " + ", ".join(sorted(matched_tags)))

            # Lexical overlap with the engine's purpose line.
            purpose_words = set(words(normalize(candidate.get("purpose", ""))))
            overlap = intent_words & purpose_words
            if overlap:
                score += min(3.0, len(overlap) * 0.5)
                reasons.append("purpose overlap: " + ", ".join(sorted(overlap)[:4]))

            # The retrieval stage already ranked these; keep that as a prior.
            score += float(candidate.get("retrieval_score", 0.0)) * 2.0

            # Explicit locale preference, stated rather than implied.
            engine = candidate.get("engine", "")
            prefs = LOCALE_PREFERENCE.get(locale.gl, {})
            for tag, preferred in prefs.items():
                if tag in candidate.get("capability_tags", []):
                    if engine == preferred:
                        score += 2.5
                        reasons.append("preferred for " + locale.gl + " locale")
                    elif engine in ("google", "google_light", "bing"):
                        score -= 0.5

            regional = REGIONAL_ENGINES.get(engine)
            if regional:
                markets, script = regional
                if (
                    locale.gl not in markets
                    and engine.split("_")[0] not in intent_words
                    and not re.search(script, intent or "")
                ):
                    score -= REGIONAL_PENALTY
                    reasons.append(
                        engine + " serves " + "/".join(sorted(markets)) + "; this intent resolves to " + locale.gl
                    )

            # Cheap engines win ties; nothing here is more expensive than 1
            # today, but the rule keeps the ranking honest if that changes.
            score -= (float(candidate.get("cost", 1)) - 1.0) * 0.5

            # An engine reachable only through another engine's identifier is a
            # drill-down. Penalise it only when drilling down buys nothing: if
            # it declares a capability no addressable candidate has, it is the
            # answer, not a detour.
            #
            # google_patents_details declares the same patent_search capability
            # as google_patents, so "find the patent covering X" wants the
            # search. apple_reviews declares app_reviews, which
            # apple_app_store does not, so "what users say about the app"
            # genuinely needs the second hop.
            if _is_redundant_drill_down(candidate, candidates) and not drill_down:
                score -= DRILL_DOWN_PENALTY
                reasons.append(
                    "reachable only through another engine's identifier and adds no "
                    "capability the shallower engine lacks"
                )

            scored.append((score, candidate, reasons))

        scored.sort(key=lambda row: (-row[0], row[1].get("engine", "")))

        chosen: list[EngineChoice] = []
        rejected: list[dict[str, Any]] = []
        top_score = scored[0][0] if scored else 0.0

        for score, candidate, reasons in scored:
            engine = candidate.get("engine", "")
            if len(chosen) < max_select and score > 0 and score >= top_score * 0.55:
                confidence = _confidence(score, top_score)
                chosen.append(
                    EngineChoice(
                        engine=engine,
                        confidence=confidence,
                        reason="; ".join(reasons) or "best available capability match",
                    )
                )
            else:
                rejected.append(
                    {
                        "engine": engine,
                        "score": round(score, 3),
                        "reason": _rejection_reason(candidate, reasons, score, top_score),
                    }
                )

        if not chosen and scored:
            best = scored[0]
            chosen.append(
                EngineChoice(
                    engine=best[1].get("engine", ""),
                    confidence=0.35,
                    reason="no strong capability match; falling back to the closest candidate",
                )
            )

        return SelectionResult(
            chosen=chosen,
            rejected=rejected,
            reasoning=(
                "Deterministic capability scoring over "
                + str(len(candidates))
                + " retrieved candidates."
            ),
            provider=self.name,
            model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    async def synthesize(self, intent: str, engine_specs: list[dict[str, Any]]) -> SynthesisResult:
        started = time.perf_counter()
        locale, matched = infer_locale(intent)
        query_class = classify_query(intent)
        prior = engine_specs[0].get("volatility_prior", "7d") if engine_specs else "7d"
        freshness, signals = infer_freshness(
            intent, volatility_prior=prior, query_class=query_class
        )

        params: dict[str, Any] = {"q": _query_text(intent)}
        location = extract_location_phrase(intent)
        if location:
            params["location"] = location
        params["gl"] = locale.gl
        params["hl"] = locale.hl
        params.update(normalize_dates(intent))
        # Entity resolution: city names become the IATA codes google_flights
        # requires, so a flight intent is actually routable.
        route = resolve_route(intent)
        params.update(route)
        if route and "date" in params:
            params["outbound_date"] = params["date"]

        return SynthesisResult(
            parameters=params,
            locale={"gl": locale.gl, "hl": locale.hl, "matched": matched or ""},
            freshness=freshness,
            freshness_signals=signals,
            entities=sorted(extract_entities(intent)),
            query_class=query_class,
            notes="Deterministic synthesis; no model call.",
            provider=self.name,
            model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    async def health(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "status": "ok", "network": False}


def _confidence(score: float, top: float) -> float:
    if top <= 0:
        return 0.3
    ratio = score / top
    # Map the score ratio onto a calibrated band. A deterministic selector
    # should never claim 1.0.
    return round(min(0.95, max(0.3, 0.45 + ratio * 0.45)), 3)


def _rejection_reason(
    candidate: dict[str, Any], reasons: list[str], score: float, top: float
) -> str:
    engine = candidate.get("engine", "unknown")
    note = candidate.get("substitute_note")
    if note:
        return note
    if score <= 0:
        return engine + " shares no capability tag with this intent."
    if top > 0 and score < top * 0.55:
        matched = reasons[0] if reasons else "weak lexical overlap only"
        return (
            engine
            + " scored "
            + str(round(score, 2))
            + " against "
            + str(round(top, 2))
            + " for the leader ("
            + matched
            + ")."
        )
    return engine + " was outranked by a closer capability match."


def _query_text(intent: str) -> str:
    """Strip imperative framing so the query is what a user would type."""
    cleaned = intent.strip()
    for prefix in (
        "find ",
        "search for ",
        "search ",
        "show me ",
        "show ",
        "get me ",
        "get ",
        "look up ",
        "lookup ",
        "list ",
        "give me ",
        "i want ",
        "i need ",
        "can you find ",
        "what are ",
        "what is ",
    ):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return cleaned.strip().rstrip("?.")


__all__ = ["LOCALE_PREFERENCE", "MockLLMAdapter"]
