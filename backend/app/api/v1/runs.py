"""Runs, the Run Inspector, replay, SSE streaming and false-hit reports."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.api.deps import PaginationDep, SessionDep, client_ip, require
from app.api.v1._serializers import serialize_plan, serialize_run, serialize_run_summary
from app.core import metrics
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.db.models.caching import CacheEntry, FalseHitReport
from app.db.models.planning import Plan, Run, Step
from app.schemas.common import OkResponse, Page
from app.schemas.planning import (
    FalseHitReportRequest,
    PayloadResponse,
    PlanResponse,
    RunResponse,
    RunSummary,
    SearchResponse,
)
from app.services import runs as run_service
from app.services.audit.service import AuditService
from app.services.auth.service import Principal
from app.services.stream import bus

router = APIRouter(tags=["runs"])


# --------------------------------------------------------------------------
# listing and detail
# --------------------------------------------------------------------------
@router.get("/runs", response_model=Page[RunSummary])
async def list_runs(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.RUN_READ))],
    pagination: PaginationDep,
    project_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    engine: Annotated[str | None, Query()] = None,
    changed_selection: Annotated[bool | None, Query()] = None,
) -> Page[RunSummary]:
    limit, offset = pagination
    query = select(Run).where(Run.org_id == principal.org_id)
    count_query = select(func.count(Run.id)).where(Run.org_id == principal.org_id)

    if project_id:
        query = query.where(Run.project_id == project_id)
        count_query = count_query.where(Run.project_id == project_id)
    if status_filter:
        query = query.where(Run.status == status_filter)
        count_query = count_query.where(Run.status == status_filter)
    if engine:
        sub = select(Step.run_id).where(Step.engine == engine)
        query = query.where(Run.id.in_(sub))
        count_query = count_query.where(Run.id.in_(sub))
    if changed_selection is not None:
        sub = select(Plan.id).where(Plan.marginal_replan_changed_selection.is_(changed_selection))
        query = query.where(Run.plan_id.in_(sub))
        count_query = count_query.where(Run.plan_id.in_(sub))

    total = int(await session.scalar(count_query) or 0)
    rows = (
        await session.scalars(query.order_by(Run.created_at.desc()).limit(limit).offset(offset))
    ).all()
    return Page(
        items=[serialize_run_summary(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.RUN_READ))],
) -> RunResponse:
    """The Run Inspector payload: plan, candidates, steps, provenance, mode."""
    run = await session.scalar(select(Run).options(selectinload(Run.steps)).where(Run.id == run_id))
    if run is None or run.org_id != principal.org_id:
        raise NotFoundError("Run not found.")

    plan = None
    if run.plan_id:
        plan = await session.scalar(
            select(Plan).options(selectinload(Plan.candidates)).where(Plan.id == run.plan_id)
        )

    # Payload references are gated separately from run visibility (section 47).
    can_see_payloads = principal.can(Permission.PAYLOAD_READ)
    return serialize_run(run, plan=plan, include_steps=True, include_payload_refs=can_see_payloads)


@router.get("/runs/{run_id}/plan", response_model=PlanResponse)
async def get_run_plan(
    run_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.RUN_READ))],
) -> PlanResponse:
    run = await session.get(Run, run_id)
    if run is None or run.org_id != principal.org_id or not run.plan_id:
        raise NotFoundError("Run or plan not found.")
    plan = await session.scalar(
        select(Plan).options(selectinload(Plan.candidates)).where(Plan.id == run.plan_id)
    )
    if plan is None:
        raise NotFoundError("Plan not found.")
    return serialize_plan(plan)


@router.get("/runs/{run_id}/steps/{step_id}/payload", response_model=PayloadResponse)
async def get_step_payload(
    run_id: str,
    step_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.PAYLOAD_READ))],
) -> PayloadResponse:
    """Raw SERP payload, behind its own permission.

    Cached SERPs are not anonymous infrastructure data - a
    google_maps_contributor_reviews payload is one named person's complete
    review history (section 55).
    """
    from app.integrations.storage import get_object_store

    step = await session.get(Step, step_id)
    if step is None or step.run_id != run_id or step.org_id != principal.org_id:
        raise NotFoundError("Step not found.")
    if not step.payload_ref:
        raise NotFoundError("This step has no stored payload.")

    payload = await get_object_store().get_json(step.payload_ref)
    if payload is None:
        raise NotFoundError("The payload is no longer in object storage.")

    return PayloadResponse(
        step_id=step.id,
        engine=step.engine,
        payload_ref=step.payload_ref,
        payload=payload,
        pii_risk=step.pii_risk,
        mode=step.mode,
    )


# --------------------------------------------------------------------------
# SSE (sections 42, 69)
# --------------------------------------------------------------------------
@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: str,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.RUN_READ))],
):
    """Real backend stage transitions.

    Every frame here was published by the planner or the executor as a stage
    actually completed. The UI pipeline animation is driven from this stream,
    never from a frontend timer.
    """
    run = await session.get(Run, run_id)
    if run is None or run.org_id != principal.org_id:
        raise NotFoundError("Run not found.")

    last_event_id = 0
    header = request.headers.get("last-event-id")
    if header and header.isdigit():
        last_event_id = int(header)

    async def generator():
        async for event in bus.subscribe(run_id, last_event_id=last_event_id):
            if await request.is_disconnected():
                break
            yield event.to_sse()

    return EventSourceResponse(generator(), ping=15)


# --------------------------------------------------------------------------
# replay and false-hit reporting
# --------------------------------------------------------------------------
@router.post("/runs/{run_id}/replay", response_model=SearchResponse)
async def replay(
    run_id: str,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.RUN_REPLAY))],
) -> SearchResponse:
    """Re-run the same intent against current cache state.

    This is the second half of the demo proof: the first run warms the cache,
    this one re-plans against that warm state, and the selected plan can
    legitimately differ.
    """
    from app.api.v1.search import _finalize

    result = await run_service.replay_run(
        session, principal=principal, run_id=run_id, ip=client_ip(request)
    )
    return await _finalize(request, session, principal, result)


@router.post("/runs/{run_id}/report-false-hit", response_model=OkResponse)
async def report_false_hit(
    run_id: str,
    payload: FalseHitReportRequest,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.RUN_READ))],
) -> OkResponse:
    """File a bad semantic hit from the Run Inspector (section 47).

    This is the real producer behind
    ``serpflow_semantic_false_hit_reports_total``.
    """
    run = await session.get(Run, run_id)
    if run is None or run.org_id != principal.org_id:
        raise NotFoundError("Run not found.")

    step = None
    if payload.step_id:
        step = await session.get(Step, payload.step_id)
        if step is None or step.run_id != run_id:
            raise NotFoundError("Step not found.")
    else:
        step = next(
            (s for s in run.steps if s.cache_layer == "semantic"),
            run.steps[0] if run.steps else None,
        )

    cache_entry_id = None
    invalidated = False
    if step is not None and step.matched_query:
        entry = await session.scalar(
            select(CacheEntry).where(
                CacheEntry.org_id == principal.org_id,
                CacheEntry.engine == step.engine,
                CacheEntry.query_text == step.matched_query,
                CacheEntry.invalidated_at.is_(None),
            )
        )
        if entry is not None:
            cache_entry_id = entry.id
            if payload.invalidate_entry:
                from datetime import UTC, datetime

                entry.invalidated_at = datetime.now(UTC)
                invalidated = True

    report = FalseHitReport(
        org_id=principal.org_id,
        project_id=run.project_id,
        run_id=run.id,
        step_id=step.id if step else None,
        cache_entry_id=cache_entry_id,
        engine=step.engine if step else "",
        reported_by=principal.id,
        similarity=step.similarity if step else None,
        requested_query=(step.parameters or {}).get("q", "") if step else "",
        matched_query=step.matched_query or "" if step else "",
        note=payload.note,
        invalidated_entry=invalidated,
    )
    session.add(report)

    metrics.semantic_false_hit_reports_total.labels(
        project_id=metrics.safe_label(run.project_id),
        engine=metrics.safe_label(step.engine if step else "unknown"),
    ).inc()

    await AuditService(session, org_id=principal.org_id).record(
        action="cache.false_hit_reported",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="run",
        resource_id=run.id,
        project_id=run.project_id,
        after={
            "engine": step.engine if step else None,
            "similarity": step.similarity if step else None,
            "invalidated_entry": invalidated,
        },
        ip=client_ip(request),
    )

    return OkResponse(
        message=(
            "Report filed. The cache entry was invalidated." if invalidated else "Report filed."
        )
    )


__all__ = ["router"]
