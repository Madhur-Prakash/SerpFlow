"""LLM adapter contract.

Three adapters implement it: ``groq`` (real), ``mock`` (deterministic) and the
benchmark's unaided baseline. Section 77: external integrations always have a
clear real/mock boundary, and the resolved adapter is reported, never implied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class EngineChoice:
    """Stage B output for one selected engine."""

    engine: str
    confidence: float
    reason: str = ""


@dataclass(slots=True)
class SelectionResult:
    """Stage B: which engines, and crucially why not the others."""

    chosen: list[EngineChoice] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""
    provider: str = "mock"
    model: str = "deterministic"
    latency_ms: float = 0.0

    @property
    def primary(self) -> str | None:
        return self.chosen[0].engine if self.chosen else None

    @property
    def confidence(self) -> float:
        if not self.chosen:
            return 0.0
        return sum(c.confidence for c in self.chosen) / len(self.chosen)


@dataclass(slots=True)
class SynthesisResult:
    """Stage C: bound parameters plus the inferred freshness requirement."""

    parameters: dict[str, Any] = field(default_factory=dict)
    locale: dict[str, str] = field(default_factory=dict)
    freshness: str = "stable"
    freshness_signals: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    query_class: str = "general"
    notes: str = ""
    provider: str = "mock"
    model: str = "deterministic"
    latency_ms: float = 0.0


class LLMAdapter(Protocol):
    """Everything the planner asks a model for. Nothing else talks to an LLM."""

    name: str
    model: str

    async def select_engines(
        self,
        intent: str,
        candidates: list[dict[str, Any]],
        *,
        max_select: int = 3,
    ) -> SelectionResult:
        """Stage B. ``candidates`` is the retrieved shortlist, never the whole
        catalog - section 13 forbids passing 60+ schemas on every call."""
        ...

    async def synthesize(
        self,
        intent: str,
        engine_specs: list[dict[str, Any]],
    ) -> SynthesisResult:
        """Stage C: parameter binding, locale inference, freshness inference."""
        ...

    async def health(self) -> dict[str, Any]: ...


FRESHNESS_LEVELS: dict[str, int] = {
    "realtime": 15 * 60,
    "fresh": 24 * 60 * 60,
    "recent": 7 * 24 * 60 * 60,
    "stable": 365 * 24 * 60 * 60,
}

FRESHNESS_ORDER = ["realtime", "fresh", "recent", "stable"]


def freshness_max_age_seconds(level: str) -> int:
    return FRESHNESS_LEVELS.get(level, FRESHNESS_LEVELS["stable"])


def stricter_freshness(a: str, b: str) -> str:
    """The tighter of two requirements wins."""
    ia = FRESHNESS_ORDER.index(a) if a in FRESHNESS_ORDER else len(FRESHNESS_ORDER) - 1
    ib = FRESHNESS_ORDER.index(b) if b in FRESHNESS_ORDER else len(FRESHNESS_ORDER) - 1
    return FRESHNESS_ORDER[min(ia, ib)]


__all__ = [
    "FRESHNESS_LEVELS",
    "FRESHNESS_ORDER",
    "EngineChoice",
    "LLMAdapter",
    "SelectionResult",
    "SynthesisResult",
    "freshness_max_age_seconds",
    "stricter_freshness",
]
