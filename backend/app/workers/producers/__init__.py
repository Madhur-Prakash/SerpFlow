"""Typed producers for the background topics (section 43)."""

from __future__ import annotations

from typing import Any

from app.workers import kafka


async def queue_run(run_id: str, org_id: str, *, trigger: str = "scheduled") -> bool:
    """Background execution only. Interactive search never goes through Kafka."""
    return await kafka.publish(
        kafka.TOPIC_RUNS_EXECUTE,
        {"run_id": run_id, "org_id": org_id, "trigger": trigger},
        key=org_id,
    )


async def queue_cache_refresh(cache_entry_id: str, org_id: str, **extra: Any) -> bool:
    return await kafka.publish(
        kafka.TOPIC_CACHE_REFRESH,
        {"cache_entry_id": cache_entry_id, "org_id": org_id, **extra},
        key=org_id,
    )


async def queue_credential_validation(org_id: str, credential_id: str | None = None) -> bool:
    return await kafka.publish(
        kafka.TOPIC_CREDENTIALS_VALIDATE,
        {"org_id": org_id, "credential_id": credential_id},
        key=org_id,
    )


async def queue_quota_reconcile(org_id: str) -> bool:
    return await kafka.publish(kafka.TOPIC_QUOTA_RECONCILE, {"org_id": org_id}, key=org_id)


async def queue_alert(
    org_id: str,
    kind: str,
    title: str,
    message: str,
    *,
    severity: str = "warning",
    project_id: str | None = None,
    context: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> bool:
    return await kafka.publish(
        kafka.TOPIC_ALERTS,
        {
            "org_id": org_id,
            "project_id": project_id,
            "kind": kind,
            "severity": severity,
            "title": title,
            "message": message,
            "context": context or {},
            "dedupe_key": dedupe_key,
        },
        key=org_id,
    )


async def queue_webhook(org_id: str, event: str, payload: dict[str, Any]) -> bool:
    """Section 61 events: budget.threshold_reached, run.completed, run.failed,
    anomaly.detected, routing.accuracy_regressed, credential.validation_failed,
    upstream.quota_changed."""
    return await kafka.publish(
        kafka.TOPIC_WEBHOOKS,
        {"org_id": org_id, "event": event, "payload": payload},
        key=org_id,
    )


async def queue_analytics_rollup(org_id: str) -> bool:
    return await kafka.publish(kafka.TOPIC_ANALYTICS, {"org_id": org_id}, key=org_id)


async def queue_catalog_reload(catalog_version: str) -> bool:
    return await kafka.publish(
        kafka.TOPIC_CATALOG, {"catalog_version": catalog_version}, key=catalog_version
    )


__all__ = [
    "queue_alert",
    "queue_analytics_rollup",
    "queue_cache_refresh",
    "queue_catalog_reload",
    "queue_credential_validation",
    "queue_quota_reconcile",
    "queue_run",
    "queue_webhook",
]
