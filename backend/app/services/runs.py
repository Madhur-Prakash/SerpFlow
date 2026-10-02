"""Run orchestration: plan, then execute, with one code path.

The REST API, the MCP server, the CLI and the Kafka background worker all call
into here. Section 58 is explicit that MCP must not duplicate planner or
executor logic, and this module is how that is enforced: there is exactly one
place where a plan becomes a run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, SerpFlowError
from app.core.logging import bind, get_logger
from app.core.permissions import Permission
from app.db.models.identity import Organization, Project, ServicePrincipalSession
from app.db.models.planning import Plan, Run
from app.integrations.serpapi import ResolvedMode, resolve_mode
from app.services.audit.service import AuditService
from app.services.auth.service import Principal
from app.services.budgets.service import BudgetService
from app.services.cache.service import CacheService
from app.services.catalog.loader import load_catalog
from app.services.credentials.service import CredentialService
from app.services.executor.service import ExecutionResult, ExecutorService
from app.services.planner.service import PlannerService
from app.services.stream import bus, progress_for

log = get_logger("serpflow.runs")


async def _load_project(
    session: AsyncSession, principal: Principal, project_id: str | None
) -> Project:
    target = project_id or principal.project_id
    if target:
        project = await session.get(Project, target)
        if project is None or project.org_id != principal.org_id:
            raise NotFoundError("Project not found.")
        return project
    project = await session.scalar(
        select(Project).where(Project.org_id == principal.org_id).order_by(Project.created_at)
    )
    if project is None:
        raise NotFoundError("This organization has no projects.")
    return project


async def resolve_execution_mode(principal: Principal) -> ResolvedMode:
    """Section 21 precedence, in one place so it cannot drift."""
    return resolve_mode(key_environment=principal.key_environment or "live")


def _cache_scope(org: Organization | None, project: Project) -> str:
    if project.shared_cache_enabled and org is not None and org.cache_scope == "organization":
        return "organization"
    return "project"


async def create_plan(
    session: AsyncSession,
    *,
    principal: Principal,
    intent: str,
    project_id: str | None = None,
    budget: int | None = None,
    run_id: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Plan only. Costs no SerpApi credits, which is why analysts may do it."""
    project = await _load_project(session, principal, project_id)
    org = await session.get(Organization, principal.org_id)
    mode = await resolve_execution_mode(principal)
    bind(org_id=principal.org_id, project_id=project.id, principal_id=principal.id)

    budgets = BudgetService(session, org_id=principal.org_id, project_id=project.id)
    remaining = await budgets.remaining_for_plan(
        api_key_id=principal.api_key_id, session_id=principal.session_id
    )

    cache = CacheService(
        session,
        org_id=principal.org_id,
        project_id=project.id,
        scope=_cache_scope(org, project),
        semantic_threshold=project.semantic_threshold,
    )
    planner = PlannerService(
        session,
        org_id=principal.org_id,
        project_id=project.id,
        principal_id=principal.id,
        cache=cache,
        mode=mode.mode,
        engine_allowlist=project.engine_allowlist,
        engine_denylist=project.engine_denylist,
        semantic_threshold=project.semantic_threshold,
        cache_scope=_cache_scope(org, project),
    )

    result = await planner.plan(
        intent,
        budget=budget,
        remaining_budget=remaining,
        progress=progress_for(run_id) if run_id else None,
        persist=persist,
    )
    return {
        "plan": result.plan,
        "result": result,
        "project": project,
        "mode": mode,
        "remaining_budget": remaining,
    }


async def plan_and_execute(
    session: AsyncSession,
    *,
    principal: Principal,
    intent: str,
    project_id: str | None = None,
    budget: int | None = None,
    execute: bool = True,
    trigger: str = "interactive",
    run: Run | None = None,
    ip: str = "",
    service_session: ServicePrincipalSession | None = None,
) -> dict[str, Any]:
    """The whole flow: plan with cache-aware replanning, then execute."""
    project = await _load_project(session, principal, project_id)
    org = await session.get(Organization, principal.org_id)
    mode = await resolve_execution_mode(principal)

    if run is None:
        run = Run(
            org_id=principal.org_id,
            project_id=project.id,
            principal_id=principal.id,
            principal_type=principal.type,
            api_key_id=principal.api_key_id,
            service_session_id=service_session.id if service_session else None,
            intent=intent,
            status="planning",
            trigger=trigger,
            mode=mode.mode,
        )
        session.add(run)
        await session.flush()

    bind(
        run_id=run.id,
        org_id=principal.org_id,
        project_id=project.id,
        principal_id=principal.id,
    )
    bus.start(run.id)

    try:
        planned = await create_plan(
            session,
            principal=principal,
            intent=intent,
            project_id=project.id,
            budget=budget,
            run_id=run.id,
            persist=True,
        )
    except SerpFlowError as exc:
        run.status = "failed"
        run.error_code = exc.code
        run.error_message = exc.message
        run.finished_at = datetime.now(UTC)
        await bus.fail(run.id, exc.code, exc.message)
        raise

    plan: Plan = planned["plan"]
    run.plan_id = plan.id
    run.naive_cost = plan.naive_cost
    run.marginal_cost = plan.marginal_cost
    await session.flush()

    if not execute:
        run.status = "planned"
        run.finished_at = datetime.now(UTC)
        await bus.finish(
            run.id,
            {
                "plan_id": plan.id,
                "executed": False,
                "naive_cost": plan.naive_cost,
                "marginal_cost": plan.marginal_cost,
            },
        )
        return {"run": run, "plan": plan, "execution": None, "mode": mode, "project": project}

    credentials = CredentialService(session, org_id=principal.org_id)
    credential = None
    if mode.needs_credential:
        credential = await credentials.resolve(project)

    cache = CacheService(
        session,
        org_id=principal.org_id,
        project_id=project.id,
        scope=_cache_scope(org, project),
        semantic_threshold=project.semantic_threshold,
    )
    budgets = BudgetService(session, org_id=principal.org_id, project_id=project.id)
    executor = ExecutorService(
        session,
        org_id=principal.org_id,
        project_id=project.id,
        mode=mode,
        credential=credential,
        cache=cache,
        budgets=budgets,
        engine_allowlist=project.engine_allowlist,
        engine_denylist=project.engine_denylist,
        ttl_overrides=project.ttl_overrides,
    )

    try:
        execution: ExecutionResult = await executor.execute(
            run,
            plan,
            progress=progress_for(run.id),
            api_key_id=principal.api_key_id,
            session_id=service_session.id if service_session else None,
        )
    except SerpFlowError as exc:
        await bus.fail(run.id, exc.code, exc.message)
        raise
    except Exception as exc:
        await bus.fail(run.id, "INTERNAL_ERROR", str(exc)[:300])
        raise

    # Routing savings: what the cold winner would have cost, minus what the
    # selected plan cost cold. Separate from cache savings in the waterfall.
    routing_savings = 0
    for alternative in plan.rejected_alternatives or []:
        if alternative.get("naive_rank") == 0:
            routing_savings = max(0, int(alternative.get("naive_cost", 0)) - plan.naive_cost)
            break
    if routing_savings:
        await budgets.record_routing_saving(
            credits=routing_savings,
            run_id=run.id,
            note="selected route is cheaper than the highest-confidence alternative",
        )

    if service_session is not None:
        service_session.credits_used += execution.credits_spent
        service_session.runs_count += 1

    await AuditService(session, org_id=principal.org_id).record(
        action="run.executed",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.email or principal.id,
        resource_type="run",
        resource_id=run.id,
        project_id=project.id,
        after={
            "intent": intent[:300],
            "plan_id": plan.id,
            "status": run.status,
            "credits_spent": execution.credits_spent,
            "credits_saved": execution.credits_saved,
            "mode": mode.mode,
            "marginal_replan_changed_selection": plan.marginal_replan_changed_selection,
        },
        ip=ip,
    )

    await bus.finish(
        run.id,
        {
            "run_id": run.id,
            "plan_id": plan.id,
            "status": run.status,
            "credits_spent": execution.credits_spent,
            "credits_saved": execution.credits_saved,
            "naive_cost": plan.naive_cost,
            "marginal_cost": plan.marginal_cost,
            "cache_summary": execution.cache_summary,
            "mode": mode.mode,
            "changed_selection": plan.marginal_replan_changed_selection,
            "summary": execution.results.get("summary", {}),
        },
    )

    return {
        "run": run,
        "plan": plan,
        "execution": execution,
        "mode": mode,
        "project": project,
    }


async def execute_background_run(
    session: AsyncSession, *, run_id: str, org_id: str
) -> dict[str, Any] | None:
    """Kafka path: scheduled, bulk, retried and webhook-triggered runs only."""
    from app.core.permissions import permissions_for

    run = await session.get(Run, run_id)
    if run is None or run.org_id != org_id:
        log.warning("background run not found", extra={"event": "worker.run_missing"})
        return None
    if run.status not in ("pending", "queued", "planning"):
        return None

    principal = Principal(
        id=run.principal_id or "system",
        type=run.principal_type or "service",
        org_id=org_id,
        project_id=run.project_id,
        role="developer",
        api_key_id=run.api_key_id,
        permissions=permissions_for("developer"),
    )
    return await plan_and_execute(
        session,
        principal=principal,
        intent=run.intent,
        project_id=run.project_id,
        execute=True,
        trigger=run.trigger or "background",
        run=run,
    )


async def replay_run(
    session: AsyncSession, *, principal: Principal, run_id: str, ip: str = ""
) -> dict[str, Any]:
    """Re-run the same intent, recording the lineage.

    This is the second half of the demo proof: the first run warms the cache,
    the replay re-plans against that warm state, and the selected plan can
    legitimately differ.
    """
    original = await session.get(Run, run_id)
    if original is None or original.org_id != principal.org_id:
        raise NotFoundError("Run not found.")
    if not principal.can(Permission.RUN_REPLAY):
        from app.core.exceptions import PermissionDeniedError

        raise PermissionDeniedError("This role may not replay runs.")

    mode = await resolve_execution_mode(principal)
    run = Run(
        org_id=principal.org_id,
        project_id=original.project_id,
        principal_id=principal.id,
        principal_type=principal.type,
        api_key_id=principal.api_key_id,
        intent=original.intent,
        status="planning",
        trigger="replay",
        mode=mode.mode,
        replay_of_run_id=original.id,
    )
    session.add(run)
    await session.flush()

    return await plan_and_execute(
        session,
        principal=principal,
        intent=original.intent,
        project_id=original.project_id,
        execute=True,
        trigger="replay",
        run=run,
        ip=ip,
    )


def catalog_version() -> str:
    return load_catalog().version


__all__ = [
    "catalog_version",
    "create_plan",
    "execute_background_run",
    "plan_and_execute",
    "replay_run",
    "resolve_execution_mode",
]
