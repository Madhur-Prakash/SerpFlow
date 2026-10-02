"""Budget ledger, audit log, alerts and notification channels.

Section 38 budgets exist at four scopes: organization, project, api_key,
session. Section 39 is the rule that stops the dashboard lying: a SerpFlow cap
being exhausted and a SerpApi account being out of quota are different events
with different fixes, and are never conflated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_id


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "period", name="uq_budgets_scope_period"),
        Index("ix_budgets_org_scope", "org_id", "scope"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("bgt"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # organization | project | api_key | session
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    limit_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    current_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # daily | weekly | monthly | total
    period: Mapped[str] = mapped_column(String(16), default="monthly", nullable=False)
    period_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    alert_at: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    alert_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exhausted_alert_fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # stale | error | queue
    on_exhausted: Mapped[str] = mapped_column(String(12), default="error", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def remaining(self) -> int:
        return max(0, self.limit_credits - self.current_usage)

    @property
    def utilization(self) -> float:
        if self.limit_credits <= 0:
            return 0.0
        return self.current_usage / self.limit_credits


class BudgetLedgerEntry(Base, TimestampMixin):
    """Append-only spend/savings ledger.

    Section 37: when a shared organization cache is enabled, SPEND is attributed
    to the project that fetched, while SAVINGS are attributed to the project
    that benefited. ``beneficiary_project_id`` is what makes
    "cross-project cache benefit" computable rather than estimated.
    """

    __tablename__ = "budget_ledger"
    __table_args__ = (
        Index("ix_ledger_project_created", "project_id", "created_at"),
        Index("ix_ledger_org_created", "org_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("led"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    beneficiary_project_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    step_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    principal_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # spend | saving
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    # live | exact | semantic | archive | routing
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    engine: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)


class AuditLogEntry(Base, TimestampMixin):
    """Append-only, tamper-evident via a per-org hash chain (section 54)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_org_created", "org_id", "created_at"),
        Index("ix_audit_actor", "actor_id"),
        Index("ix_audit_resource", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("aud"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    actor_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    actor_label: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    user_agent: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(60), nullable=True)

    prev_hash: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(80), default="", nullable=False)


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_org_status", "org_id", "status"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("alrt"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(12), default="warning", nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)


class NotificationChannel(Base, TimestampMixin):
    __tablename__ = "notification_channels"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("chan"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # email | webhook | slack
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    secret_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    events: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_delivery_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WebhookDelivery(Base, TimestampMixin):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_deliveries_channel", "channel_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("whd"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(400), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "Alert",
    "AuditLogEntry",
    "Budget",
    "BudgetLedgerEntry",
    "NotificationChannel",
    "WebhookDelivery",
]
