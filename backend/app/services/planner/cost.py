"""Section 14 - the cost model and marginal replanning.

This is the thesis.

After stage D produces candidate plans, inspect current cache state for every
step of every candidate, then::

    marginal_cost = sum(cost of steps that actually require live upstream calls)

A warm entry counts toward marginal savings ONLY if it also satisfies the
step's freshness requirement from stage C. Available is not the same as
acceptable.

Candidates are then ranked twice - once on cold cost, once on marginal cost::

    Plan A    cold cost = 4    marginal cost = 4
    Plan B    cold cost = 8    marginal cost = 1

Plan B wins. A planner that only ever compared cold costs would have picked A
and paid four credits to avoid paying one.

When the two rankings disagree, that fact is persisted on the Plan and counted
in ``serpflow_marginal_replan_changed_selection_total``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core import metrics
from app.core.logging import get_logger
from app.services.cache.service import CacheService, CacheState
from app.services.catalog.loader import CatalogIndex
from app.services.planner.budget import Reduction, reduce_to_fit
from app.services.planner.candidates import ROLE_ANSWER, CandidatePlan

log = get_logger("serpflow.planner.cost")

# Coverage is ranked before price, not discounted against it.
#
# A narrow-coverage substitute is cheaper precisely because it answers a
# smaller question: yelp_reviews costs a ninth of the Google Maps contributor
# chain and cannot establish reviewer identity at all. Letting price outrank
# coverage would make the planner optimise a question nobody asked, so cost
# only breaks ties within a coverage band.
COVERAGE_RANK: dict[str, int] = {"full": 0, "partial": 1, "narrow": 2}

# Within a band, a slightly weaker route still has to be meaningfully cheaper.
COVERAGE_MARGIN_PENALTY: dict[str, float] = {"full": 0.0, "partial": 0.25, "narrow": 0.5}


@dataclass(slots=True)
class StepCost:
    index: int
    engine: str
    fan_out: int
    unit_cost: int
    naive_cost: int
    marginal_cost: int
    warm: bool
    cache_state: dict[str, Any]
    freshness_requirement: str


@dataclass(slots=True)
class CostedPlan:
    plan: CandidatePlan
    steps: list[StepCost]
    reductions: list[Reduction] = field(default_factory=list)
    feasible: bool = True
    uncapped_naive_cost: int = 0
    uncapped_marginal_cost: int = 0

    @property
    def naive_cost(self) -> int:
        return sum(s.naive_cost for s in self.steps)

    @property
    def marginal_cost(self) -> int:
        return sum(s.marginal_cost for s in self.steps)

    @property
    def warm_indices(self) -> list[int]:
        return [s.index for s in self.steps if s.warm]

    @property
    def savings(self) -> int:
        return max(0, self.naive_cost - self.marginal_cost)

    @property
    def coverage_penalty(self) -> float:
        return COVERAGE_MARGIN_PENALTY.get(self.plan.coverage, 0.25)

    @property
    def coverage_rank(self) -> int:
        return COVERAGE_RANK.get(self.plan.coverage, 1)

    def marginal_rank_key(self) -> tuple:
        return (
            self.coverage_rank,
            self.marginal_cost + self.coverage_penalty,
            -self.plan.confidence,
            self.naive_cost,
            self.plan.signature,
        )

    def cold_rank_key(self) -> tuple:
        return (
            self.coverage_rank,
            self.naive_cost + self.coverage_penalty,
            -self.plan.confidence,
            self.plan.signature,
        )


@dataclass(slots=True)
class ReplanOutcome:
    """The complete, persistable record of the re-ranking decision."""

    costed: list[CostedPlan]
    selected: CostedPlan
    cold_winner: CostedPlan
    changed_selection: bool
    explanation: str
    budget_cap: int | None = None

    @property
    def candidate_count(self) -> int:
        return len(self.costed)

    @property
    def rankable(self) -> list[CostedPlan]:
        return [c for c in self.costed if c.plan.role == ROLE_ANSWER and c.feasible]


async def evaluate_cache_state(
    cache: CacheService,
    index: CatalogIndex,
    plan: CandidatePlan,
    *,
    parameters: dict[str, Any],
    freshness_by_engine: dict[str, str],
    default_freshness: str = "stable",
) -> CostedPlan:
    """Inspect the cache for every step of one candidate.

    Steps whose parameters are produced upstream are inspected with a
    representative binding rather than a concrete one - the concrete value does
    not exist until the upstream step runs. The representative probe asks the
    honest question: how many calls of this engine, in this partition, under
    this locale, are already satisfiable within the step's freshness bound?
    """
    steps: list[StepCost] = []

    for i, step in enumerate(plan.path.steps):
        spec = index.get(step.engine)
        freshness = freshness_by_engine.get(step.engine, default_freshness)
        unit = spec.cost
        fan_out = max(1, step.fan_out)
        naive = unit * fan_out

        probe = _probe_parameters(step, parameters, spec.optional)
        chained = any(b.source == "chain" for b in step.bindings)

        if chained:
            state, warm_calls = await _inspect_fanout_step(
                cache, step.engine, probe, freshness, fan_out
            )
            marginal = max(0, (fan_out - warm_calls)) * unit
            warm = warm_calls >= fan_out
        else:
            state = await cache.inspect(step.engine, probe, freshness=freshness)
            warm = state.is_warm
            marginal = 0 if warm else naive

        steps.append(
            StepCost(
                index=i,
                engine=step.engine,
                fan_out=fan_out,
                unit_cost=unit,
                naive_cost=naive,
                marginal_cost=marginal,
                warm=warm,
                cache_state={**state.as_dict(), "step": i, "engine": step.engine},
                freshness_requirement=freshness,
            )
        )

    costed = CostedPlan(plan=plan, steps=steps)
    costed.uncapped_naive_cost = costed.naive_cost
    costed.uncapped_marginal_cost = costed.marginal_cost
    _sync(costed)
    return costed


def _sync(costed: CostedPlan) -> None:
    costed.plan.naive_cost = costed.naive_cost
    costed.plan.marginal_cost = costed.marginal_cost
    costed.plan.warm_step_indices = costed.warm_indices
    costed.plan.cache_state = [s.cache_state for s in costed.steps]


def _probe_parameters(step: Any, parameters: dict[str, Any], optional: list[str]) -> dict[str, Any]:
    """Parameters for a cache probe on one step.

    Root-bound parameters are used as-is. Chained parameters have no value yet,
    so they are omitted and the probe falls back to the locale partition - the
    honest approximation, rather than a fabricated identifier that would
    guarantee a miss and make every chain look cold.
    """
    probe: dict[str, Any] = {}
    for binding in step.bindings:
        if binding.source == "root" and binding.param in parameters:
            probe[binding.param] = parameters[binding.param]
    for name in ("gl", "hl", "location"):
        if name in parameters and (name in optional or name in ("gl", "hl")):
            probe[name] = parameters[name]
    return probe


async def _inspect_fanout_step(
    cache: CacheService,
    engine: str,
    probe: dict[str, Any],
    freshness: str,
    fan_out: int,
) -> tuple[CacheState, int]:
    """Cache state for a step whose identifiers come from upstream.

    Returns the representative state and the number of calls already warm,
    counted as durable entries for this engine in this partition that still
    satisfy the freshness bound. A step needing 12 calls with 12 such entries
    costs nothing; one needing 80 with 12 costs 68.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from app.db.models.caching import CacheEntry
    from app.integrations.llm.base import freshness_max_age_seconds
    from app.services.cache.keys import partition_key

    partition = partition_key(cache.project_id, cache.org_id, scope=cache.scope)
    cutoff = datetime.now(UTC) - timedelta(seconds=freshness_max_age_seconds(freshness))

    query = select(func.count(CacheEntry.id)).where(
        CacheEntry.partition_key == partition,
        CacheEntry.engine == engine,
        CacheEntry.invalidated_at.is_(None),
        CacheEntry.expires_at > datetime.now(UTC),
        CacheEntry.created_at >= cutoff,
    )
    if probe.get("gl"):
        query = query.where(CacheEntry.gl == str(probe["gl"]))
    if probe.get("hl"):
        query = query.where(CacheEntry.hl == str(probe["hl"]))

    try:
        warm_entries = int(await cache.session.scalar(query) or 0)
    except Exception:
        warm_entries = 0

    warm_calls = min(fan_out, warm_entries)
    if warm_calls == 0:
        return (
            CacheState(
                layer="miss",
                freshness_requirement=freshness,
                reason=(
                    "no entries for "
                    + engine
                    + " in this partition satisfy the "
                    + freshness
                    + " bound, so all "
                    + str(fan_out)
                    + " call(s) would be live"
                ),
            ),
            0,
        )

    return (
        CacheState(
            layer="exact" if warm_calls >= fan_out else "semantic",
            available=True,
            acceptable=True,
            freshness_requirement=freshness,
            reason=(
                str(warm_calls)
                + " of "
                + str(fan_out)
                + " "
                + engine
                + " call(s) are already warm and within the "
                + freshness
                + " bound"
            ),
        ),
        warm_calls,
    )


async def replan_on_marginal_cost(
    cache: CacheService,
    index: CatalogIndex,
    candidates: list[CandidatePlan],
    *,
    parameters: dict[str, Any],
    freshness_by_engine: dict[str, str],
    default_freshness: str = "stable",
    project_id: str = "",
    budget: int | None = None,
    remaining: int | None = None,
) -> ReplanOutcome:
    """Cost every candidate, reduce to fit, rank twice, record what changed."""
    costed: list[CostedPlan] = []
    for plan in candidates:
        costed.append(
            await evaluate_cache_state(
                cache,
                index,
                plan,
                parameters=parameters,
                freshness_by_engine=freshness_by_engine,
                default_freshness=default_freshness,
            )
        )

    # ---- section 16 step 3: identify plans that fit ---------------------
    # Reduction happens before ranking, so two candidates are compared at the
    # costs they would actually be executed at rather than at costs neither
    # would ever incur.
    cap = budget if budget is not None else remaining
    if cap is not None and remaining is not None:
        cap = min(cap, remaining)

    if cap is not None:
        for item in costed:
            fits, reductions = reduce_to_fit(index, item, cap)
            item.reductions = reductions
            item.feasible = fits
            item.plan.feasible_within_budget = fits
            _sync(item)
            if not fits:
                item.plan.rejection_reason = (
                    "Cannot fit the "
                    + str(cap)
                    + "-credit budget even after fan-out reduction; the minimum viable "
                    + "shape still costs "
                    + str(item.marginal_cost)
                    + " credits."
                )

    # ---- rank ------------------------------------------------------------
    # Only plans the selector endorsed as answering the intent compete.
    # Truncations are retained for the Plan Inspector and as a last-resort
    # fallback, but a plan nobody chose should never win on price alone.
    rankable = [c for c in costed if c.plan.role == ROLE_ANSWER and c.feasible]
    if not rankable:
        rankable = [c for c in costed if c.feasible] or costed

    cold_order = sorted(rankable, key=lambda c: c.cold_rank_key())
    for rank, item in enumerate(cold_order):
        item.plan.naive_rank = rank

    marginal_order = sorted(rankable, key=lambda c: c.marginal_rank_key())
    for rank, item in enumerate(marginal_order):
        item.plan.marginal_rank = rank

    fallback_rank = len(rankable)
    for item in costed:
        if item not in rankable:
            item.plan.naive_rank = fallback_rank
            item.plan.marginal_rank = fallback_rank

    cold_winner = cold_order[0]
    selected = marginal_order[0]
    changed = selected.plan.signature != cold_winner.plan.signature

    explanation = _explain(selected, cold_winner, changed, cap)

    if changed:
        metrics.marginal_replan_changed_selection_total.labels(
            project_id=metrics.safe_label(project_id)
        ).inc()
        log.info(
            "marginal replan changed selection",
            extra={
                "event": "planner.replan_changed_selection",
                "cold_winner": cold_winner.plan.signature,
                "selected": selected.plan.signature,
                "cold_winner_cost": cold_winner.naive_cost,
                "selected_naive": selected.naive_cost,
                "selected_marginal": selected.marginal_cost,
            },
        )

    if selected.savings > 0:
        metrics.marginal_credits_avoided_total.labels(
            project_id=metrics.safe_label(project_id)
        ).inc(selected.savings)

    for item in costed:
        item.plan.selected = item is selected
        if item is not selected and not item.plan.rejection_reason:
            item.plan.rejection_reason = _rejection_reason(item, selected)

    return ReplanOutcome(
        costed=costed,
        selected=selected,
        cold_winner=cold_winner,
        changed_selection=changed,
        explanation=explanation,
        budget_cap=cap,
    )


def _explain(selected: CostedPlan, cold_winner: CostedPlan, changed: bool, cap: int | None) -> str:
    if changed:
        return (
            "Cache-aware replanning changed the selected plan. Ranked on cold cost alone, "
            + cold_winner.plan.signature
            + " would have won at "
            + str(cold_winner.naive_cost)
            + " credits. "
            + selected.plan.signature
            + " costs "
            + str(selected.naive_cost)
            + " credits cold, but "
            + str(len(selected.warm_indices))
            + " of its "
            + str(len(selected.steps))
            + " steps are already warm and still satisfy their freshness requirements, "
            + "so its marginal cost is "
            + str(selected.marginal_cost)
            + " against "
            + str(cold_winner.marginal_cost)
            + " for the cold winner."
        )
    if selected.savings > 0:
        return (
            selected.plan.signature
            + " wins on both rankings. "
            + str(len(selected.warm_indices))
            + " of its "
            + str(len(selected.steps))
            + " steps are warm, cutting the cost from "
            + str(selected.naive_cost)
            + " to "
            + str(selected.marginal_cost)
            + " credits, but it would have been selected cold as well."
        )
    suffix = " within the " + str(cap) + "-credit budget." if cap is not None else "."
    return (
        selected.plan.signature
        + " wins on both rankings with nothing warm, so marginal cost equals cold cost at "
        + str(selected.naive_cost)
        + " credits"
        + suffix
    )


def _rejection_reason(losing: CostedPlan, winner: CostedPlan) -> str:
    """Why this candidate lost. Surfaced verbatim in the Plan Inspector."""
    from app.services.planner.candidates import ROLE_FALLBACK

    prefix = ""
    if losing.plan.trade_off_note:
        prefix = losing.plan.trade_off_note.strip().rstrip(".") + ". "

    if losing.plan.role == ROLE_FALLBACK:
        return (
            prefix
            + "Retained as a budget fallback only: it is a truncation of a fuller plan and "
            + "answers a weaker question, so it does not compete on cost."
        )

    if losing.marginal_cost > winner.marginal_cost:
        detail = (
            " ("
            + str(len(losing.warm_indices))
            + " warm step(s) against "
            + str(len(winner.warm_indices))
            + ")"
            if losing.warm_indices or winner.warm_indices
            else ""
        )
        return (
            prefix
            + "Marginal cost "
            + str(losing.marginal_cost)
            + " against "
            + str(winner.marginal_cost)
            + " for the selected plan"
            + detail
            + "."
        )
    if losing.marginal_cost == winner.marginal_cost:
        if losing.plan.coverage != "full":
            return (
                prefix
                + "Same marginal cost as the selected plan, but only "
                + losing.plan.coverage
                + " coverage."
            )
        return (
            prefix
            + "Same marginal cost, but lower selector confidence ("
            + str(round(losing.plan.confidence, 2))
            + " against "
            + str(round(winner.plan.confidence, 2))
            + ")."
        )
    return (
        prefix
        + "Cheaper on the margin at "
        + str(losing.marginal_cost)
        + " credits, but "
        + losing.plan.coverage
        + " coverage does not answer the intent as completely."
    )


def summarize(outcome: ReplanOutcome) -> dict[str, Any]:
    return {
        "candidate_count": outcome.candidate_count,
        "selected": outcome.selected.plan.signature,
        "cold_winner": outcome.cold_winner.plan.signature,
        "changed_selection": outcome.changed_selection,
        "naive_cost": outcome.selected.naive_cost,
        "marginal_cost": outcome.selected.marginal_cost,
        "savings": outcome.selected.savings,
        "warm_steps": outcome.selected.warm_indices,
        "budget_cap": outcome.budget_cap,
        "explanation": outcome.explanation,
        "candidates": [
            {
                "signature": c.plan.signature,
                "role": c.plan.role,
                "naive_cost": c.naive_cost,
                "marginal_cost": c.marginal_cost,
                "uncapped_naive_cost": c.uncapped_naive_cost,
                "naive_rank": c.plan.naive_rank,
                "marginal_rank": c.plan.marginal_rank,
                "coverage": c.plan.coverage,
                "feasible": c.feasible,
                "warm_steps": c.warm_indices,
                "reductions": [r.as_dict() for r in c.reductions],
            }
            for c in outcome.costed
        ],
    }


__all__ = [
    "COVERAGE_MARGIN_PENALTY",
    "COVERAGE_RANK",
    "CostedPlan",
    "ReplanOutcome",
    "StepCost",
    "evaluate_cache_state",
    "replan_on_marginal_cost",
    "summarize",
]
