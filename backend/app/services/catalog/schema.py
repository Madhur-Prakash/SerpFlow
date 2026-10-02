"""Typed model of the engine catalog (section 11).

Two relationship kinds, both mandatory:

* dependency edges (``satisfied_by`` / ``feeds``) describe how engines CHAIN
* ``capability_tags`` and ``substitutes`` describe how engines COMPETE

Without the second, stage D cannot emit alternative candidate plans and section
14 marginal replanning has nothing to re-rank.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Coverage = Literal["full", "partial", "narrow"]
LatencyClass = Literal["fast", "medium", "slow"]
PiiRisk = Literal["low", "medium", "high"]

VOLATILITY_SECONDS: dict[str, int] = {
    "15m": 15 * 60,
    "1h": 60 * 60,
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
    "365d": 365 * 24 * 60 * 60,
}

LATENCY_MS: dict[str, int] = {"fast": 700, "medium": 1800, "slow": 4500}

_FIELD_REF = re.compile(r"^(?P<engine>[a-z0-9_]+)\.(?P<path>.+)$")


class Substitute(BaseModel):
    """A competing engine for the same capability."""

    model_config = ConfigDict(extra="forbid")

    engine: str
    coverage: Coverage = "partial"
    note: str = ""

    @field_validator("note")
    @classmethod
    def _note_is_real(cls, v: str) -> str:
        # The note is user-facing copy: it surfaces verbatim in Plan Inspector
        # rejection reasons, so a placeholder is a defect.
        if v and len(v.strip()) < 15:
            raise ValueError("substitute note must state the real trade-off")
        return v.strip()


class RequiredParam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "string"
    description: str = ""
    # Dotted field references on other engines that can produce this value.
    satisfied_by: list[str] = Field(default_factory=list)
    # When set, this parameter and the named one are interchangeable.
    alternative_to: str | None = None
    # Explicit override for the inference below.
    #
    # Parameter names collide across engines: google.q is the user's query and
    # the caller always has one, while google_scholar_cite.q is a Scholar
    # result_id that only an upstream hop can produce. Both are called "q", so
    # the name cannot decide it and the catalog says so instead.
    caller_suppliable: bool | None = None

    @property
    def is_root_satisfiable(self) -> bool:
        """True when the caller can supply it directly without an upstream hop."""
        if self.caller_suppliable is not None:
            return self.caller_suppliable
        return not self.satisfied_by


class ProducedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "string"
    # Dotted ``engine.param`` targets this field can satisfy.
    feeds: list[str] = Field(default_factory=list)
    fan_out_hint: int = 1


class EngineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str
    purpose: str = ""
    capability_tags: list[str] = Field(default_factory=list)
    substitutes: list[Substitute] = Field(default_factory=list)
    # Required when `substitutes` is empty: states why nothing competes.
    single_source_note: str = ""
    requires: dict[str, RequiredParam] = Field(default_factory=dict)
    optional: list[str] = Field(default_factory=list)
    produces: dict[str, ProducedField] = Field(default_factory=dict)
    cost: int = 1
    latency_class: LatencyClass = "medium"
    volatility_prior: str = "7d"
    locale_sensitive: list[str] = Field(default_factory=list)
    pii_risk: PiiRisk = "low"
    docs_url: str = ""

    @field_validator("volatility_prior")
    @classmethod
    def _known_volatility(cls, v: str) -> str:
        if v not in VOLATILITY_SECONDS:
            raise ValueError("unknown volatility_prior: " + v)
        return v

    @property
    def volatility_seconds(self) -> int:
        return VOLATILITY_SECONDS[self.volatility_prior]

    @property
    def expected_latency_ms(self) -> int:
        return LATENCY_MS[self.latency_class]

    def root_params(self) -> list[str]:
        """Parameters the caller must supply because nothing produces them."""
        return [name for name, spec in self.requires.items() if spec.is_root_satisfiable]

    def chainable_params(self) -> list[str]:
        return [name for name, spec in self.requires.items() if not spec.is_root_satisfiable]

    def required_groups(self) -> list[list[str]]:
        """Alternative-aware requirement groups.

        ``google_maps_reviews`` accepts either ``data_id`` or ``place_id``;
        this collapses those into one group so pathfinding treats them as a
        single obligation satisfiable either way.
        """
        groups: dict[str, list[str]] = {}
        for name, spec in self.requires.items():
            anchor = spec.alternative_to or name
            groups.setdefault(anchor, [])
            if name not in groups[anchor]:
                groups[anchor].append(name)
        # Fold any group whose anchor is itself an alternative of another.
        return [sorted(set(members)) for members in groups.values()]

    def search_text(self) -> str:
        parts = [
            self.engine.replace("_", " "),
            self.purpose,
            " ".join(tag.replace("_", " ") for tag in self.capability_tags),
            " ".join(self.requires.keys()),
            " ".join(self.optional[:12]),
        ]
        return " ".join(p for p in parts if p).lower()


class DependencyEdge(BaseModel):
    """``from_engine`` produces ``produces_field``, which satisfies
    ``to_engine.satisfies_param``. Computed from the YAML, never invented."""

    model_config = ConfigDict(extra="forbid")

    from_engine: str
    to_engine: str
    produces_field: str
    satisfies_param: str
    param_type: str = "string"
    fan_out_hint: int = 1
    note: str = ""

    @property
    def key(self) -> str:
        return self.from_engine + "->" + self.to_engine + ":" + self.satisfies_param


class SubstituteEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str
    substitute_engine: str
    coverage: Coverage
    note: str
    shared_tags: list[str] = Field(default_factory=list)
    confidence_penalty: float = 0.1


class CatalogMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str
    released: str = ""
    source: str = ""
    notes: str = ""
    capability_tags: dict[str, str] = Field(default_factory=dict)
    coverage_levels: dict[str, str] = Field(default_factory=dict)
    volatility_priors: dict[str, str] = Field(default_factory=dict)


COVERAGE_PENALTY: dict[str, float] = {"full": 0.05, "partial": 0.15, "narrow": 0.35}


def parse_field_ref(ref: str) -> tuple[str, str] | None:
    """``google_maps.local_results[].data_id`` -> (engine, field path)."""
    match = _FIELD_REF.match(ref.strip())
    if not match:
        return None
    return match.group("engine"), match.group("path")


def checksum(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


__all__ = [
    "COVERAGE_PENALTY",
    "LATENCY_MS",
    "VOLATILITY_SECONDS",
    "CatalogMeta",
    "Coverage",
    "DependencyEdge",
    "EngineSpec",
    "ProducedField",
    "RequiredParam",
    "Substitute",
    "SubstituteEdge",
    "checksum",
    "parse_field_ref",
]
