"""ORM-to-schema serializers.

The Plan Inspector renders persisted values (section 15), so these functions
copy stored fields out of the row. They deliberately do not recompute the
counterfactual - if ``naive_cost`` and ``marginal_cost`` disagree with what the
planner decided, that is a bug to find, not something the UI should paper over.
"""

from __future__ import annotations

from typing import Any

from app.db.models.planning import Plan, Run
from app.schemas.planning import (
    BudgetReductionView,
    FreshnessRequirementView,
    PlanCandidateView,
    PlanResponse,
    PlanStepView,
    RejectedAlternativeView,
    RejectedEngineView,
    RunResponse,
    RunSummary,
    StageTraceEvent,
    StepResponse,
    WarmStepView,
)


def serialize_plan(plan: Plan, *, include_candidates: bool = True) -> PlanResponse:
    candidates: list[PlanCandidateView] = []
    if include_candidates:
        for candidate in sorted(plan.candidates or [], key=lambda c: c.marginal_rank):
            candidates.append(
                PlanCandidateView(
                    id=candidate.id,
                    label=candidate.label,
                    strategy=candidate.strategy,
                    engines=candidate.engines,
                    hops=candidate.hops,
                    naive_cost=candidate.naive_cost,
                    marginal_cost=candidate.marginal_cost,
                    warm_step_indices=candidate.warm_step_indices,
                    cache_state=candidate.cache_state,
                    coverage=candidate.coverage,
                    confidence=candidate.confidence,
                    naive_rank=candidate.naive_rank,
                    marginal_rank=candidate.marginal_rank,
                    selected=candidate.selected,
                    feasible_within_budget=candidate.feasible_within_budget,
                    rejection_reason=candidate.rejection_reason,
                    trade_off_note=candidate.trade_off_note,
                    steps=candidate.steps,
                )
            )

    return PlanResponse(
        id=plan.id,
        org_id=plan.org_id,
        project_id=plan.project_id,
        intent=plan.intent,
        normalized_intent=plan.normalized_intent,
        steps=[PlanStepView.model_validate(item) for item in (plan.steps or [])],
        parameter_bindings=plan.parameter_bindings,
        naive_cost=plan.naive_cost,
        marginal_cost=plan.marginal_cost,
        projected_full_scale_cost=plan.projected_full_scale_cost,
        savings=max(0, plan.naive_cost - plan.marginal_cost),
        warm_steps=[WarmStepView.model_validate(item) for item in (plan.warm_steps or [])],
        freshness_requirements=[
            FreshnessRequirementView.model_validate(item)
            for item in (plan.freshness_requirements or [])
        ],
        budget_reduction=(
            BudgetReductionView(**plan.budget_reduction) if plan.budget_reduction else None
        ),
        confidence=plan.confidence,
        catalog_version=plan.catalog_version,
        candidate_count=plan.candidate_count,
        single_candidate_reason=plan.single_candidate_reason,
        rejected_alternatives=[
            RejectedAlternativeView.model_validate(item)
            for item in (plan.rejected_alternatives or [])
        ],
        rejected_engines=[
            RejectedEngineView.model_validate(item) for item in (plan.rejected_engines or [])
        ],
        candidates=candidates,
        cold_winner_candidate_id=plan.cold_winner_candidate_id,
        marginal_replan_changed_selection=plan.marginal_replan_changed_selection,
        replan_explanation=plan.replan_explanation,
        budget_limit=plan.budget_limit,
        planner_latency_ms=plan.planner_latency_ms,
        mode=plan.mode,
        stage_trace=[StageTraceEvent.model_validate(item) for item in (plan.stage_trace or [])],
        created_at=plan.created_at,
    )


def serialize_step(step: Any, *, include_payload_ref: bool = True) -> StepResponse:
    return StepResponse(
        id=step.id,
        index=step.index,
        engine=step.engine,
        label=step.label,
        parameters=step.parameters,
        depends_on=step.depends_on,
        fan_out=step.fan_out,
        status=step.status,
        cache_layer=step.cache_layer,
        matched_query=step.matched_query,
        similarity=step.similarity,
        age_seconds=step.age_seconds,
        ttl_source=step.ttl_source,
        freshness_requirement=step.freshness_requirement,
        credits=step.credits,
        latency_ms=step.latency_ms,
        confidence=step.confidence,
        # The reference is not the payload. Reading the payload itself needs
        # payload:read, which is gated separately from run visibility.
        payload_ref=step.payload_ref if include_payload_ref else None,
        payload_bytes=step.payload_bytes,
        serpapi_search_id=step.serpapi_search_id,
        http_status=step.http_status,
        mode=step.mode,
        pii_risk=step.pii_risk,
        error_code=step.error_code,
        error_message=step.error_message,
        extracted=step.extracted,
    )


def serialize_run(
    run: Run,
    *,
    plan: Plan | None = None,
    include_steps: bool = False,
    include_payload_refs: bool = True,
) -> RunResponse:
    return RunResponse(
        id=run.id,
        project_id=run.project_id,
        plan_id=run.plan_id,
        intent=run.intent,
        status=run.status,
        trigger=run.trigger,
        credits_spent=run.credits_spent,
        credits_saved=run.credits_saved,
        naive_cost=run.naive_cost,
        marginal_cost=run.marginal_cost,
        mode=run.mode,
        duration_ms=run.duration_ms,
        error_code=run.error_code,
        created_at=run.created_at,
        principal_id=run.principal_id,
        principal_type=run.principal_type,
        cache_summary=run.cache_summary,
        provenance=run.provenance,
        result_summary=run.result_summary,
        results_ref=run.results_ref if include_payload_refs else None,
        error_message=run.error_message,
        trace_id=run.trace_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        replay_of_run_id=run.replay_of_run_id,
        expires_at=run.expires_at,
        max_pii_risk=run.max_pii_risk,
        steps=(
            [serialize_step(s, include_payload_ref=include_payload_refs) for s in run.steps]
            if include_steps
            else []
        ),
        plan=serialize_plan(plan) if plan is not None else None,
    )


def serialize_run_summary(run: Run) -> RunSummary:
    return RunSummary(
        id=run.id,
        project_id=run.project_id,
        plan_id=run.plan_id,
        intent=run.intent,
        status=run.status,
        trigger=run.trigger,
        credits_spent=run.credits_spent,
        credits_saved=run.credits_saved,
        naive_cost=run.naive_cost,
        marginal_cost=run.marginal_cost,
        mode=run.mode,
        duration_ms=run.duration_ms,
        error_code=run.error_code,
        created_at=run.created_at,
    )


__all__ = ["serialize_plan", "serialize_run", "serialize_run_summary", "serialize_step"]
