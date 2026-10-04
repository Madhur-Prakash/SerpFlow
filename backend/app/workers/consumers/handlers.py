"""Kafka consumer handlers for every background topic (section 43)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select

from app.core import metrics
from app.core.logging import bind, get_logger
from app.db.session import session_scope
from app.workers import kafka

log = get_logger("serpflow.workers")


# --------------------------------------------------------------------------
# serpflow.runs.execute - scheduled, bulk, retried and webhook-triggered runs
# --------------------------------------------------------------------------
async def handle_run_execute(message: dict[str, Any]) -> None:
    from app.services.runs import execute_background_run

    run_id = message.get("run_id")
    org_id = message.get("org_id")
    bind(run_id=run_id, org_id=org_id)
    if not run_id or not org_id:
        log.warning("run execute message missing identifiers", extra={"event": "worker.bad_msg"})
        return
    async with session_scope(org_id) as session:
        await execute_background_run(session, run_id=run_id, org_id=org_id)


# --------------------------------------------------------------------------
# serpflow.cache.refresh - adaptive TTL learning (section 20)
# --------------------------------------------------------------------------
async def handle_cache_refresh(message: dict[str, Any]) -> None:
    from app.db.models.caching import CacheEntry, TTLObservation
    from app.services.cache.ttl import adapt, compare_top_results, top_results_digest

    entry_id = message.get("cache_entry_id")
    org_id = message.get("org_id")
    if not entry_id or not org_id:
        return

    async with session_scope(org_id) as session:
        entry = await session.get(CacheEntry, entry_id)
        if entry is None or entry.org_id != org_id:
            return

        new_digest = message.get("new_digest") or top_results_digest(message.get("payload") or {})
        previous_ids = message.get("previous_top_ids") or []
        current_ids = message.get("current_top_ids") or []
        if previous_ids or current_ids:
            churn, unchanged = compare_top_results(previous_ids, current_ids)
        else:
            unchanged = bool(entry.top_results_digest) and entry.top_results_digest == new_digest
            churn = 0.0 if unchanged else 1.0

        observed_interval = None
        if entry.last_hit_at:
            observed_interval = int((datetime.now(UTC) - entry.last_hit_at).total_seconds())

        decision = adapt(
            entry.ttl_seconds,
            churn=churn,
            top10_unchanged=unchanged,
            observed_interval_seconds=observed_interval,
        )
        previous_ttl = entry.ttl_seconds
        entry.ttl_seconds = decision.ttl_seconds
        entry.ttl_source = decision.source
        entry.expires_at = datetime.now(UTC) + timedelta(seconds=decision.ttl_seconds)
        entry.top_results_digest = new_digest
        entry.refresh_count += 1

        session.add(
            TTLObservation(
                org_id=org_id,
                project_id=entry.project_id,
                engine=entry.engine,
                query_class=message.get("query_class", "general"),
                cache_entry_id=entry.id,
                previous_ttl_seconds=previous_ttl,
                new_ttl_seconds=decision.ttl_seconds,
                direction=decision.direction,
                top10_changed=not unchanged,
                churn_ratio=churn,
                observed_interval_seconds=observed_interval,
            )
        )
        metrics.adaptive_ttl_seconds.labels(
            engine=metrics.safe_label(entry.engine), direction=decision.direction
        ).observe(decision.ttl_seconds)


# --------------------------------------------------------------------------
# serpflow.credentials.validate - periodic background validation (section 26)
# --------------------------------------------------------------------------
async def handle_credential_validate(message: dict[str, Any]) -> None:
    from app.db.models.governance import Alert
    from app.db.models.keys import UpstreamCredential
    from app.services.credentials.service import CredentialService

    org_id = message.get("org_id")
    credential_id = message.get("credential_id")
    if not org_id:
        return

    async with session_scope(org_id) as session:
        service = CredentialService(session, org_id=org_id)
        if credential_id:
            credentials = [await service.get(credential_id)]
        else:
            credentials = [c for c in await service.list() if c.revoked_at is None]

        for credential in credentials:
            if not credential.ciphertext:
                continue
            try:
                await service.validate(credential)
            except Exception:
                session.add(
                    Alert(
                        org_id=org_id,
                        kind="credential.validation_failed",
                        severity="critical",
                        title="Credential validation failed",
                        message=(
                            "Credential "
                            + credential.name
                            + " ("
                            + credential.fingerprint
                            + ") failed its scheduled upstream validation."
                        ),
                        context={"credential_id": credential.id},
                        dedupe_key="credential.validation_failed:" + credential.id,
                    )
                )
        _ = UpstreamCredential


# --------------------------------------------------------------------------
# serpflow.quota.reconcile - section 40
# --------------------------------------------------------------------------
async def handle_quota_reconcile(message: dict[str, Any]) -> None:
    from app.db.models.governance import Alert, BudgetLedgerEntry
    from app.db.models.keys import UpstreamQuotaSnapshot
    from app.services.credentials.service import CredentialService

    org_id = message.get("org_id")
    if not org_id:
        return

    async with session_scope(org_id) as session:
        service = CredentialService(session, org_id=org_id)
        for credential in await service.list():
            if credential.revoked_at is not None or not credential.ciphertext:
                continue
            last = await session.scalar(
                select(UpstreamQuotaSnapshot)
                .where(UpstreamQuotaSnapshot.credential_id == credential.id)
                .order_by(UpstreamQuotaSnapshot.created_at.desc())
                .limit(1)
            )
            since = last.created_at if last else datetime.now(UTC) - timedelta(days=1)
            internal = int(
                await session.scalar(
                    select(func.coalesce(func.sum(BudgetLedgerEntry.credits), 0)).where(
                        BudgetLedgerEntry.org_id == org_id,
                        BudgetLedgerEntry.kind == "spend",
                        BudgetLedgerEntry.created_at >= since,
                    )
                )
                or 0
            )
            try:
                snapshot = await service.reconcile_quota(
                    credential, internal_spend_since_last=internal
                )
            except Exception as exc:
                log.warning(
                    "quota reconcile failed",
                    extra={"event": "quota.reconcile_failed", "error": type(exc).__name__},
                )
                continue

            if snapshot.searches_left is not None:
                metrics.upstream_quota_remaining.labels(
                    credential_fingerprint=metrics.safe_label(credential.fingerprint)
                ).set(snapshot.searches_left)
            if snapshot.divergence is not None:
                metrics.upstream_quota_divergence.labels(
                    credential_fingerprint=metrics.safe_label(credential.fingerprint)
                ).set(snapshot.divergence)
                # Divergence is expected the moment the key is used elsewhere.
                # Surfacing it is the point; hiding it would make the internal
                # ledger look like upstream truth.
                if abs(snapshot.divergence) > 5:
                    session.add(
                        Alert(
                            org_id=org_id,
                            kind="upstream.quota_divergence",
                            severity="warning",
                            title="Upstream quota diverges from the internal ledger",
                            message=(
                                "SerpFlow recorded "
                                + str(snapshot.internal_spend_since_last)
                                + " credits since the last reconciliation, while the SerpApi "
                                + "account consumed "
                                + str(snapshot.upstream_spend_since_last)
                                + ". This credential is likely in use outside SerpFlow."
                            ),
                            context={
                                "credential_id": credential.id,
                                "divergence": snapshot.divergence,
                            },
                            dedupe_key="quota.divergence:" + credential.id,
                        )
                    )


# --------------------------------------------------------------------------
# serpflow.alerts
# --------------------------------------------------------------------------
async def handle_alert(message: dict[str, Any]) -> None:
    from app.db.models.governance import Alert

    org_id = message.get("org_id")
    if not org_id:
        return
    async with session_scope(org_id) as session:
        dedupe = message.get("dedupe_key")
        if dedupe:
            existing = await session.scalar(
                select(Alert).where(
                    Alert.org_id == org_id, Alert.dedupe_key == dedupe, Alert.status == "open"
                )
            )
            if existing is not None:
                return
        session.add(
            Alert(
                org_id=org_id,
                project_id=message.get("project_id"),
                kind=str(message.get("kind", "generic")),
                severity=str(message.get("severity", "warning")),
                title=str(message.get("title", "Alert"))[:240],
                message=str(message.get("message", "")),
                context=message.get("context") or {},
                dedupe_key=dedupe,
            )
        )
    await kafka.publish(
        kafka.TOPIC_WEBHOOKS,
        {
            "org_id": org_id,
            "event": str(message.get("kind", "anomaly.detected")),
            "payload": message,
        },
    )


# --------------------------------------------------------------------------
# serpflow.webhooks (section 61)
# --------------------------------------------------------------------------
async def handle_webhook(message: dict[str, Any]) -> None:
    import hashlib
    import hmac as hmac_mod

    from app.db.models.governance import NotificationChannel, WebhookDelivery

    org_id = message.get("org_id")
    event = str(message.get("event", ""))
    if not org_id or not event:
        return

    async with session_scope(org_id) as session:
        channels = (
            await session.scalars(
                select(NotificationChannel).where(
                    NotificationChannel.org_id == org_id,
                    NotificationChannel.enabled.is_(True),
                )
            )
        ).all()
        for channel in channels:
            if channel.events and event not in channel.events:
                continue
            delivery = WebhookDelivery(
                org_id=org_id,
                channel_id=channel.id,
                event=event,
                payload=message.get("payload") or {},
            )
            session.add(delivery)
            await session.flush()

            if channel.kind == "email":
                await _deliver_email_channel(channel, event, delivery)
                continue

            if channel.kind not in ("webhook", "slack"):
                delivery.status = "skipped"
                continue

            body = json.dumps(
                {"event": event, "org_id": org_id, "data": delivery.payload}, default=str
            )
            headers = {"content-type": "application/json", "x-serpflow-event": event}
            if channel.secret_hash:
                headers["x-serpflow-signature"] = hmac_mod.new(
                    channel.secret_hash.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
                ).hexdigest()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(channel.target, content=body, headers=headers)
                delivery.attempts += 1
                delivery.response_status = response.status_code
                delivery.status = "delivered" if response.status_code < 400 else "failed"
                delivery.delivered_at = datetime.now(UTC)
                channel.last_delivery_at = datetime.now(UTC)
                channel.last_delivery_status = str(response.status_code)
                if response.status_code >= 400:
                    channel.failure_count += 1
            except Exception as exc:
                delivery.attempts += 1
                delivery.status = "failed"
                delivery.error = type(exc).__name__
                channel.failure_count += 1
                channel.last_delivery_status = type(exc).__name__


async def _deliver_email_channel(channel: Any, event: str, delivery: Any) -> None:
    """Send an alert to an `email` notification channel.

    `channel.target` is the address. The alert body is derived from the event
    payload rather than dumped as JSON, because this one goes to a person.
    """
    from app.services.email import EmailSendError, render_alert, send_rendered

    payload = delivery.payload or {}
    title = str(payload.get("title") or event.replace(".", " ").replace("_", " ").capitalize())
    body = str(payload.get("message") or "SerpFlow raised an alert on your organization.")

    details: list[tuple[str, str]] = []
    for key in ("severity", "project_id", "engine", "limit_credits", "current_usage"):
        value = payload.get(key)
        if value is not None:
            details.append((key.replace("_", " ").capitalize(), str(value)))

    rendered = render_alert(
        recipient_name=channel.name or "there",
        kind=event,
        title=title,
        message=body,
        details=details,
        # The label selects the presentation: urgency, opening, closing, and
        # whether the identifiers below are included at all.
        channel_label=channel.name,
    )
    try:
        await send_rendered(channel.target, rendered)
    except EmailSendError as exc:
        delivery.attempts += 1
        delivery.status = "failed"
        delivery.error = str(exc)[:500]
        channel.failure_count += 1
        channel.last_delivery_status = "email_failed"
        return

    delivery.attempts += 1
    delivery.status = "delivered"
    delivery.delivered_at = datetime.now(UTC)
    channel.last_delivery_at = datetime.now(UTC)
    channel.last_delivery_status = "sent"


# --------------------------------------------------------------------------
# serpflow.analytics - rollups
# --------------------------------------------------------------------------
async def handle_analytics(message: dict[str, Any]) -> None:
    org_id = message.get("org_id")
    if not org_id:
        return
    async with session_scope(org_id) as session:
        from app.services.analytics.service import AnalyticsService

        analytics = AnalyticsService(session, org_id=org_id)
        snapshot = await analytics.dashboard(days=1)
        log.info(
            "analytics rollup",
            extra={
                "event": "analytics.rollup",
                "org_id": org_id,
                "credits_spent": snapshot["credits_spent"],
                "credits_saved": snapshot["credits_saved"],
            },
        )


# --------------------------------------------------------------------------
# serpflow.catalog - catalog version changes
# --------------------------------------------------------------------------
async def handle_catalog(message: dict[str, Any]) -> None:
    from app.services.catalog.loader import reload_catalog

    index = reload_catalog()
    log.info(
        "catalog reloaded",
        extra={"event": "catalog.reloaded", "catalog_version": index.version, **index.stats()},
    )
    _ = message


HANDLERS = {
    kafka.TOPIC_RUNS_EXECUTE: handle_run_execute,
    kafka.TOPIC_CACHE_REFRESH: handle_cache_refresh,
    kafka.TOPIC_CREDENTIALS_VALIDATE: handle_credential_validate,
    kafka.TOPIC_QUOTA_RECONCILE: handle_quota_reconcile,
    kafka.TOPIC_ALERTS: handle_alert,
    kafka.TOPIC_WEBHOOKS: handle_webhook,
    kafka.TOPIC_ANALYTICS: handle_analytics,
    kafka.TOPIC_CATALOG: handle_catalog,
}


__all__ = [
    "HANDLERS",
    "handle_alert",
    "handle_analytics",
    "handle_cache_refresh",
    "handle_catalog",
    "handle_credential_validate",
    "handle_quota_reconcile",
    "handle_run_execute",
    "handle_webhook",
]
