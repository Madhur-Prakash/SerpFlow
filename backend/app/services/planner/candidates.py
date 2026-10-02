"""Stage D - PATH-FIND AND GENERATE CANDIDATES (section 13).

Multiple candidate plans are mandatory. A single-candidate result is valid only
where no alternative path exists, and the Plan object must record that fact
explicitly. If stage D returns one plan, section 14 has nothing to operate on
and the product thesis is unimplementable - so candidate plurality is a hard
requirement here, not an optimisation.

Candidates are generated three ways:

1. the selected engine's own valid chains (differing in entry point or hops)
2. substitute chains, where a competing engine serves the same capability
3. shallower chains that answer a weaker version of the intent, kept only when
   nothing richer exists
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.catalog.graph import EnginePath, find_paths
from app.services.catalog.loader import CatalogIndex
from app.services.planner.retrieval import Candidate

# A plan the selector endorsed as answering the intent. These compete on
# marginal cost (section 14).
ROLE_ANSWER = "answer"
# A truncation retained for the Plan Inspector and as a last-resort budget
# fallback. A plan nobody chose must never win on price alone - a one-credit
# place lookup is cheaper than a review-ring investigation and answers a
# completely different question.
ROLE_FALLBACK = "fallback"


@dataclass(slots=True)
class CandidatePlan:
    """One complete, executable alternative."""

    label: str
    path: EnginePath
    strategy: str  # primary | substitute | shallow
    confidence: float
    role: str = ROLE_ANSWER
    coverage: str = "full"
    substitute_of: str | None = None
    trade_off_note: str | None = None
    rationale: str = ""

    # populated by the cost model in services/planner/cost.py
    naive_cost: int = 0
    marginal_cost: int = 0
    warm_step_indices: list[int] = field(default_factory=list)
    cache_state: list[dict[str, Any]] = field(default_factory=list)
    naive_rank: int = 0
    marginal_rank: int = 0
    feasible_within_budget: bool = True
    rejection_reason: str | None = None
    selected: bool = False

    @property
    def engines(self) -> list[str]:
        return self.path.engines

    @property
    def signature(self) -> str:
        return self.path.signature

    @property
    def hops(self) -> int:
        return self.path.hops

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "strategy": self.strategy,
            "role": self.role,
            "engines": self.engines,
            "hops": self.hops,
            "confidence": round(self.confidence, 4),
            "coverage": self.coverage,
            "substitute_of": self.substitute_of,
            "trade_off_note": self.trade_off_note,
            "rationale": self.rationale,
            "naive_cost": self.naive_cost,
            "marginal_cost": self.marginal_cost,
            "warm_step_indices": self.warm_step_indices,
            "cache_state": self.cache_state,
            "naive_rank": self.naive_rank,
            "marginal_rank": self.marginal_rank,
            "feasible_within_budget": self.feasible_within_budget,
            "rejection_reason": self.rejection_reason,
            "selected": self.selected,
            "steps": self.path.to_dict()["steps"],
        }


@dataclass(slots=True)
class CandidateSet:
    plans: list[CandidatePlan]
    single_candidate_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.plans)


def _label_for(path: EnginePath, strategy: str) -> str:
    if path.hops == 1:
        return path.engines[0]
    arrow = " -> ".join(path.engines)
    return arrow if strategy == "primary" else arrow


def generate(
    index: CatalogIndex,
    *,
    chosen_engines: list[tuple[str, float]],
    retrieved: list[Candidate],
    available_params: set[str],
    max_candidates: int | None = None,
    max_hops: int | None = None,
    engine_allowlist: list[str] | None = None,
    engine_denylist: list[str] | None = None,
) -> CandidateSet:
    """Build the candidate set for one intent."""
    limit = max_candidates or settings.planner_max_candidates
    hops = max_hops or settings.planner_max_hops
    by_engine = {c.engine: c for c in retrieved}
    allow = set(engine_allowlist or [])
    deny = set(engine_denylist or [])

    def permitted(path_engines: list[str]) -> bool:
        """Engine policy is enforced here, not only at retrieval.

        A substitute or an upstream producer can pull a denied engine back into
        a chain, and the executor would then refuse it mid-run. Rejecting the
        whole path now means the planner never proposes something it is not
        allowed to execute.
        """
        for engine in path_engines:
            if deny and engine in deny:
                return False
            if allow and engine not in allow:
                return False
        return True

    plans: dict[str, CandidatePlan] = {}
    notes: list[str] = []

    # --- 1. the selected engines' own chains -----------------------------
    for engine, confidence in chosen_engines:
        for path in find_paths(index, engine, available_params=available_params, max_hops=hops):
            if path.signature in plans or not permitted(path.engines):
                continue
            plans[path.signature] = CandidatePlan(
                label=_label_for(path, "primary"),
                path=path,
                strategy="primary",
                confidence=confidence,
                coverage="full",
                rationale=(
                    "Direct route to "
                    + engine
                    + " over "
                    + str(path.hops)
                    + " typed dependency hop(s)."
                ),
            )

    # --- 2. substitute chains --------------------------------------------
    for engine, confidence in chosen_engines:
        for sub in index.substitutes_for(engine):
            name = sub.substitute_engine
            if name not in by_engine and not index.has(name):
                continue
            for path in find_paths(index, name, available_params=available_params, max_hops=hops):
                if path.signature in plans or not permitted(path.engines):
                    continue
                penalty = sub.confidence_penalty
                plans[path.signature] = CandidatePlan(
                    label=_label_for(path, "substitute"),
                    path=path,
                    strategy="substitute",
                    confidence=max(0.05, confidence - penalty),
                    coverage=sub.coverage,
                    substitute_of=engine,
                    trade_off_note=sub.note,
                    rationale=(
                        name
                        + " competes with "
                        + engine
                        + " on the "
                        + (", ".join(sub.shared_tags) or "same")
                        + " capability, at "
                        + sub.coverage
                        + " coverage."
                    ),
                )

    # --- 3. shallower chains ---------------------------------------------
    # A shorter chain answers a weaker version of the intent. It is kept so the
    # budget stage always has something cheap to fall back to, but it is ranked
    # with a confidence penalty proportional to what it drops.
    for signature, plan in list(plans.items()):
        if plan.hops < 2:
            continue
        for depth in range(1, plan.hops):
            prefix = plan.path.steps[:depth]
            shallow = EnginePath(steps=[s.clone() for s in prefix], target=prefix[-1].engine)
            if shallow.signature in plans or not permitted(shallow.engines):
                continue
            dropped = plan.engines[depth:]
            plans[shallow.signature] = CandidatePlan(
                label=_label_for(shallow, "shallow"),
                path=shallow,
                strategy="shallow",
                role=ROLE_FALLBACK,
                confidence=max(0.05, plan.confidence - 0.2 * len(dropped)),
                coverage="partial",
                trade_off_note=(
                    "Stops before "
                    + ", ".join(dropped)
                    + ". The result set is correct but shallower: "
                    + _impact_of_dropping(index, dropped)
                ),
                rationale="Truncation of " + signature + " at hop " + str(depth) + ".",
            )

    # Stage B ranks its choices by confidence. The top choice defines the
    # capability the intent is actually asking for; a plan that terminates
    # somewhere else answers a different question and must not win on price.
    target = chosen_engines[0][0] if chosen_engines else ""
    _assign_roles(index, plans, target)
    _demote_truncations(plans)

    ordered = sorted(
        plans.values(),
        key=lambda p: (
            {"primary": 0, "substitute": 1, "shallow": 2}[p.strategy],
            -p.confidence,
            p.path.naive_cost,
        ),
    )

    # Always keep at least one plan per strategy family where one exists, so
    # the set is genuinely diverse rather than six variations of one route.
    # Answering plans are what section 14 re-ranks, so they are kept first and
    # never squeezed out by a cheaper fallback.
    kept: list[CandidatePlan] = [p for p in ordered if p.role == ROLE_ANSWER][:limit]
    for plan in ordered:
        if plan in kept:
            continue
        if len(kept) >= limit + 3:
            break
        kept.append(plan)

    if not kept:
        # No valid path exists at all. The caller raises NoViablePlanError with
        # the parameters that were available, which is far more useful than a
        # guessed plan.
        return CandidateSet(plans=[], single_candidate_reason=None, notes=notes)

    answering = [p for p in kept if p.role == ROLE_ANSWER]
    single_reason: str | None = None
    if len(answering) <= 1:
        only = answering[0] if answering else kept[0]
        single_reason = _explain_single_candidate(index, only)
        notes.append(single_reason)

    return CandidateSet(plans=kept, single_candidate_reason=single_reason, notes=notes)


def _assign_roles(index: CatalogIndex, plans: dict[str, CandidatePlan], target: str) -> None:
    """Answering plans terminate at the target capability or a substitute of it.

    Without this, a one-credit place lookup outranks a review-ring
    investigation purely on cost, and the planner optimises a question nobody
    asked.
    """
    if not target or not index.has(target):
        return
    answer_engines = {target}
    answer_engines |= {s.substitute_engine for s in index.substitutes_for(target)}
    target_tags = set(index.get(target).capability_tags)

    for plan in plans.values():
        terminal = plan.engines[-1]
        if terminal in answer_engines:
            continue
        terminal_tags = (
            set(index.engines[terminal].capability_tags) if index.has(terminal) else set()
        )
        if terminal_tags & target_tags:
            continue
        plan.role = ROLE_FALLBACK
        if not plan.rejection_reason:
            plan.rejection_reason = (
                terminal
                + " answers a different capability ("
                + (", ".join(sorted(terminal_tags)) or "none declared")
                + ") than the selected target "
                + target
                + " ("
                + ", ".join(sorted(target_tags))
                + "), so it is retained as a fallback rather than ranked against it."
            )


def _demote_truncations(plans: dict[str, CandidatePlan]) -> None:
    """Any plan whose engine list is a strict prefix of another plan's is a
    truncation of it, not a peer. Comparing the two on cost is meaningless:
    the shorter one is cheaper precisely because it does less."""
    signatures = {p.signature: p for p in plans.values()}
    for signature, plan in signatures.items():
        prefix = signature + ">"
        if any(other.startswith(prefix) for other in signatures if other != signature):
            plan.role = ROLE_FALLBACK


def _impact_of_dropping(index: CatalogIndex, dropped: list[str]) -> str:
    parts: list[str] = []
    for engine in dropped:
        spec = index.engines.get(engine)
        if spec is None:
            continue
        parts.append(spec.purpose.rstrip("."))
    if not parts:
        return "downstream detail is not retrieved."
    return "; ".join(parts) + " is not retrieved."


def _explain_single_candidate(index: CatalogIndex, plan: CandidatePlan) -> str:
    """Section 15 requires an explicit reason whenever candidate_count == 1."""
    terminal = plan.engines[-1]
    spec = index.engines.get(terminal)
    if spec is not None and spec.single_source_note:
        return (
            "Only one candidate exists: "
            + spec.single_source_note.strip()
            + " No substitute engine in catalog version "
            + index.version
            + " shares its capability, and no alternative path reaches it."
        )
    substitutes = index.substitutes_for(terminal)
    if not substitutes:
        return (
            "Only one candidate exists: no engine in catalog version "
            + index.version
            + " shares a capability tag with "
            + terminal
            + ", so there is no competing route to re-rank against."
        )
    return (
        "Only one candidate exists: "
        + terminal
        + " has declared substitutes ("
        + ", ".join(s.substitute_engine for s in substitutes[:3])
        + ") but none of them is reachable from the parameters this intent supplies."
    )


__all__ = ["ROLE_ANSWER", "ROLE_FALLBACK", "CandidatePlan", "CandidateSet", "generate"]
