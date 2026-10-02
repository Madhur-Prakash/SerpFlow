"""The entity / numeral guard (section 17).

A mechanism, not a rule of thumb:

    1. Extract from BOTH the incoming query and the candidate cached query:
         - all numerals and numeric tokens (16, 17, 2024, v3, 4K)
         - all named entities (products, brands, places, people, organisations)
         - all model/version identifiers
    2. Require EXACT SET EQUALITY of both extracted sets.
    3. Any difference rejects the hit, regardless of cosine score.

So ``iphone 16`` can never match ``iphone 17``, and ``restaurants in
Koramangala`` can never match ``restaurants in Indiranagar``, even at cosine
0.98.

This is deliberately deterministic. A model asked to judge equivalence is right
most of the time, and "most of the time" means serving the wrong
neighbourhood's restaurants to someone once every few dozen queries - a silent
correctness failure that a cache hit rate makes look like a win.

Every rejection is logged so the threshold can be tuned with evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.text import GuardTokens, guard_tokens

REASON_NUMERAL = "numeral_mismatch"
REASON_ENTITY = "entity_mismatch"
REASON_VERSION = "version_mismatch"
REASON_OK = "accepted"


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    accepted: bool
    reason: str
    detail: str = ""
    incoming: GuardTokens | None = None
    candidate: GuardTokens | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "detail": self.detail,
            "incoming_tokens": self.incoming.as_dict() if self.incoming else {},
            "candidate_tokens": self.candidate.as_dict() if self.candidate else {},
        }

    @property
    def incoming_token_list(self) -> list[str]:
        return self.incoming.all_tokens() if self.incoming else []

    @property
    def candidate_token_list(self) -> list[str]:
        return self.candidate.all_tokens() if self.candidate else []


def _difference(a: set[str], b: set[str]) -> str:
    only_a = sorted(a - b)
    only_b = sorted(b - a)
    parts: list[str] = []
    if only_a:
        parts.append("requested has " + ", ".join(only_a[:5]))
    if only_b:
        parts.append("cached has " + ", ".join(only_b[:5]))
    return "; ".join(parts)


def check(incoming_query: str, candidate_query: str) -> GuardVerdict:
    """Compare two queries. Exact set equality on all three token families."""
    incoming = guard_tokens(incoming_query)
    candidate = guard_tokens(candidate_query)

    if incoming.numerals != candidate.numerals:
        return GuardVerdict(
            accepted=False,
            reason=REASON_NUMERAL,
            detail=_difference(incoming.numerals, candidate.numerals),
            incoming=incoming,
            candidate=candidate,
        )

    if incoming.versions != candidate.versions:
        return GuardVerdict(
            accepted=False,
            reason=REASON_VERSION,
            detail=_difference(incoming.versions, candidate.versions),
            incoming=incoming,
            candidate=candidate,
        )

    if incoming.entities != candidate.entities:
        return GuardVerdict(
            accepted=False,
            reason=REASON_ENTITY,
            detail=_difference(incoming.entities, candidate.entities),
            incoming=incoming,
            candidate=candidate,
        )

    return GuardVerdict(
        accepted=True,
        reason=REASON_OK,
        detail="numeral, version and entity sets are identical",
        incoming=incoming,
        candidate=candidate,
    )


def tokens_for_storage(query: str) -> dict[str, list[str]]:
    """Guard material extracted once at write time and stored on the entry, so
    a lookup never has to re-derive it for every candidate row."""
    return guard_tokens(query).as_dict()


def check_against_stored(
    incoming_query: str,
    stored_numerals: list[str] | None,
    stored_entities: list[str] | None,
    stored_versions: list[str] | None,
    candidate_query: str = "",
) -> GuardVerdict:
    """Fast path using the tokens persisted on the cache entry.

    Falls back to re-extracting from the candidate query for rows written
    before the columns existed, so an older entry is never silently accepted
    without being guarded.
    """
    if stored_numerals is None and stored_entities is None and stored_versions is None:
        return check(incoming_query, candidate_query)

    incoming = guard_tokens(incoming_query)
    candidate = GuardTokens(
        numerals=set(stored_numerals or []),
        entities=set(stored_entities or []),
        versions=set(stored_versions or []),
    )

    if incoming.numerals != candidate.numerals:
        return GuardVerdict(
            False,
            REASON_NUMERAL,
            _difference(incoming.numerals, candidate.numerals),
            incoming,
            candidate,
        )
    if incoming.versions != candidate.versions:
        return GuardVerdict(
            False,
            REASON_VERSION,
            _difference(incoming.versions, candidate.versions),
            incoming,
            candidate,
        )
    if incoming.entities != candidate.entities:
        return GuardVerdict(
            False,
            REASON_ENTITY,
            _difference(incoming.entities, candidate.entities),
            incoming,
            candidate,
        )
    return GuardVerdict(
        True, REASON_OK, "numeral, version and entity sets are identical", incoming, candidate
    )


__all__ = [
    "REASON_ENTITY",
    "REASON_NUMERAL",
    "REASON_OK",
    "REASON_VERSION",
    "GuardVerdict",
    "check",
    "check_against_stored",
    "tokens_for_storage",
]
