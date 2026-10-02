"""Budget ledger and enforcement (sections 38, 39, 40).

Budgets exist at four scopes - organization, project, api_key, session - and
the tightest one wins. Section 39 is the rule that keeps the error messages
useful::

    BUDGET_EXHAUSTED         the user-configured SerpFlow cap is gone.
                             Fix: raise the configured budget.
    UPSTREAM_QUOTA_EXHAUSTED the SerpApi account itself is dry.
                             Fix: add upstream capacity.

These are never conflated. They have different causes and different fixes, and
a dashboard that merges them sends people to the wrong place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.governance import Budget, BudgetLedgerEntry

log = get_logger("serpflow.budgets")

SCOPES = ("session", "api_key", "project", "organization")
EXHAUSTION_MODES = ("stale", "error", "queue")


@dataclass(slots=True)
class BudgetVerdict:
    allowed: bool
    message: str = ""
    binding_scope: str | None = None
    binding_budget_id: str | None = None
    remaining: int | None = None
    limit: int | None = None
    on_exhausted: str = "error"
    checked: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "binding_scope": self.binding_scope,
            "binding_budget_id": self.binding_budget_id,
            "remaining": self.remaining,
            "limit": self.limit,
            "on_exhausted": self.on_exhausted,
            "checked": self.checked,
        }


def period_bounds(period: str, *, now: datetime | None = None) -> tuple[datetime, datetime | None]:
    current = now or datetime.now(UTC)
    if period == "daily":
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period == "weekly":
        start = (current - timedelta(days=current.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start, start + timedelta(days=7)
    if period == "monthly":
        start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    return datetime(1970, 1, 1, tzinfo=UTC), None


class BudgetService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        org_id: str,
        project_id: str | None = None,
    ) -> None:
        self.session = session
        self.org_id = org_id
        self.project_id = project_id

    # ------------------------------------------------------------ discovery
    async def applicable(
        self, *, api_key_id: str | None = None, session_id: str | None = None
    ) -> list[Budget]:
        scope_ids: list[tuple[str, str]] = [("organization", self.org_id)]
        if self.project_id:
            scope_ids.append(("project", self.project_id))
        if api_key_id:
            scope_ids.append(("api_key", api_key_id))
        if session_id:
            scope_ids.append(("session", session_id))

        rows = (
            await self.session.scalars(
                select(Budget).where(
                    Budget.org_id == self.org_id,
                    Budget.enabled.is_(True),
                )
            )
        ).all()
        wanted = {(s, i) for s, i in scope_ids}
        return [b for b in rows if (b.scope, b.scope_id) in wanted]

    # ------------------------------------------------------------ enforcement
    async def check(
        self,
        credits: int,
        *,
        api_key_id: str | None = None,
        session_id: str | None = None,
    ) -> BudgetVerdict:
        """Can this spend proceed? The tightest applicable budget decides."""
        budgets = await self.applicable(api_key_id=api_key_id, session_id=session_id)
        if not budgets:
            return BudgetVerdict(allowed=True, message="No budget configured for this scope.")

        checked: list[dict[str, Any]] = []
        blocking: Budget | None = None

        for budget in sorted(budgets, key=lambda b: SCOPES.index(b.scope)):
            await self._roll_period(budget)
            remaining = budget.remaining
            checked.append(
                {
                    "scope": budget.scope,
                    "budget_id": budget.id,
                    "limit": budget.limit_credits,
                    "usage": budget.current_usage,
                    "remaining": remaining,
                    "period": budget.period,
                    "on_exhausted": budget.on_exhausted,
                }
            )
            metrics.budget_utilization_ratio.labels(
                scope=budget.scope,
                budget_id=metrics.safe_label(budget.id),
                project_id=metrics.safe_label(self.project_id),
            ).set(budget.utilization)
            if remaining < credits and blocking is None:
                blocking = budget

        if blocking is None:
            return BudgetVerdict(allowed=True, checked=checked)

        return BudgetVerdict(
            allowed=False,
            message=(
                "The "
                + blocking.scope
                + " budget is exhausted: "
                + str(blocking.current_usage)
                + " of "
                + str(blocking.limit_credits)
                + " credits used this "
                + blocking.period
                + " period. Raise the configured SerpFlow budget to continue. "
                + "This is a SerpFlow cap, not the upstream SerpApi account quota."
            ),
            binding_scope=blocking.scope,
            binding_budget_id=blocking.id,
            remaining=blocking.remaining,
            limit=blocking.limit_credits,
            on_exhausted=blocking.on_exhausted,
            checked=checked,
        )

    async def remaining_for_plan(
        self, *, api_key_id: str | None = None, session_id: str | None = None
    ) -> int | None:
        """Tightest remaining allowance, fed to budget-aware replanning."""
        budgets = await self.applicable(api_key_id=api_key_id, session_id=session_id)
        if not budgets:
            return None
        for budget in budgets:
            await self._roll_period(budget)
        return min(b.remaining for b in budgets)

    async def _roll_period(self, budget: Budget) -> None:
        """Reset usage when the budget period has rolled over."""
        if budget.period == "total":
            return
        start, end = period_bounds(budget.period)
        if budget.period_started_at is None or budget.period_started_at < start:
            budget.period_started_at = start
            budget.period_ends_at = end
            budget.current_usage = 0
            budget.alert_fired_at = None
            budget.exhausted_alert_fired_at = None

    # --------------------------------------------------------------- ledger
    async def record_spend(
        self,
        *,
        engine: str,
        credits: int,
        run_id: str | None = None,
        step_id: str | None = None,
        api_key_id: str | None = None,
        session_id: str | None = None,
        principal_id: str | None = None,
    ) -> None:
        """Attribute real upstream spend to the project that fetched."""
        self.session.add(
            BudgetLedgerEntry(
                org_id=self.org_id,
                project_id=self.project_id or self.org_id,
                run_id=run_id,
                step_id=step_id,
                api_key_id=api_key_id,
                session_id=session_id,
                principal_id=principal_id,
                kind="spend",
                source="live",
                engine=engine,
                credits=credits,
                note="live upstream call",
            )
        )
        for budget in await self.applicable(api_key_id=api_key_id, session_id=session_id):
            await self._roll_period(budget)
            budget.current_usage += credits
            await self._maybe_alert(budget)

    async def record_saving(
        self,
        *,
        source: str,
        engine: str,
        credits: int,
        run_id: str | None = None,
        step_id: str | None = None,
        beneficiary_project_id: str | None = None,
        fetching_project_id: str | None = None,
    ) -> None:
        """Attribute an avoided credit.

        Section 37: with a shared organization cache, SPEND belongs to the
        project that fetched while SAVINGS belong to the project that
        benefited. Keeping both columns is what makes "cross-project cache
        benefit" a computed figure rather than an estimate.
        """
        self.session.add(
            BudgetLedgerEntry(
                org_id=self.org_id,
                project_id=fetching_project_id or self.project_id or self.org_id,
                beneficiary_project_id=beneficiary_project_id or self.project_id,
                run_id=run_id,
                step_id=step_id,
                kind="saving",
                source=source,
                engine=engine,
                credits=credits,
                note=(
                    "cross-project cache benefit"
                    if fetching_project_id and fetching_project_id != self.project_id
                    else source + " cache hit"
                ),
            )
        )

    async def record_routing_saving(
        self, *, credits: int, run_id: str | None = None, note: str = ""
    ) -> None:
        """Credits avoided by choosing a cheaper valid route, before any cache."""
        if credits <= 0:
            return
        self.session.add(
            BudgetLedgerEntry(
                org_id=self.org_id,
                project_id=self.project_id or self.org_id,
                beneficiary_project_id=self.project_id,
                run_id=run_id,
                kind="saving",
                source="routing",
                credits=credits,
                note=note or "cheaper valid route selected",
            )
        )

    async def _maybe_alert(self, budget: Budget) -> None:
        from app.db.models.governance import Alert

        now = datetime.now(UTC)
        utilization = budget.utilization

        if utilization >= 1.0 and budget.exhausted_alert_fired_at is None:
            budget.exhausted_alert_fired_at = now
            self.session.add(
                Alert(
                    org_id=self.org_id,
                    project_id=self.project_id,
                    kind="budget.exhausted",
                    severity="critical",
                    title=budget.scope.title() + " budget exhausted",
                    message=(
                        "The "
                        + budget.scope
                        + " budget of "
                        + str(budget.limit_credits)
                        + " credits is fully consumed. This is the SerpFlow cap, "
                        + "not the upstream SerpApi quota."
                    ),
                    context={"budget_id": budget.id, "scope": budget.scope},
                    dedupe_key="budget.exhausted:" + budget.id,
                )
            )
        elif (
            utilization >= (budget.alert_at or settings.default_budget_alert_ratio)
            and budget.alert_fired_at is None
        ):
            budget.alert_fired_at = now
            self.session.add(
                Alert(
                    org_id=self.org_id,
                    project_id=self.project_id,
                    kind="budget.threshold_reached",
                    severity="warning",
                    title=(
                        budget.scope.title() + " budget at " + str(int(utilization * 100)) + "%"
                    ),
                    message=(
                        str(budget.current_usage)
                        + " of "
                        + str(budget.limit_credits)
                        + " credits used this "
                        + budget.period
                        + " period."
                    ),
                    context={"budget_id": budget.id, "utilization": round(utilization, 3)},
                    dedupe_key="budget.threshold:" + budget.id,
                )
            )

    # -------------------------------------------------------------- reporting
    async def summary(self) -> dict[str, Any]:
        budgets = await self.applicable()
        for budget in budgets:
            await self._roll_period(budget)

        spend = await self.session.scalar(
            select(func.coalesce(func.sum(BudgetLedgerEntry.credits), 0)).where(
                BudgetLedgerEntry.org_id == self.org_id,
                BudgetLedgerEntry.kind == "spend",
            )
        )
        saved = await self.session.scalar(
            select(func.coalesce(func.sum(BudgetLedgerEntry.credits), 0)).where(
                BudgetLedgerEntry.org_id == self.org_id,
                BudgetLedgerEntry.kind == "saving",
            )
        )
        return {
            "budgets": [
                {
                    "id": b.id,
                    "scope": b.scope,
                    "scope_id": b.scope_id,
                    "name": b.name,
                    "limit": b.limit_credits,
                    "current_usage": b.current_usage,
                    "remaining": b.remaining,
                    "utilization": round(b.utilization, 4),
                    "period": b.period,
                    "alert_at": b.alert_at,
                    "on_exhausted": b.on_exhausted,
                }
                for b in budgets
            ],
            "credits_spent_total": int(spend or 0),
            "credits_saved_total": int(saved or 0),
        }

    async def projected_exhaustion(self) -> dict[str, Any] | None:
        """Linear burn-rate projection for the dashboard."""
        budgets = [b for b in await self.applicable() if b.period != "total"]
        if not budgets:
            return None
        budget = min(budgets, key=lambda b: b.remaining)
        start = budget.period_started_at or period_bounds(budget.period)[0]
        elapsed_hours = max(1.0, (datetime.now(UTC) - start).total_seconds() / 3600.0)
        rate = budget.current_usage / elapsed_hours
        if rate <= 0:
            return {
                "budget_id": budget.id,
                "scope": budget.scope,
                "remaining": budget.remaining,
                "burn_rate_per_hour": 0.0,
                "exhausts_at": None,
                "note": "No spend recorded yet this period.",
            }
        hours_left = budget.remaining / rate
        return {
            "budget_id": budget.id,
            "scope": budget.scope,
            "remaining": budget.remaining,
            "burn_rate_per_hour": round(rate, 3),
            "exhausts_at": (datetime.now(UTC) + timedelta(hours=hours_left)).isoformat(),
            "hours_remaining": round(hours_left, 1),
            "period_ends_at": budget.period_ends_at.isoformat() if budget.period_ends_at else None,
        }


async def ensure_budget(
    session: AsyncSession,
    *,
    org_id: str,
    scope: str,
    scope_id: str,
    limit_credits: int,
    period: str = "monthly",
    name: str = "",
    alert_at: float | None = None,
    on_exhausted: str = "error",
) -> Budget:
    existing = await session.scalar(
        select(Budget).where(
            Budget.scope == scope, Budget.scope_id == scope_id, Budget.period == period
        )
    )
    start, end = period_bounds(period)
    if existing is not None:
        existing.limit_credits = limit_credits
        existing.alert_at = alert_at or existing.alert_at
        existing.on_exhausted = on_exhausted
        return existing
    budget = Budget(
        org_id=org_id,
        scope=scope,
        scope_id=scope_id,
        name=name or (scope + " budget"),
        limit_credits=limit_credits,
        period=period,
        period_started_at=start,
        period_ends_at=end,
        alert_at=alert_at or settings.default_budget_alert_ratio,
        on_exhausted=on_exhausted,
    )
    session.add(budget)
    return budget


def today() -> date:
    return datetime.now(UTC).date()


__all__ = [
    "EXHAUSTION_MODES",
    "SCOPES",
    "BudgetService",
    "BudgetVerdict",
    "ensure_budget",
    "period_bounds",
    "today",
]
