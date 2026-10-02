"""Budgets, cache dashboard, analytics, benchmarks, audit and alerts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    PaginationDep,
    ProjectDep,
    SessionDep,
    client_ip,
    require,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Permission
from app.db.models.benchmark import BenchmarkRun, BenchmarkTask, RoutingEval
from app.db.models.caching import CacheEntry, SemanticGuardRejection
from app.db.models.governance import (
    Alert,
    AuditLogEntry,
    Budget,
    NotificationChannel,
)
from app.schemas.common import OkResponse, Page
from app.schemas.governance import (
    AlertResponse,
    AlertUpdate,
    AuditEntryResponse,
    AuditVerifyResponse,
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BenchmarkTaskResponse,
    BudgetCreate,
    BudgetOverview,
    BudgetResponse,
    BudgetUpdate,
    CacheDashboardResponse,
    CacheEntryResponse,
    CacheInvalidateRequest,
    DashboardResponse,
    GuardRejectionResponse,
    NotificationChannelCreate,
    NotificationChannelResponse,
    RoutingEvalResponse,
    SavingsDecompositionResponse,
)
from app.services.analytics.service import AnalyticsService
from app.services.audit.service import AuditService
from app.services.auth.service import Principal
from app.services.benchmark.service import BenchmarkHarness
from app.services.budgets.service import BudgetService, period_bounds
from app.services.cache.redis_client import hot_stats
from app.services.cache.service import CacheService
from app.services.catalog.loader import load_catalog

router = APIRouter(tags=["governance"])


def _budget_view(budget: Budget) -> BudgetResponse:
    return BudgetResponse(
        id=budget.id,
        org_id=budget.org_id,
        scope=budget.scope,  # type: ignore[arg-type]
        scope_id=budget.scope_id,
        name=budget.name,
        limit_credits=budget.limit_credits,
        current_usage=budget.current_usage,
        remaining=budget.remaining,
        utilization=round(budget.utilization, 4),
        period=budget.period,  # type: ignore[arg-type]
        period_started_at=budget.period_started_at,
        period_ends_at=budget.period_ends_at,
        alert_at=budget.alert_at,
        on_exhausted=budget.on_exhausted,  # type: ignore[arg-type]
        enabled=budget.enabled,
        created_at=budget.created_at,
    )


# --------------------------------------------------------------------------
# budgets (sections 38, 39, 40)
# --------------------------------------------------------------------------
@router.get("/budgets", response_model=BudgetOverview)
async def list_budgets(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.BUDGET_READ))],
) -> BudgetOverview:
    rows = (
        await session.scalars(
            select(Budget).where(Budget.org_id == principal.org_id).order_by(Budget.scope)
        )
    ).all()
    service = BudgetService(session, org_id=principal.org_id, project_id=principal.project_id)
    summary = await service.summary()
    analytics = AnalyticsService(session, org_id=principal.org_id)
    return BudgetOverview(
        budgets=[_budget_view(b) for b in rows],
        credits_spent_total=summary["credits_spent_total"],
        credits_saved_total=summary["credits_saved_total"],
        projected_exhaustion=await service.projected_exhaustion(),
        # Internal ledger and upstream quota, reported side by side.
        upstream_quota=await analytics.upstream_quota(),
    )


@router.post("/budgets", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: BudgetCreate,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.BUDGET_WRITE))],
) -> BudgetResponse:
    start, end = period_bounds(payload.period)

    # (scope, scope_id, period) is unique. Without this check the insert fails
    # on the constraint and the caller gets a bare 500, which says nothing
    # about what to do; a budget already existing for this scope is an
    # ordinary, recoverable answer.
    existing = await session.scalar(
        select(Budget).where(
            Budget.org_id == principal.org_id,
            Budget.scope == payload.scope,
            Budget.scope_id == payload.scope_id,
            Budget.period == payload.period,
        )
    )
    if existing is not None:
        raise ConflictError(
            "A "
            + payload.period
            + " budget already exists for this "
            + payload.scope
            + ". Update it instead, or choose another period."
        )

    budget = Budget(
        org_id=principal.org_id,
        scope=payload.scope,
        scope_id=payload.scope_id,
        name=payload.name or (payload.scope + " budget"),
        limit_credits=payload.limit_credits,
        period=payload.period,
        period_started_at=start,
        period_ends_at=end,
        alert_at=payload.alert_at,
        on_exhausted=payload.on_exhausted,
    )
    session.add(budget)
    try:
        await session.flush()
    except IntegrityError as exc:
        # The check above loses a race with a concurrent create. Same answer.
        await session.rollback()
        raise ConflictError(
            "A " + payload.period + " budget already exists for this " + payload.scope + "."
        ) from exc

    await AuditService(session, org_id=principal.org_id).record(
        action="budget.created",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="budget",
        resource_id=budget.id,
        after=payload.model_dump(),
        ip=client_ip(request),
    )
    return _budget_view(budget)


@router.patch("/budgets/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: str,
    payload: BudgetUpdate,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.BUDGET_WRITE))],
) -> BudgetResponse:
    budget = await session.get(Budget, budget_id)
    if budget is None or budget.org_id != principal.org_id:
        raise NotFoundError("Budget not found.")
    data = payload.model_dump(exclude_unset=True)
    before = {k: getattr(budget, k) for k in data}
    for field, value in data.items():
        setattr(budget, field, value)
    await AuditService(session, org_id=principal.org_id).record(
        action="budget.updated",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="budget",
        resource_id=budget.id,
        before=before,
        after=data,
        ip=client_ip(request),
    )
    return _budget_view(budget)


@router.delete("/budgets/{budget_id}", response_model=OkResponse)
async def delete_budget(
    budget_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.BUDGET_WRITE))],
) -> OkResponse:
    budget = await session.get(Budget, budget_id)
    if budget is None or budget.org_id != principal.org_id:
        raise NotFoundError("Budget not found.")
    await session.delete(budget)
    return OkResponse(message="Budget deleted.")


# --------------------------------------------------------------------------
# cache (section 50)
# --------------------------------------------------------------------------
@router.get("/cache", response_model=CacheDashboardResponse)
async def cache_dashboard(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CACHE_READ))],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> CacheDashboardResponse:
    analytics = AnalyticsService(session, org_id=principal.org_id)
    data = await analytics.cache_dashboard(days=days)
    return CacheDashboardResponse(**data, redis=await hot_stats())


@router.get("/cache/entries", response_model=Page[CacheEntryResponse])
async def list_cache_entries(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CACHE_READ))],
    pagination: PaginationDep,
    engine: Annotated[str | None, Query()] = None,
    project_id: Annotated[str | None, Query()] = None,
) -> Page[CacheEntryResponse]:
    limit, offset = pagination
    query = select(CacheEntry).where(CacheEntry.org_id == principal.org_id)
    count_query = select(func.count(CacheEntry.id)).where(CacheEntry.org_id == principal.org_id)
    if engine:
        query = query.where(CacheEntry.engine == engine)
        count_query = count_query.where(CacheEntry.engine == engine)
    if project_id:
        query = query.where(CacheEntry.project_id == project_id)
        count_query = count_query.where(CacheEntry.project_id == project_id)
    total = int(await session.scalar(count_query) or 0)
    rows = (
        await session.scalars(
            query.order_by(CacheEntry.created_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return Page(
        items=[CacheEntryResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/cache/guard-rejections", response_model=Page[GuardRejectionResponse])
async def list_guard_rejections(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CACHE_READ))],
    pagination: PaginationDep,
) -> Page[GuardRejectionResponse]:
    """Every near-match the entity/numeral guard rejected.

    Logged so the similarity threshold can be tuned with evidence rather than
    intuition (section 17).
    """
    limit, offset = pagination
    total = int(
        await session.scalar(
            select(func.count(SemanticGuardRejection.id)).where(
                SemanticGuardRejection.org_id == principal.org_id
            )
        )
        or 0
    )
    rows = (
        await session.scalars(
            select(SemanticGuardRejection)
            .where(SemanticGuardRejection.org_id == principal.org_id)
            .order_by(SemanticGuardRejection.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page(
        items=[GuardRejectionResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/cache/invalidate", response_model=OkResponse)
async def invalidate_cache(
    payload: CacheInvalidateRequest,
    request: Request,
    session: SessionDep,
    project: ProjectDep,
    principal: Annotated[Principal, Depends(require(Permission.CACHE_INVALIDATE))],
) -> OkResponse:
    cache = CacheService(session, org_id=principal.org_id, project_id=project.id)
    removed = await cache.invalidate(engine=payload.engine, entry_id=payload.entry_id)
    await AuditService(session, org_id=principal.org_id).record(
        action="cache.invalidated",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="cache",
        resource_id=payload.entry_id or payload.engine or "all",
        project_id=project.id,
        after={"entries_invalidated": removed},
        ip=client_ip(request),
    )
    return OkResponse(message=str(removed) + " cache entries invalidated.")


# --------------------------------------------------------------------------
# analytics (section 52)
# --------------------------------------------------------------------------
@router.get("/analytics/dashboard", response_model=DashboardResponse)
async def dashboard(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ANALYTICS_READ))],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> DashboardResponse:
    analytics = AnalyticsService(session, org_id=principal.org_id)
    data = await analytics.dashboard(days=days)
    budgets = BudgetService(session, org_id=principal.org_id, project_id=principal.project_id)
    data["projected_exhaustion"] = await budgets.projected_exhaustion()
    return DashboardResponse(**data)


@router.get("/analytics/savings", response_model=SavingsDecompositionResponse)
async def savings(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ANALYTICS_READ))],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> SavingsDecompositionResponse:
    analytics = AnalyticsService(session, org_id=principal.org_id)
    return SavingsDecompositionResponse(**await analytics.savings_decomposition(days=days))


@router.get("/analytics/attribution")
async def attribution(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ANALYTICS_READ))],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict:
    return await AnalyticsService(session, org_id=principal.org_id).cost_attribution(days=days)


@router.get("/analytics/routing")
async def routing_quality(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ANALYTICS_READ))],
) -> dict:
    return await AnalyticsService(session, org_id=principal.org_id).routing_quality()


@router.get("/analytics/volatility")
async def volatility(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ANALYTICS_READ))],
    days: Annotated[int, Query(ge=1, le=365)] = 90,
) -> dict:
    return await AnalyticsService(session, org_id=principal.org_id).volatility(days=days)


@router.get("/analytics/engine-reach")
async def engine_reach(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ANALYTICS_READ))],
) -> dict:
    index = load_catalog()
    return await AnalyticsService(session, org_id=principal.org_id).engine_reach(
        catalog_engine_count=len(index.engines)
    )


@router.get("/analytics/cross-project")
async def cross_project(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ANALYTICS_READ))],
) -> dict:
    """Cross-project cache benefit (section 37).

    SPEND is attributed to the fetching project, SAVINGS to the beneficiary.
    """
    return await AnalyticsService(session, org_id=principal.org_id).cross_project_benefit()


# --------------------------------------------------------------------------
# benchmarks (section 53)
# --------------------------------------------------------------------------
@router.get("/benchmarks", response_model=list[BenchmarkRunResponse])
async def list_benchmarks(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.BENCHMARK_READ))],
    catalog_version: Annotated[str | None, Query()] = None,
) -> list[BenchmarkRunResponse]:
    query = select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).limit(50)
    if catalog_version:
        query = query.where(BenchmarkRun.catalog_version == catalog_version)
    rows = (await session.scalars(query)).all()
    return [BenchmarkRunResponse.model_validate(r) for r in rows]


@router.get("/benchmarks/tasks", response_model=Page[BenchmarkTaskResponse])
async def list_benchmark_tasks(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.BENCHMARK_READ))],
    pagination: PaginationDep,
    category: Annotated[str | None, Query()] = None,
) -> Page[BenchmarkTaskResponse]:
    limit, offset = pagination
    query = select(BenchmarkTask)
    count_query = select(func.count(BenchmarkTask.id))
    if category:
        query = query.where(BenchmarkTask.category == category)
        count_query = count_query.where(BenchmarkTask.category == category)
    total = int(await session.scalar(count_query) or 0)
    rows = (
        await session.scalars(
            query.order_by(BenchmarkTask.task_key.asc()).limit(limit).offset(offset)
        )
    ).all()
    return Page(
        items=[BenchmarkTaskResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/benchmarks/{run_id}/evals", response_model=list[RoutingEvalResponse])
async def list_evals(
    run_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.BENCHMARK_READ))],
) -> list[RoutingEvalResponse]:
    rows = (
        await session.scalars(
            select(RoutingEval)
            .where(RoutingEval.benchmark_run_id == run_id)
            .order_by(RoutingEval.task_key.asc())
        )
    ).all()
    return [RoutingEvalResponse.model_validate(r) for r in rows]


@router.post("/benchmarks/run", response_model=BenchmarkRunResponse)
async def run_benchmark(
    payload: BenchmarkRunRequest,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.BENCHMARK_RUN))],
) -> BenchmarkRunResponse:
    """Run the suite on demand.

    This makes real LLM calls, which is why it is on demand and not in CI.
    """
    harness = BenchmarkHarness(session)
    report = await harness.run(
        system=payload.system,
        suite_version=payload.suite_version,
        limit=payload.limit,
        persist=True,
        org_id=principal.org_id,
    )
    row = await session.get(BenchmarkRun, report["benchmark_run_id"])
    if row is None:
        raise NotFoundError("Benchmark run was not persisted.")
    return BenchmarkRunResponse.model_validate(row)


# --------------------------------------------------------------------------
# audit (section 54)
# --------------------------------------------------------------------------
@router.get("/audit", response_model=Page[AuditEntryResponse])
async def list_audit(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.AUDIT_READ))],
    pagination: PaginationDep,
    action: Annotated[str | None, Query()] = None,
    actor_id: Annotated[str | None, Query()] = None,
) -> Page[AuditEntryResponse]:
    limit, offset = pagination
    query = select(AuditLogEntry).where(AuditLogEntry.org_id == principal.org_id)
    count_query = select(func.count(AuditLogEntry.id)).where(
        AuditLogEntry.org_id == principal.org_id
    )
    if action:
        query = query.where(AuditLogEntry.action == action)
        count_query = count_query.where(AuditLogEntry.action == action)
    if actor_id:
        query = query.where(AuditLogEntry.actor_id == actor_id)
        count_query = count_query.where(AuditLogEntry.actor_id == actor_id)
    total = int(await session.scalar(count_query) or 0)
    rows = (
        await session.scalars(
            query.order_by(AuditLogEntry.sequence.desc()).limit(limit).offset(offset)
        )
    ).all()
    return Page(
        items=[AuditEntryResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/audit/verify", response_model=AuditVerifyResponse)
async def verify_audit(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.AUDIT_READ))],
) -> AuditVerifyResponse:
    """Walk the hash chain and report the first break, if any."""
    result = await AuditService(session, org_id=principal.org_id).verify_chain()
    return AuditVerifyResponse(**result)


@router.get("/audit/export")
async def export_audit(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.AUDIT_EXPORT))],
    limit: Annotated[int, Query(ge=1, le=50000)] = 10000,
) -> dict:
    rows = await AuditService(session, org_id=principal.org_id).export(limit=limit)
    return {"org_id": principal.org_id, "count": len(rows), "entries": rows}


# --------------------------------------------------------------------------
# alerts and channels (sections 61, 66)
# --------------------------------------------------------------------------
@router.get("/alerts", response_model=Page[AlertResponse])
async def list_alerts(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ALERT_READ))],
    pagination: PaginationDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> Page[AlertResponse]:
    limit, offset = pagination
    query = select(Alert).where(Alert.org_id == principal.org_id)
    count_query = select(func.count(Alert.id)).where(Alert.org_id == principal.org_id)
    if status_filter:
        query = query.where(Alert.status == status_filter)
        count_query = count_query.where(Alert.status == status_filter)
    total = int(await session.scalar(count_query) or 0)
    rows = (
        await session.scalars(query.order_by(Alert.created_at.desc()).limit(limit).offset(offset))
    ).all()
    return Page(
        items=[AlertResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/alerts/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: str,
    payload: AlertUpdate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ALERT_WRITE))],
) -> AlertResponse:
    alert = await session.get(Alert, alert_id)
    if alert is None or alert.org_id != principal.org_id:
        raise NotFoundError("Alert not found.")
    alert.status = payload.status
    now = datetime.now(UTC)
    if payload.status == "acknowledged":
        alert.acknowledged_by = principal.id
        alert.acknowledged_at = now
    elif payload.status == "resolved":
        alert.resolved_at = now
    return AlertResponse.model_validate(alert)


@router.get("/notification-channels", response_model=list[NotificationChannelResponse])
async def list_channels(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ALERT_READ))],
) -> list[NotificationChannelResponse]:
    rows = (
        await session.scalars(
            select(NotificationChannel).where(NotificationChannel.org_id == principal.org_id)
        )
    ).all()
    return [NotificationChannelResponse.model_validate(r) for r in rows]


@router.post(
    "/notification-channels",
    response_model=NotificationChannelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    payload: NotificationChannelCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ALERT_WRITE))],
) -> NotificationChannelResponse:
    from app.core.security import hash_opaque_token

    channel = NotificationChannel(
        org_id=principal.org_id,
        project_id=principal.project_id,
        name=payload.name,
        kind=payload.kind,
        target=payload.target,
        events=payload.events,
        # Only the hash is stored; it is also the HMAC signing key for deliveries.
        secret_hash=hash_opaque_token(payload.secret) if payload.secret else None,
    )
    session.add(channel)
    await session.flush()
    return NotificationChannelResponse.model_validate(channel)


@router.delete("/notification-channels/{channel_id}", response_model=OkResponse)
async def delete_channel(
    channel_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ALERT_WRITE))],
) -> OkResponse:
    channel = await session.get(NotificationChannel, channel_id)
    if channel is None or channel.org_id != principal.org_id:
        raise NotFoundError("Channel not found.")
    await session.delete(channel)
    return OkResponse(message="Channel deleted.")


__all__ = ["router"]
