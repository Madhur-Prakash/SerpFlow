"""Plan, run and search (sections 42, 57).

``POST /v1/search`` executes synchronously. With ``stream: true`` it returns
202 and the run id, then executes in-process while the client tails
``GET /v1/runs/{id}/stream``. Either way interactive search is NEVER routed
through Kafka - that topic exists for scheduled, bulk, retried and
webhook-triggered runs only.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import SessionDep, client_ip, rate_limit, require
from app.api.middleware import set_provenance
from app.api.v1._serializers import serialize_plan, serialize_run
from app.core.logging import get_logger
from app.core.permissions import Permission
from app.db.session import get_sessionmaker, set_tenant
from app.schemas.common import ModeInfo
from app.schemas.planning import (
    PlanRequest,
    PlanResponse,
    SearchAccepted,
    SearchRequest,
    SearchResponse,
)
from app.services import runs as run_service
from app.services.auth.service import Principal
from app.services.budgets.service import BudgetService
from app.services.stream import bus

log = get_logger("serpflow.api.search")

router = APIRouter(tags=["search"])


@router.post(
    "/plan",
    response_model=PlanResponse,
    dependencies=[Depends(rate_limit)],
)
async def create_plan(
    payload: PlanRequest,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.PLAN_CREATE))],
) -> PlanResponse:
    """Plan without executing.

    Planning calls an LLM, not SerpApi, so it consumes zero credits. That is
    why the analyst role is permitted here but not on /run or /search.
    """
    planned = await run_service.create_plan(
        session,
        principal=principal,
        intent=payload.intent,
        project_id=payload.project_id,
        budget=payload.budget,
    )
    plan = planned["plan"]
    mode = planned["mode"]
    set_provenance(
        request,
        mode=mode.label,
        budget_remaining=planned["remaining_budget"],
    )
    return serialize_plan(plan)


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    request: Request,
    background: BackgroundTasks,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.EXECUTE))],
):
    """Plan with cache-aware marginal-cost replanning, then execute."""
    await rate_limit(request, principal)

    if payload.stream:
        return await _start_streaming_search(payload, request, principal)

    result = await run_service.plan_and_execute(
        session,
        principal=principal,
        intent=payload.intent,
        project_id=payload.project_id,
        budget=payload.budget,
        execute=True,
        trigger="interactive",
        ip=client_ip(request),
    )
    return await _finalize(request, session, principal, result)


@router.post("/run", response_model=SearchResponse)
async def run(
    payload: SearchRequest,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.EXECUTE))],
):
    """Alias of /search kept for API symmetry with /plan."""
    return await search(payload, request, BackgroundTasks(), session, principal)


async def _finalize(request, session, principal: Principal, result: dict) -> SearchResponse:
    run_row = result["run"]
    plan_row = result["plan"]
    execution = result["execution"]
    mode = result["mode"]

    budgets = BudgetService(session, org_id=principal.org_id, project_id=run_row.project_id)
    remaining = await budgets.remaining_for_plan(api_key_id=principal.api_key_id)

    first_step = run_row.steps[0] if run_row.steps else None
    set_provenance(
        request,
        cache=_dominant_layer(execution.cache_summary if execution else {}),
        matched_query=first_step.matched_query if first_step else None,
        age=first_step.age_seconds if first_step else None,
        ttl_source=first_step.ttl_source if first_step else None,
        budget_remaining=remaining,
        run_id=run_row.id,
        mode=mode.label,
    )

    return SearchResponse(
        run=serialize_run(run_row, plan=plan_row, include_steps=True),
        plan=serialize_plan(plan_row),
        results=execution.results if execution else {},
        mode=ModeInfo(**mode.as_dict()),
        provenance={
            **(run_row.provenance or {}),
            "budget_remaining": remaining,
            "cache_summary": execution.cache_summary if execution else {},
        },
    )


def _dominant_layer(summary: dict) -> str:
    if not summary:
        return "miss"
    layer = max(summary.items(), key=lambda kv: kv[1])
    return layer[0] if layer[1] else "miss"


async def _start_streaming_search(
    payload: SearchRequest, request: Request, principal: Principal
) -> JSONResponse:
    """Allocate the run, return 202, execute in-process.

    The execution continues on this process's event loop - it is not handed to
    Kafka. The client attaches to the SSE stream immediately and sees the real
    stage transitions as they happen.
    """
    from app.db.models.planning import Run

    mode = await run_service.resolve_execution_mode(principal)
    maker = get_sessionmaker()
    async with maker() as setup_session:
        await set_tenant(setup_session, principal.org_id)
        project = await run_service._load_project(setup_session, principal, payload.project_id)
        run_row = Run(
            org_id=principal.org_id,
            project_id=project.id,
            principal_id=principal.id,
            principal_type=principal.type,
            api_key_id=principal.api_key_id,
            intent=payload.intent,
            status="pending",
            trigger="interactive",
            mode=mode.mode,
        )
        setup_session.add(run_row)
        await setup_session.commit()
        run_id = run_row.id
        project_id = project.id

    bus.start(run_id)
    await bus.publish(run_id, "queued", "running", {"intent": payload.intent})

    asyncio.create_task(
        _execute_detached(
            run_id=run_id,
            project_id=project_id,
            principal=principal,
            intent=payload.intent,
            budget=payload.budget,
            ip=client_ip(request),
        )
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=SearchAccepted(
            run_id=run_id,
            stream_url="/v1/runs/" + run_id + "/stream",
            mode=ModeInfo(**mode.as_dict()),
        ).model_dump(),
        headers={"X-SerpFlow-Run-Id": run_id, "X-SerpFlow-Mode": mode.label},
    )


async def _execute_detached(
    *,
    run_id: str,
    project_id: str,
    principal: Principal,
    intent: str,
    budget: int | None,
    ip: str,
) -> None:
    from app.db.models.planning import Run

    maker = get_sessionmaker()
    try:
        async with maker() as session:
            await set_tenant(session, principal.org_id)
            run_row = await session.get(Run, run_id)
            if run_row is None:
                return
            try:
                await run_service.plan_and_execute(
                    session,
                    principal=principal,
                    intent=intent,
                    project_id=project_id,
                    budget=budget,
                    execute=True,
                    trigger="interactive",
                    run=run_row,
                    ip=ip,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    except Exception as exc:
        log.error(
            "streamed search failed",
            extra={
                "event": "search.stream_failed",
                "run_id": run_id,
                "error": type(exc).__name__,
            },
        )
        code = getattr(exc, "code", type(exc).__name__)
        message = getattr(exc, "message", str(exc))
        if not bus.is_finished(run_id):
            await bus.fail(run_id, code, message[:400])
        # Persist the failure so the Run Inspector shows it.
        async with maker() as session:
            await set_tenant(session, principal.org_id)
            row = await session.get(Run, run_id)
            if row is not None and row.status not in ("succeeded", "failed"):
                row.status = "failed"
                row.error_code = code
                row.error_message = message[:1000]
                await session.commit()


__all__ = ["router"]
