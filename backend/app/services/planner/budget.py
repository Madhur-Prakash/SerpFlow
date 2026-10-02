"""Section 16 - budget-aware replanning.

    1. generate candidate plans
    2. calculate marginal costs
    3. identify plans that fit
    4. choose the appropriate valid plan
    5. record what was reduced, if anything

Step 3 is doing more work than it looks. "Identify plans that fit" means every
candidate is reduced to a budget-feasible shape *before* the final ranking, not
after - otherwise two plans are compared at costs neither of them would
actually be executed at.

Every reduction carries a human-readable ``impact_note``. A planner that
silently truncates is worse than one that refuses, because the caller acts on a
result they believe is complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.services.catalog.graph import apply_fan_out_caps
from app.services.catalog.loader import CatalogIndex

if TYPE_CHECKING:
    from app.services.planner.cost import CostedPlan

REDUCTION_SAMPLING = "sampling"
REDUCTION_FAN_OUT_CAP = "fan_out_cap"
REDUCTION_OMITTED_STEP = "omitted_step"


@dataclass(slots=True)
class Reduction:
    type: str
    step: int
    original: int
    reduced: int
    impact_note: str
    engine: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "step": self.step,
            "engine": self.engine,
            "original": self.original,
            "reduced": self.reduced,
            "impact_note": self.impact_note,
        }


@dataclass(slots=True)
class BudgetDecision:
    applied: bool
    reductions: list[Reduction] = field(default_factory=list)
    full_plan_cost: int = 0
    selected_plan_cost: int = 0
    note: str = ""

    def as_dict(self) -> dict[str, Any] | None:
        if not self.applied and not self.reductions:
            return None
        return {
            "applied": self.applied,
            "reductions": [r.as_dict() for r in self.reductions],
            "full_plan_cost": self.full_plan_cost,
            "selected_plan_cost": self.selected_plan_cost,
            "note": self.note,
        }


# What is actually lost when a step's fan-out is cut, per capability.
_IMPACT_BY_TAG: dict[str, str] = {
    "contributor_history": (
        "Contributor sampling reduced; ring-detection recall will be lower - a reviewer "
        "active only on venues outside the sample will not be linked."
    ),
    "place_reviews": (
        "Fewer places have their reviews fetched, so sentiment and reviewer coverage are partial."
    ),
    "product_reviews": "Fewer products have their reviews fetched; rating aggregates are partial.",
    "place_search": "Fewer places are enumerated, so downstream hops see a smaller universe.",
    "product_search": "Fewer products are enumerated; price comparison is over a smaller set.",
    "academic_author": "Fewer author profiles are resolved; co-authorship coverage is partial.",
    "academic_search": "Fewer papers are retrieved; citation coverage is partial.",
    "app_reviews": "Fewer applications have their reviews fetched.",
    "place_photos": "Fewer places have their photographs fetched.",
    "news_search": "Fewer articles are retrieved; coverage of smaller outlets drops first.",
}


def impact_note(index: CatalogIndex, engine: str, original: int, reduced: int) -> str:
    spec = index.engines.get(engine)
    if spec is not None:
        base = ""
        for tag in spec.capability_tags:
            if tag in _IMPACT_BY_TAG:
                base = _IMPACT_BY_TAG[tag]
                break
        if not base:
            base = spec.purpose.rstrip(".") + " is sampled rather than enumerated."
    else:
        base = "This step is sampled rather than enumerated."
    return base + " Reduced from " + str(original) + " to " + str(reduced) + " calls."


def omission_note(index: CatalogIndex, engine: str, step_index: int) -> str:
    spec = index.engines.get(engine)
    purpose = spec.purpose.rstrip(".") if spec else engine
    return (
        purpose
        + " is not executed at all. The result stops at hop "
        + str(step_index)
        + ", and the finding that depends on it is unavailable."
    )


def reduce_to_fit(
    index: CatalogIndex, costed: CostedPlan, cap: int
) -> tuple[bool, list[Reduction]]:
    """Shrink one candidate until its marginal cost fits ``cap``.

    Fan-out is scaled proportionally across every widened step rather than
    squeezing the last hop to one call. The shape of the plan is what makes its
    answer meaningful: a contributor chain sampled 3 places deep and 12
    contributors wide is still a contributor chain, while the same budget spent
    on 18 places and 1 contributor is not.

    Returns ``(fits, reductions)``. ``costed`` is mutated in place when it fits.
    """
    from app.services.planner.cost import StepCost

    if costed.marginal_cost <= cap:
        return True, []

    widened = [s for s in costed.steps if s.fan_out > 1]
    if not widened:
        return _omit_tail(index, costed, cap)

    # Largest scale factor whose resulting marginal cost fits.
    best_scale: float | None = None
    for step_pct in range(100, 0, -1):
        scale = step_pct / 100.0
        projected = 0
        for step in costed.steps:
            fan_out = max(1, int(step.fan_out * scale)) if step.fan_out > 1 else step.fan_out
            projected += 0 if step.warm else _marginal_for(step, fan_out)
        if projected <= cap:
            best_scale = scale
            break

    if best_scale is None:
        return _omit_tail(index, costed, cap)

    reductions: list[Reduction] = []
    caps: dict[int, int] = {}
    new_steps: list[StepCost] = []
    for step in costed.steps:
        fan_out = max(1, int(step.fan_out * best_scale)) if step.fan_out > 1 else step.fan_out
        if fan_out < step.fan_out:
            caps[step.index] = fan_out
            reductions.append(
                Reduction(
                    type=REDUCTION_FAN_OUT_CAP,
                    step=step.index,
                    engine=step.engine,
                    original=step.fan_out,
                    reduced=fan_out,
                    impact_note=impact_note(index, step.engine, step.fan_out, fan_out),
                )
            )
        naive = step.unit_cost * fan_out
        new_steps.append(
            StepCost(
                index=step.index,
                engine=step.engine,
                fan_out=fan_out,
                unit_cost=step.unit_cost,
                naive_cost=naive,
                marginal_cost=0 if step.warm else _marginal_for(step, fan_out),
                warm=step.warm,
                cache_state=step.cache_state,
                freshness_requirement=step.freshness_requirement,
            )
        )

    costed.steps = new_steps
    if caps:
        costed.plan.path = apply_fan_out_caps(costed.plan.path, caps)
    _sync_plan(costed)
    return True, reductions


def _marginal_for(step: Any, fan_out: int) -> int:
    """Marginal cost of a step at a given width.

    The warm portion is an absolute count of calls already satisfiable, so
    narrowing the step does not shrink the saving - it consumes it. A step
    needing 12 calls with 12 warm entries costs nothing.
    """
    if step.warm:
        return 0
    warm_calls = max(0, step.fan_out - (step.marginal_cost // max(1, step.unit_cost)))
    remaining = max(0, fan_out - warm_calls)
    return remaining * step.unit_cost


def _omit_tail(index: CatalogIndex, costed: CostedPlan, cap: int) -> tuple[bool, list[Reduction]]:
    """Last resort: drop terminal steps until the plan fits."""
    from app.services.planner.cost import StepCost

    reductions: list[Reduction] = []
    steps = list(costed.steps)
    current = sum(s.marginal_cost for s in steps)

    while steps and current > cap:
        tail = steps[-1]
        if tail.marginal_cost <= 0 and len(steps) > 1:
            steps.pop()
            continue
        reductions.append(
            Reduction(
                type=REDUCTION_OMITTED_STEP,
                step=tail.index,
                engine=tail.engine,
                original=tail.naive_cost,
                reduced=0,
                impact_note=omission_note(index, tail.engine, tail.index),
            )
        )
        current -= tail.marginal_cost
        steps.pop()

    if not steps or current > cap:
        return False, reductions

    kept = [s.engine for s in steps]
    costed.plan.path.steps = [s for s in costed.plan.path.steps if s.engine in kept][: len(steps)]
    costed.steps = [
        StepCost(
            index=i,
            engine=s.engine,
            fan_out=s.fan_out,
            unit_cost=s.unit_cost,
            naive_cost=s.naive_cost,
            marginal_cost=s.marginal_cost,
            warm=s.warm,
            cache_state=s.cache_state,
            freshness_requirement=s.freshness_requirement,
        )
        for i, s in enumerate(steps)
    ]
    _sync_plan(costed)
    return True, reductions


def _sync_plan(costed: CostedPlan) -> None:
    costed.plan.naive_cost = costed.naive_cost
    costed.plan.marginal_cost = costed.marginal_cost
    costed.plan.warm_step_indices = costed.warm_indices


def project_full_scale(index: CatalogIndex, costed: CostedPlan) -> int:
    """Uncapped projection for the UI (section 70).

    This number is always labelled a projection and is never executed live.
    """
    total = 0
    for step in costed.steps:
        spec = index.engines.get(step.engine)
        total += (spec.cost if spec else 1) * max(1, step.fan_out)
    return total


def build_decision(
    costed: CostedPlan,
    *,
    cap: int | None,
    uncapped_naive: int,
    alternative_note: str = "",
) -> BudgetDecision:
    if cap is None:
        return BudgetDecision(
            applied=False,
            full_plan_cost=uncapped_naive,
            selected_plan_cost=costed.marginal_cost,
            note="No budget supplied; the full plan was selected.",
        )
    if not costed.reductions:
        return BudgetDecision(
            applied=bool(alternative_note),
            full_plan_cost=uncapped_naive,
            selected_plan_cost=costed.marginal_cost,
            note=alternative_note
            or (
                "The selected plan fits within the "
                + str(cap)
                + "-credit budget unmodified ("
                + str(costed.marginal_cost)
                + " marginal credits)."
            ),
        )
    return BudgetDecision(
        applied=True,
        reductions=list(costed.reductions),
        full_plan_cost=uncapped_naive,
        selected_plan_cost=costed.marginal_cost,
        note=(
            (alternative_note + " " if alternative_note else "")
            + "The full plan would cost "
            + str(uncapped_naive)
            + " credits. Fan-out was capped on "
            + str(len([r for r in costed.reductions if r.type == REDUCTION_FAN_OUT_CAP]))
            + " step(s) to fit the "
            + str(cap)
            + "-credit budget."
        ).strip(),
    )


__all__ = [
    "REDUCTION_FAN_OUT_CAP",
    "REDUCTION_OMITTED_STEP",
    "REDUCTION_SAMPLING",
    "BudgetDecision",
    "Reduction",
    "build_decision",
    "impact_note",
    "omission_note",
    "project_full_scale",
    "reduce_to_fit",
]
