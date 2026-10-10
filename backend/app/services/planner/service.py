"""The planner (section 13, stages A-D, plus 14 and 16).

    intent
    -> multiple candidate plans        (stages A-D)
    -> inspect cache state             (section 14)
    -> calculate marginal cost
    -> re-rank plans
    -> select cheapest valid warm-aware plan
    -> check budget                    (section 16)

Every stage emits a progress event. Those events are what the UI pipeline
animation is driven from (section 42): real backend stage transitions over SSE,
never a frontend timer.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core import metrics, telemetry
from app.core.config import settings
from app.core.exceptions import NoViablePlanError
from app.core.logging import get_logger
from app.core.text import adapt_query
from app.db.models.planning import Plan, PlanCandidate
from app.integrations.llm import LLMAdapter, get_llm
from app.integrations.llm.base import stricter_freshness
from app.services.cache.service import CacheService
from app.services.catalog.loader import CatalogIndex, load_catalog
from app.services.planner import candidates as stage_d
from app.services.planner import retrieval as stage_a
from app.services.planner.budget import BudgetDecision, build_decision, project_full_scale
from app.services.planner.cost import CostedPlan, ReplanOutcome, replan_on_marginal_cost

log = get_logger("serpflow.planner")

ProgressFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]

# The stage sequence the UI animates (section 69). Emitted in this exact order.
STAGES = [
    ("analyzing_intent", "Analyzing intent"),
    ("finding_candidates", "Finding candidate engines"),
    ("synthesizing_parameters", "Synthesizing parameters"),
    ("inferring_freshness", "Inferring freshness requirements"),
    ("finding_paths", "Finding valid paths"),
    ("generating_candidates", "Generating candidate plans"),
    ("inspecting_cache", "Inspecting cache state"),
    ("calculating_marginal_cost", "Calculating marginal cost"),
    ("reranking_plans", "Re-ranking plans"),
    ("checking_budget", "Checking budget"),
    ("executing", "Executing required steps"),
]


@dataclass(slots=True)
class PlanResult:
    plan: Plan
    selected: CostedPlan
    outcome: ReplanOutcome
    budget: BudgetDecision
    stage_trace: list[dict[str, Any]] = field(default_factory=list)

    @property
    def steps(self) -> list[dict[str, Any]]:
        return self.plan.steps


class PlannerService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        org_id: str,
        project_id: str,
        principal_id: str | None = None,
        llm: LLMAdapter | None = None,
        catalog: CatalogIndex | None = None,
        cache: CacheService | None = None,
        mode: str = "replay",
        engine_allowlist: list[str] | None = None,
        engine_denylist: list[str] | None = None,
        semantic_threshold: float | None = None,
        cache_scope: str | None = None,
    ) -> None:
        self.session = session
        self.org_id = org_id
        self.project_id = project_id
        self.principal_id = principal_id
        self.llm = llm or get_llm()
        self.catalog = catalog or load_catalog()
        self.cache = cache or CacheService(
            session,
            org_id=org_id,
            project_id=project_id,
            scope=cache_scope,
            semantic_threshold=semantic_threshold,
        )
        self.mode = mode
        self.engine_allowlist = engine_allowlist or []
        self.engine_denylist = engine_denylist or []
        self._trace: list[dict[str, Any]] = []
        self._started = 0.0

    # ------------------------------------------------------------- progress
    async def _emit(
        self, progress: ProgressFn | None, stage: str, status: str, detail: dict[str, Any]
    ) -> None:
        elapsed = (time.perf_counter() - self._started) * 1000.0 if self._started else 0.0
        record = {
            "stage": stage,
            "status": status,
            "elapsed_ms": round(elapsed, 2),
            "detail": detail,
        }
        self._trace.append(record)
        if progress is not None:
            await progress(stage, status, {**detail, "elapsed_ms": round(elapsed, 2)})

    # ----------------------------------------------------------------- plan
    async def plan(
        self,
        intent: str,
        *,
        budget: int | None = None,
        remaining_budget: int | None = None,
        progress: ProgressFn | None = None,
        persist: bool = True,
    ) -> PlanResult:
        self._started = time.perf_counter()
        self._trace = []

        with telemetry.span(
            telemetry.SPAN_PLAN,
            **{
                "serpflow.intent_length": len(intent),
                "serpflow.catalog_version": self.catalog.version,
                "serpflow.mode": self.mode,
            },
        ):
            await self._emit(progress, "analyzing_intent", "running", {"intent": intent})

            # ---- Stage A: RETRIEVE ---------------------------------------
            stage_started = time.perf_counter()
            with telemetry.span(telemetry.SPAN_CATALOG_RETRIEVE):
                retrieved = stage_a.retrieve(
                    self.catalog,
                    intent,
                    engine_allowlist=self.engine_allowlist,
                    engine_denylist=self.engine_denylist,
                )
            metrics.plan_latency_seconds.labels(stage="retrieve").observe(
                time.perf_counter() - stage_started
            )
            if not retrieved:
                raise NoViablePlanError(
                    "No engine in catalog version "
                    + self.catalog.version
                    + " is permitted by this project's engine policy.",
                )
            summary = stage_a.summarize(retrieved)
            await self._emit(progress, "analyzing_intent", "complete", {"intent": intent})
            await self._emit(progress, "finding_candidates", "running", summary)

            # ---- Stage B: SELECT -----------------------------------------
            stage_started = time.perf_counter()
            with telemetry.span(telemetry.SPAN_PLAN_SELECT):
                selection = await self.llm.select_engines(
                    intent, [c.to_payload() for c in retrieved], max_select=3
                )
            metrics.plan_latency_seconds.labels(stage="select").observe(
                time.perf_counter() - stage_started
            )
            if not selection.chosen:
                raise NoViablePlanError("The selector could not choose an engine for this intent.")

            chosen = [(c.engine, c.confidence) for c in selection.chosen]
            telemetry.set_attributes(
                **{
                    "serpflow.chosen_engine": chosen[0][0],
                    "serpflow.confidence": chosen[0][1],
                    "serpflow.candidates": len(retrieved),
                    "serpflow.rejected": len(selection.rejected),
                }
            )
            await self._emit(
                progress,
                "finding_candidates",
                "complete",
                {
                    **summary,
                    "chosen": [c.engine for c in selection.chosen],
                    "rejected_count": len(selection.rejected),
                    "provider": selection.provider,
                    "model": selection.model,
                },
            )

            # ---- Stage C: SYNTHESIZE -------------------------------------
            await self._emit(progress, "synthesizing_parameters", "running", {})
            stage_started = time.perf_counter()
            specs = [
                {
                    "engine": c.engine,
                    "requires": {
                        k: v.model_dump() for k, v in self.catalog.get(c.engine).requires.items()
                    },
                    "optional": self.catalog.get(c.engine).optional,
                    "locale_sensitive": self.catalog.get(c.engine).locale_sensitive,
                    "volatility_prior": self.catalog.get(c.engine).volatility_prior,
                }
                for c in selection.chosen
            ]
            with telemetry.span(telemetry.SPAN_PLAN_SYNTHESIZE):
                synthesis = await self.llm.synthesize(intent, specs)
            metrics.plan_latency_seconds.labels(stage="synthesize").observe(
                time.perf_counter() - stage_started
            )
            parameters = dict(synthesis.parameters)
            await self._emit(
                progress,
                "synthesizing_parameters",
                "complete",
                {
                    "parameters": parameters,
                    "locale": synthesis.locale,
                    "entities": synthesis.entities[:8],
                    "query_class": synthesis.query_class,
                },
            )

            # ---- Stage C: FRESHNESS INFERENCE ----------------------------
            await self._emit(progress, "inferring_freshness", "running", {})
            freshness_by_engine = self._infer_freshness_per_engine(intent, synthesis)
            default_freshness = synthesis.freshness
            await self._emit(
                progress,
                "inferring_freshness",
                "complete",
                {
                    "freshness": default_freshness,
                    "signals": synthesis.freshness_signals[:4],
                    "per_engine": freshness_by_engine,
                },
            )

            # ---- Stage D: PATH-FIND --------------------------------------
            await self._emit(progress, "finding_paths", "running", {})
            available = self._available_params(parameters)
            stage_started = time.perf_counter()
            with telemetry.span(telemetry.SPAN_PLAN_PATHFIND):
                candidate_set = stage_d.generate(
                    self.catalog,
                    chosen_engines=chosen,
                    retrieved=retrieved,
                    available_params=available,
                    max_candidates=settings.planner_max_candidates,
                    max_hops=settings.planner_max_hops,
                    engine_allowlist=self.engine_allowlist,
                    engine_denylist=self.engine_denylist,
                )
            metrics.plan_latency_seconds.labels(stage="pathfind").observe(
                time.perf_counter() - stage_started
            )
            if not candidate_set.plans:
                raise NoViablePlanError(
                    "No valid dependency path reaches "
                    + chosen[0][0]
                    + " from the parameters this intent supplies ("
                    + ", ".join(sorted(available))
                    + ").",
                    details={
                        "chosen": [e for e, _ in chosen],
                        "available_params": sorted(available),
                    },
                )
            await self._emit(
                progress,
                "finding_paths",
                "complete",
                {"paths": [p.signature for p in candidate_set.plans]},
            )

            # ---- Stage D: CANDIDATE PLANS --------------------------------
            await self._emit(progress, "generating_candidates", "running", {})
            with telemetry.span(
                telemetry.SPAN_PLAN_CANDIDATES,
                **{"serpflow.candidate_count": candidate_set.count},
            ):
                pass
            metrics.plan_candidates_count.observe(candidate_set.count)
            await self._emit(
                progress,
                "generating_candidates",
                "complete",
                {
                    "candidate_count": candidate_set.count,
                    "candidates": [
                        {
                            "label": p.label,
                            "strategy": p.strategy,
                            "engines": p.engines,
                            "cold_cost": p.path.naive_cost,
                        }
                        for p in candidate_set.plans
                    ],
                    "single_candidate_reason": candidate_set.single_candidate_reason,
                },
            )

            # ---- Section 14: CACHE STATE + MARGINAL COST -----------------
            await self._emit(progress, "inspecting_cache", "running", {})
            stage_started = time.perf_counter()
            with telemetry.span(telemetry.SPAN_PLAN_MARGINAL_COST):
                outcome = await replan_on_marginal_cost(
                    self.cache,
                    self.catalog,
                    candidate_set.plans,
                    parameters=parameters,
                    freshness_by_engine=freshness_by_engine,
                    default_freshness=default_freshness,
                    project_id=self.project_id,
                    budget=budget,
                    remaining=remaining_budget,
                )
            metrics.plan_latency_seconds.labels(stage="marginal_cost").observe(
                time.perf_counter() - stage_started
            )
            warm_total = sum(len(c.warm_indices) for c in outcome.costed)
            await self._emit(
                progress,
                "inspecting_cache",
                "complete",
                {
                    "warm_steps_found": warm_total,
                    "per_candidate": [
                        {"plan": c.plan.signature, "warm_steps": c.warm_indices}
                        for c in outcome.costed
                    ],
                },
            )

            await self._emit(
                progress,
                "calculating_marginal_cost",
                "complete",
                {
                    "candidates": [
                        {
                            "plan": c.plan.signature,
                            "naive_cost": c.naive_cost,
                            "marginal_cost": c.marginal_cost,
                        }
                        for c in outcome.costed
                    ]
                },
            )

            await self._emit(
                progress,
                "reranking_plans",
                "complete",
                {
                    "cold_winner": outcome.cold_winner.plan.signature,
                    "selected": outcome.selected.plan.signature,
                    "changed_selection": outcome.changed_selection,
                    "explanation": outcome.explanation,
                },
            )

            # ---- Section 16: BUDGET --------------------------------------
            # Reduction already happened inside the re-ranking stage, because
            # "identify plans that fit" has to precede "choose the appropriate
            # valid plan". This stage reports what that cost.
            await self._emit(progress, "checking_budget", "running", {"budget": budget})
            selected = outcome.selected
            infeasible = [c for c in outcome.costed if not c.feasible]
            alternative_note = ""
            if infeasible:
                alternative_note = (
                    str(len(infeasible))
                    + " candidate(s) could not be reduced to fit and were excluded."
                )
            budget_decision = build_decision(
                selected,
                cap=outcome.budget_cap,
                uncapped_naive=selected.uncapped_naive_cost,
                alternative_note=alternative_note,
            )
            await self._emit(
                progress,
                "checking_budget",
                "complete",
                {
                    "budget": budget,
                    "applied": budget_decision.applied,
                    "reductions": [r.as_dict() for r in budget_decision.reductions],
                    "note": budget_decision.note,
                    "selected_plan_cost": budget_decision.selected_plan_cost,
                },
            )

            metrics.plan_confidence.observe(selected.plan.confidence)
            total_ms = (time.perf_counter() - self._started) * 1000.0
            metrics.plan_latency_seconds.labels(stage="total").observe(total_ms / 1000.0)

            plan_row = self._build_plan_row(
                intent=intent,
                synthesis_parameters=parameters,
                selection_rejected=selection.rejected,
                freshness_by_engine=freshness_by_engine,
                default_freshness=default_freshness,
                freshness_signals=synthesis.freshness_signals,
                outcome=outcome,
                selected=selected,
                budget_decision=budget_decision,
                candidate_set=candidate_set,
                budget=budget,
                planner_latency_ms=total_ms,
                provider=selection.provider,
                model=selection.model,
            )

            if persist:
                self.session.add(plan_row)
                await self.session.flush()
                # Hold the rows locally. Reading plan_row.candidates here would
                # trigger a lazy load outside the async context.
                candidate_rows = [
                    self._build_candidate_row(plan_row.id, costed, selected)
                    for costed in outcome.costed
                ]
                self.session.add_all(candidate_rows)
                await self.session.flush()
                plan_row.selected_candidate_id = next(
                    (row.id for row in candidate_rows if row.selected), None
                )
                plan_row.cold_winner_candidate_id = next(
                    (
                        row.id
                        for row in candidate_rows
                        if row.label == outcome.cold_winner.plan.label
                    ),
                    plan_row.cold_winner_candidate_id,
                )
                # Mark the relationship loaded without emitting a query.
                # Serializers read it immediately, and both a lazy load and an
                # ordinary assignment (which loads the old collection to diff
                # against) would fire IO outside the async context.
                set_committed_value(plan_row, "candidates", candidate_rows)
            else:
                set_committed_value(plan_row, "candidates", [])

            return PlanResult(
                plan=plan_row,
                selected=selected,
                outcome=outcome,
                budget=budget_decision,
                stage_trace=list(self._trace),
            )

    # ------------------------------------------------------------- internals
    def _infer_freshness_per_engine(self, intent: str, synthesis: Any) -> dict[str, str]:
        """Per-engine freshness, tightened by each engine's volatility prior.

        A single intent-level level is not enough: the same intent may touch a
        15m-prior engine and a 30d-prior one, and section 14 needs the right
        acceptability bar for each step independently.
        """
        from app.core.text import infer_freshness

        out: dict[str, str] = {}
        for name, spec in self.catalog.engines.items():
            level, _ = infer_freshness(
                intent,
                volatility_prior=spec.volatility_prior,
                query_class=getattr(synthesis, "query_class", None),
            )
            # The intent-level requirement is a floor that an engine prior may
            # tighten but never relax: "latest reviews" stays fresh even on a
            # 30d-prior engine.
            out[name] = stricter_freshness(level, synthesis.freshness)
        return out

    def _available_params(self, parameters: dict[str, Any]) -> set[str]:
        """Parameter names the caller effectively supplied.

        The free-text query maps onto whatever each engine calls it, so ``q``
        implies ``query``, ``text``, ``term`` and the rest. Without this, a
        perfectly valid path to ``yelp`` or ``yandex`` would be discarded
        because the synthesised parameter happened to be named ``q``.
        """
        available = {k for k, v in parameters.items() if v not in (None, "")}
        if available & {"q", "query", "text", "search_query", "term", "p", "k", "_nkw"}:
            available |= {
                "q",
                "query",
                "text",
                "search_query",
                "term",
                "p",
                "k",
                "_nkw",
                "find_desc",
                "mauthors",
                "keyword",
            }
        if "location" in available:
            available |= {"find_loc", "l", "delivery_zip"}
        if "date" in available:
            available |= {"outbound_date", "check_in_date", "check_out_date"}
        # A two-place intent supplies the endpoints a routing engine needs.
        if {"departure_id", "arrival_id"} <= available or " to " in (
            " " + str(parameters.get("q", "")).lower() + " "
        ):
            available |= {"start_addr", "end_addr"}
        return available

    def _build_plan_row(
        self,
        *,
        intent: str,
        synthesis_parameters: dict[str, Any],
        selection_rejected: list[dict[str, Any]],
        freshness_by_engine: dict[str, str],
        default_freshness: str,
        freshness_signals: list[str],
        outcome: ReplanOutcome,
        selected: CostedPlan,
        budget_decision: BudgetDecision,
        candidate_set: stage_d.CandidateSet,
        budget: int | None,
        planner_latency_ms: float,
        provider: str,
        model: str,
    ) -> Plan:
        steps = []
        for i, step in enumerate(selected.plan.path.steps):
            spec = self.catalog.get(step.engine)
            costed_step = next((s for s in selected.steps if s.index == i), None)
            steps.append(
                {
                    "index": i,
                    "engine": step.engine,
                    "label": spec.purpose,
                    "depends_on": step.depends_on,
                    "fan_out": step.fan_out,
                    "cost": spec.cost,
                    "pii_risk": spec.pii_risk,
                    "bindings": [b.to_dict() for b in step.bindings],
                    "parameters": self._bind_step_parameters(step, synthesis_parameters, spec),
                    "freshness_requirement": freshness_by_engine.get(
                        step.engine, default_freshness
                    ),
                    "warm": bool(costed_step and costed_step.warm),
                    "cache_state": costed_step.cache_state if costed_step else {},
                }
            )

        warm_steps = [
            {
                "index": s.index,
                "engine": s.engine,
                "layer": s.cache_state.get("layer"),
                "age_seconds": s.cache_state.get("age_seconds"),
                "credits_avoided": s.naive_cost - s.marginal_cost,
                "reason": s.cache_state.get("reason"),
            }
            for s in selected.steps
            if s.warm or s.marginal_cost < s.naive_cost
        ]

        return Plan(
            org_id=self.org_id,
            project_id=self.project_id,
            principal_id=self.principal_id,
            intent=intent,
            normalized_intent=str(synthesis_parameters.get("q", intent)),
            steps=steps,
            parameter_bindings=synthesis_parameters,
            naive_cost=selected.naive_cost,
            marginal_cost=selected.marginal_cost,
            projected_full_scale_cost=selected.uncapped_naive_cost
            or project_full_scale(self.catalog, selected),
            warm_steps=warm_steps,
            freshness_requirements=[
                {
                    "engine": s["engine"],
                    "step": s["index"],
                    "requirement": s["freshness_requirement"],
                    "signals": freshness_signals[:4],
                }
                for s in steps
            ],
            budget_reduction=budget_decision.as_dict(),
            confidence=selected.plan.confidence,
            catalog_version=self.catalog.version,
            candidate_count=outcome.candidate_count,
            single_candidate_reason=candidate_set.single_candidate_reason,
            rejected_alternatives=[
                {
                    "plan": c.plan.signature,
                    "label": c.plan.label,
                    "strategy": c.plan.strategy,
                    "engines": c.plan.engines,
                    "coverage": c.plan.coverage,
                    "naive_cost": c.naive_cost,
                    "marginal_cost": c.marginal_cost,
                    "naive_rank": c.plan.naive_rank,
                    "marginal_rank": c.plan.marginal_rank,
                    "warm_steps": c.warm_indices,
                    "reason": c.plan.rejection_reason,
                    "trade_off_note": c.plan.trade_off_note,
                    "feasible_within_budget": c.plan.feasible_within_budget,
                    "role": c.plan.role,
                    "uncapped_naive_cost": c.uncapped_naive_cost,
                    "reductions": [r.as_dict() for r in c.reductions],
                }
                for c in outcome.costed
                if c is not selected
            ],
            rejected_engines=selection_rejected,
            # Set to the persisted PlanCandidate id once those rows exist.
            cold_winner_candidate_id=None,
            marginal_replan_changed_selection=outcome.changed_selection,
            replan_explanation=outcome.explanation,
            budget_limit=budget,
            planner_latency_ms=planner_latency_ms,
            mode=self.mode,
            stage_trace=[
                {**t, "provider": provider, "model": model}
                if t["stage"] == "finding_candidates"
                else t
                for t in self._trace
            ],
        )

    def _bind_step_parameters(
        self, step: Any, parameters: dict[str, Any], spec: Any
    ) -> dict[str, Any]:
        """Concrete parameters for one step.

        Chained parameters are left as placeholders; the executor fills them in
        from the upstream step's real output at run time.
        """
        bound: dict[str, Any] = {}
        query_value = parameters.get("q")
        for binding in step.bindings:
            if binding.source == "root":
                if binding.param in parameters:
                    bound[binding.param] = parameters[binding.param]
                elif query_value is not None:
                    bound[binding.param] = query_value
            else:
                bound[binding.param] = {
                    "$from_step": binding.from_step,
                    "$field": binding.from_field,
                }
        for name in spec.locale_sensitive:
            if name in parameters:
                bound[name] = parameters[name]
        for name in ("gl", "hl"):
            if name in parameters and name in spec.optional:
                bound[name] = parameters[name]
        if "location" in parameters and "location" in spec.optional:
            bound["location"] = parameters["location"]
        # Some engines take an identifier rather than a sentence in their query
        # slot (Google Finance wants "NVDA:NASDAQ"); reshape root-bound values.
        for binding in step.bindings:
            if binding.source == "root" and isinstance(bound.get(binding.param), str):
                bound[binding.param] = adapt_query(spec.engine, bound[binding.param])
        return bound

    def _build_candidate_row(
        self, plan_id: str, costed: CostedPlan, selected: CostedPlan
    ) -> PlanCandidate:
        plan = costed.plan
        return PlanCandidate(
            org_id=self.org_id,
            plan_id=plan_id,
            label=plan.label,
            strategy=plan.strategy,
            engines=plan.engines,
            steps=[s.to_dict() for s in plan.path.steps],
            hops=plan.hops,
            naive_cost=costed.naive_cost,
            marginal_cost=costed.marginal_cost,
            warm_step_indices=costed.warm_indices,
            cache_state=[s.cache_state for s in costed.steps],
            coverage=plan.coverage,
            confidence=plan.confidence,
            naive_rank=plan.naive_rank,
            marginal_rank=plan.marginal_rank,
            selected=costed is selected,
            feasible_within_budget=plan.feasible_within_budget,
            rejection_reason=plan.rejection_reason,
            trade_off_note=plan.trade_off_note,
        )


__all__ = ["STAGES", "PlanResult", "PlannerService", "ProgressFn"]
