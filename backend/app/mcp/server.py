"""MCP server (section 58).

Three tools, implemented on the same service layer the REST API uses::

    search(intent, budget?)
    plan(intent)
    explain(run_id)

No planner or executor logic is duplicated here - every call goes through
``app.services.runs``, which is the single place a plan becomes a run.

Every call resolves a full principal: service principal, session, project,
budget and permissions (section 35). An agent is not modelled as a human user
holding a shared key, and the session cap is enforced on machine-originated
requests the same way a project budget is.

    serpflow-mcp                      stdio transport
    SERPFLOW_API_KEY=sf_test_... serpflow-mcp
"""

from __future__ import annotations

import os
from typing import Any

# mcp 2.x renamed FastMCP to MCPServer. The decorator and run() APIs are
# unchanged, so one import shim covers both and the entry point keeps working
# whichever major version is resolved.
try:
    from mcp.server.mcpserver import MCPServer as _MCPServer
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer  # type: ignore[attr-defined,no-redef]

from app.core.exceptions import SerpFlowError
from app.core.logging import get_logger, setup_logging
from app.db.session import session_scope, set_tenant
from app.services.auth.service import AuthService, Principal
from app.services.budgets.service import BudgetService

log = get_logger("serpflow.mcp")

mcp = _MCPServer(
    "serpflow",
    instructions=(
        "SerpFlow routes a natural-language search intent to the right SerpApi "
        "engine or engine chain, re-plans around what is already cached, and "
        "executes only the searches that are actually required.\n\n"
        "Call plan() first when you want to see what a search would cost without "
        "spending anything - planning calls a language model, not SerpApi, so it "
        "consumes zero credits. Call search() to execute. Call explain() on a run "
        "id to see which plans were considered and why the selected one won."
    ),
)


async def _resolve_principal(session) -> tuple[Principal, Any]:
    """Resolve the service principal and open its session (section 35)."""
    api_key = os.environ.get("SERPFLOW_API_KEY")
    if not api_key:
        raise SerpFlowError(
            "SERPFLOW_API_KEY is not set. A test key routes to the deterministic "
            "mock and consumes zero SerpApi credits.",
            code="UNAUTHENTICATED",
            status_code=401,
        )
    auth = AuthService(session)
    principal = await auth.resolve_api_key(api_key)
    await set_tenant(session, principal.org_id)

    service_session = None
    if principal.type == "service" or principal.session_cap:
        service_session = await auth.open_service_session(
            principal, external_ref=os.environ.get("SERPFLOW_MCP_SESSION")
        )
        principal.session_id = service_session.id
    return principal, service_session


def _plan_view(plan: Any) -> dict[str, Any]:
    return {
        "plan_id": plan.id,
        "intent": plan.intent,
        "steps": [
            {
                "index": s["index"],
                "engine": s["engine"],
                "fan_out": s.get("fan_out", 1),
                "freshness_requirement": s.get("freshness_requirement"),
                "warm": s.get("warm", False),
            }
            for s in plan.steps
        ],
        "naive_cost": plan.naive_cost,
        "marginal_cost": plan.marginal_cost,
        "savings": max(0, plan.naive_cost - plan.marginal_cost),
        "projected_full_scale_cost": plan.projected_full_scale_cost,
        "warm_steps": plan.warm_steps,
        "candidate_count": plan.candidate_count,
        "single_candidate_reason": plan.single_candidate_reason,
        "confidence": plan.confidence,
        "catalog_version": plan.catalog_version,
        "marginal_replan_changed_selection": plan.marginal_replan_changed_selection,
        "replan_explanation": plan.replan_explanation,
        "budget_reduction": plan.budget_reduction,
        "rejected_alternatives": plan.rejected_alternatives,
    }


@mcp.tool()
async def plan(intent: str, budget: int | None = None) -> dict[str, Any]:
    """Plan a search without executing it.

    Returns the selected plan, every candidate that was considered, the cold
    and marginal costs, and which steps are already warm. Consumes zero SerpApi
    credits: planning calls a language model, not SerpApi.
    """
    from app.services import runs as run_service

    async with session_scope() as session:
        principal, _ = await _resolve_principal(session)
        result = await run_service.create_plan(
            session, principal=principal, intent=intent, budget=budget, persist=True
        )
        view = _plan_view(result["plan"])
        view["mode"] = result["mode"].as_dict()
        view["remaining_budget"] = result["remaining_budget"]
        return view


@mcp.tool()
async def search(intent: str, budget: int | None = None) -> dict[str, Any]:
    """Plan with cache-aware replanning, then execute the required searches.

    Only the steps that are not already satisfiable from cache are executed, so
    the credits spent are the marginal cost rather than the cold cost.
    """
    from app.services import runs as run_service

    async with session_scope() as session:
        principal, service_session = await _resolve_principal(session)
        result = await run_service.plan_and_execute(
            session,
            principal=principal,
            intent=intent,
            budget=budget,
            execute=True,
            trigger="mcp",
            service_session=service_session,
        )
        run = result["run"]
        execution = result["execution"]
        budgets = BudgetService(session, org_id=principal.org_id, project_id=run.project_id)
        return {
            "run_id": run.id,
            "status": run.status,
            "mode": result["mode"].as_dict(),
            "plan": _plan_view(result["plan"]),
            "credits_spent": run.credits_spent,
            "credits_saved": run.credits_saved,
            "cache_summary": run.cache_summary,
            "remaining_budget": await budgets.remaining_for_plan(
                api_key_id=principal.api_key_id, session_id=principal.session_id
            ),
            "session": (
                {
                    "session_id": service_session.id,
                    "credits_used": service_session.credits_used,
                    "session_cap": service_session.session_cap,
                }
                if service_session
                else None
            ),
            "results": (execution.results.get("summary") if execution else {}),
        }


@mcp.tool()
async def explain(run_id: str) -> dict[str, Any]:
    """Explain a run: which plans were considered, and why one won.

    This is the Plan Inspector as structured data - the stored counterfactual,
    not a recomputation.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.db.models.planning import Plan, Run

    async with session_scope() as session:
        principal, _ = await _resolve_principal(session)
        run = await session.scalar(
            select(Run).options(selectinload(Run.steps)).where(Run.id == run_id)
        )
        if run is None or run.org_id != principal.org_id:
            raise SerpFlowError("Run not found.", code="NOT_FOUND", status_code=404)

        plan_row = None
        if run.plan_id:
            plan_row = await session.scalar(
                select(Plan).options(selectinload(Plan.candidates)).where(Plan.id == run.plan_id)
            )

        return {
            "run_id": run.id,
            "intent": run.intent,
            "status": run.status,
            "mode": run.mode,
            "credits_spent": run.credits_spent,
            "credits_saved": run.credits_saved,
            "cache_summary": run.cache_summary,
            "provenance": run.provenance,
            "steps": [
                {
                    "index": s.index,
                    "engine": s.engine,
                    "cache_layer": s.cache_layer,
                    "credits": s.credits,
                    "latency_ms": round(s.latency_ms, 1),
                    "freshness_requirement": s.freshness_requirement,
                    "matched_query": s.matched_query,
                    "similarity": s.similarity,
                    "age_seconds": s.age_seconds,
                    "ttl_source": s.ttl_source,
                }
                for s in run.steps
            ],
            "plan": _plan_view(plan_row) if plan_row else None,
            "candidates": (
                [
                    {
                        "label": c.label,
                        "engines": c.engines,
                        "strategy": c.strategy,
                        "coverage": c.coverage,
                        "naive_cost": c.naive_cost,
                        "marginal_cost": c.marginal_cost,
                        "naive_rank": c.naive_rank,
                        "marginal_rank": c.marginal_rank,
                        "selected": c.selected,
                        "rejection_reason": c.rejection_reason,
                        "trade_off_note": c.trade_off_note,
                    }
                    for c in sorted(plan_row.candidates, key=lambda x: x.marginal_rank)
                ]
                if plan_row
                else []
            ),
        }


@mcp.tool()
async def catalog(engine: str | None = None) -> dict[str, Any]:
    """Inspect the engine catalog.

    With no argument, lists every engine. With one, returns that engine's
    schema, dependency edges and substitutes.
    """
    from app.services.catalog.loader import load_catalog

    index = load_catalog()
    if engine is None:
        return {
            "catalog_version": index.version,
            "engines": [
                {
                    "engine": name,
                    "purpose": index.get(name).purpose,
                    "capability_tags": index.get(name).capability_tags,
                    "cost": index.get(name).cost,
                }
                for name in index.names()
            ],
            **index.stats(),
        }
    if not index.has(engine):
        raise SerpFlowError(
            "Engine " + engine + " is not in catalog " + index.version + ".",
            code="NOT_FOUND",
            status_code=404,
        )
    spec = index.get(engine)
    return {
        "catalog_version": index.version,
        "engine": spec.engine,
        "purpose": spec.purpose,
        "capability_tags": spec.capability_tags,
        "requires": {k: v.model_dump() for k, v in spec.requires.items()},
        "optional": spec.optional,
        "produces": {k: v.model_dump() for k, v in spec.produces.items()},
        "cost": spec.cost,
        "latency_class": spec.latency_class,
        "volatility_prior": spec.volatility_prior,
        "pii_risk": spec.pii_risk,
        "substitutes": [
            {"engine": s.substitute_engine, "coverage": s.coverage, "note": s.note}
            for s in index.substitutes_for(engine)
        ],
        "depends_on": index.dependencies_of(engine),
        "feeds": index.dependents_of(engine),
    }


def main() -> None:
    setup_logging()
    log.info("serpflow mcp server starting", extra={"event": "mcp.startup"})
    mcp.run()


if __name__ == "__main__":
    main()
