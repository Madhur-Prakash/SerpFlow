"""Stage A - RETRIEVE (section 13).

Embed the intent, retrieve the top 8 candidate engines. Never pass all 54
engine schemas to the planner on every call.

The non-obvious requirement: retrieval must also pull in the *substitutes* of
strong matches, even when those substitutes score poorly on their own. If
competing engines never enter the candidate set, stage D cannot emit
alternative plans, and section 14 has nothing to re-rank. Expanding the set by
substitution is what keeps candidate plurality possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.integrations.llm.embedding import cosine_similarity, embed
from app.services.catalog.loader import CatalogIndex
from app.services.catalog.schema import EngineSpec
from app.services.catalog.vocabulary import normalized_tag_affinity, tag_scores

SUBSTITUTE_EXPANSION = 4


@dataclass(slots=True)
class Candidate:
    engine: str
    spec: EngineSpec
    score: float
    source: str = "retrieval"  # retrieval | substitute | capability
    substitute_of: str | None = None
    substitute_note: str | None = None
    coverage: str | None = None
    matched_tags: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Shape handed to the selector. Deliberately compact: this is what
        keeps the prompt small enough to stay cheap and fast."""
        return {
            "engine": self.engine,
            "purpose": self.spec.purpose,
            "capability_tags": self.spec.capability_tags,
            "requires": {k: v.model_dump() for k, v in self.spec.requires.items()},
            "optional": self.spec.optional[:10],
            "cost": self.spec.cost,
            "latency_class": self.spec.latency_class,
            "volatility_prior": self.spec.volatility_prior,
            "locale_sensitive": self.spec.locale_sensitive,
            "pii_risk": self.spec.pii_risk,
            "retrieval_score": round(self.score, 4),
            "source": self.source,
            "substitute_of": self.substitute_of,
            "substitute_note": self.substitute_note,
            "coverage": self.coverage,
            "substitutes": [
                {"engine": s.engine, "coverage": s.coverage, "note": s.note}
                for s in self.spec.substitutes
            ],
        }


def retrieve(
    index: CatalogIndex,
    intent: str,
    *,
    top_k: int | None = None,
    engine_allowlist: list[str] | None = None,
    engine_denylist: list[str] | None = None,
) -> list[Candidate]:
    """Top-k engines by embedding similarity, expanded by substitution."""
    k = top_k or settings.planner_retrieval_top_k
    allow = set(engine_allowlist or [])
    deny = set(engine_denylist or [])

    def permitted(name: str) -> bool:
        if deny and name in deny:
            return False
        return not (allow and name not in allow)

    intent_vector = embed(intent)
    intent_tags = tag_scores(intent)

    scored: list[Candidate] = []
    for name, spec in index.engines.items():
        if not permitted(name):
            continue
        # Embedding similarity alone retrieves badly here: engine docs are
        # short and use the vendor's vocabulary, so nothing in google_finance's
        # description contains "trading". Capability affinity carries most of
        # the weight and similarity breaks ties.
        affinity = normalized_tag_affinity(intent, spec.capability_tags)
        similarity = cosine_similarity(intent_vector, embed(spec.search_text()))
        matched = [tag for tag in spec.capability_tags if tag in intent_tags]
        scored.append(
            Candidate(
                engine=name,
                spec=spec,
                score=round(affinity * 0.72 + max(0.0, similarity) * 0.28, 6),
                matched_tags=matched,
            )
        )

    scored.sort(key=lambda c: (-c.score, c.engine))
    primary = scored[:k]
    chosen: dict[str, Candidate] = {c.engine: c for c in primary}

    # Expand by substitution so competing engines enter the candidate set even
    # when their own embedding score is weak.
    for candidate in list(primary[:SUBSTITUTE_EXPANSION]):
        for sub in index.substitutes_for(candidate.engine):
            name = sub.substitute_engine
            if name in chosen or not permitted(name) or not index.has(name):
                continue
            spec = index.get(name)
            chosen[name] = Candidate(
                engine=name,
                spec=spec,
                score=cosine_similarity(intent_vector, embed(spec.search_text())),
                source="substitute",
                substitute_of=candidate.engine,
                substitute_note=sub.note,
                coverage=sub.coverage,
                matched_tags=sub.shared_tags,
            )

    # Pull in anything reachable as an upstream producer of a strong match, so
    # a chain's entry point is never missing from the candidate set.
    for candidate in list(primary[:SUBSTITUTE_EXPANSION]):
        for dependency in index.dependencies_of(candidate.engine):
            if dependency in chosen or not permitted(dependency) or not index.has(dependency):
                continue
            spec = index.get(dependency)
            chosen[dependency] = Candidate(
                engine=dependency,
                spec=spec,
                score=cosine_similarity(intent_vector, embed(spec.search_text())) * 0.9,
                source="capability",
                matched_tags=spec.capability_tags,
            )

    out = sorted(chosen.values(), key=lambda c: (-c.score, c.engine))
    return out


def summarize(candidates: list[Candidate]) -> dict[str, Any]:
    return {
        "count": len(candidates),
        "engines": [c.engine for c in candidates],
        "from_substitution": [c.engine for c in candidates if c.source == "substitute"],
        "from_dependency": [c.engine for c in candidates if c.source == "capability"],
        "top_score": round(candidates[0].score, 4) if candidates else 0.0,
    }


__all__ = ["SUBSTITUTE_EXPANSION", "Candidate", "retrieve", "summarize"]
