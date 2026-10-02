"""Append-only, tamper-evident audit log (section 54).

Each entry stores the hash of the previous entry for its organization, so the
chain can be verified and any insertion, deletion or edit shows up as a break
at a known sequence number.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, redact_mapping
from app.db.models.governance import AuditLogEntry

log = get_logger("serpflow.audit")

GENESIS = "0" * 64


def compute_hash(
    *,
    prev_hash: str,
    sequence: int,
    org_id: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    before: Any,
    after: Any,
    created_at: datetime | None,
) -> str:
    material = json.dumps(
        {
            "prev": prev_hash,
            "seq": sequence,
            "org": org_id,
            "actor": actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "before": before,
            "after": after,
            "at": created_at.isoformat() if created_at else None,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class AuditService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self.session = session
        self.org_id = org_id

    async def record(
        self,
        *,
        action: str,
        actor_id: str | None = None,
        actor_type: str = "user",
        actor_label: str = "",
        resource_type: str = "",
        resource_id: str | None = None,
        project_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip: str = "",
        user_agent: str = "",
        request_id: str | None = None,
    ) -> AuditLogEntry:
        last = await self.session.scalar(
            select(AuditLogEntry)
            .where(AuditLogEntry.org_id == self.org_id)
            .order_by(AuditLogEntry.sequence.desc())
            .limit(1)
        )
        sequence = (last.sequence + 1) if last else 1
        prev_hash = last.entry_hash if last else GENESIS

        # Audit bodies frequently carry request payloads, so they go through
        # the same redaction the log sinks use.
        safe_before = redact_mapping(before) if before else None
        safe_after = redact_mapping(after) if after else None

        # The table carries a BEFORE UPDATE/DELETE trigger that makes it
        # genuinely append-only, so the hash has to be final before the INSERT.
        # That means created_at is set here rather than by the server default.
        created_at = datetime.now(UTC)
        entry = AuditLogEntry(
            org_id=self.org_id,
            created_at=created_at,
            sequence=sequence,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_label=actor_label[:200],
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            project_id=project_id,
            before=safe_before,
            after=safe_after,
            ip=ip[:64],
            user_agent=user_agent[:400],
            request_id=request_id,
            prev_hash=prev_hash,
            entry_hash=compute_hash(
                prev_hash=prev_hash,
                sequence=sequence,
                org_id=self.org_id,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                before=safe_before,
                after=safe_after,
                created_at=created_at,
            ),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def verify_chain(self, *, limit: int | None = None) -> dict[str, Any]:
        """Walk the chain and report the first break, if any."""
        query = (
            select(AuditLogEntry)
            .where(AuditLogEntry.org_id == self.org_id)
            .order_by(AuditLogEntry.sequence.asc())
        )
        if limit:
            query = query.limit(limit)
        rows = list((await self.session.scalars(query)).all())

        expected_prev = GENESIS
        for row in rows:
            if row.prev_hash != expected_prev:
                return {
                    "valid": False,
                    "entries_checked": rows.index(row),
                    "break_at_sequence": row.sequence,
                    "reason": "prev_hash does not match the preceding entry hash",
                }
            recomputed = compute_hash(
                prev_hash=row.prev_hash,
                sequence=row.sequence,
                org_id=row.org_id,
                actor_id=row.actor_id,
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                before=row.before,
                after=row.after,
                created_at=row.created_at,
            )
            if recomputed != row.entry_hash:
                return {
                    "valid": False,
                    "entries_checked": rows.index(row),
                    "break_at_sequence": row.sequence,
                    "reason": "entry contents do not match the stored hash",
                }
            expected_prev = row.entry_hash

        return {"valid": True, "entries_checked": len(rows), "head": expected_prev}

    async def allow_purge(self) -> None:
        """Permit audit deletion for the remainder of this transaction.

        The database trigger refuses DELETE unless this is set, so deleting an
        organization (or resetting the demo) has to opt in explicitly. UPDATE
        is refused unconditionally and has no escape hatch at all.
        """
        await self.session.execute(text("SELECT set_config('app.audit_purge', 'on', true)"))

    async def count(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count(AuditLogEntry.id)).where(AuditLogEntry.org_id == self.org_id)
            )
            or 0
        )

    async def export(self, *, limit: int = 10000) -> list[dict[str, Any]]:
        rows = (
            await self.session.scalars(
                select(AuditLogEntry)
                .where(AuditLogEntry.org_id == self.org_id)
                .order_by(AuditLogEntry.sequence.asc())
                .limit(limit)
            )
        ).all()
        return [
            {
                "sequence": r.sequence,
                "timestamp": r.created_at.isoformat(),
                "actor_id": r.actor_id,
                "actor_type": r.actor_type,
                "actor_label": r.actor_label,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "project_id": r.project_id,
                "before": r.before,
                "after": r.after,
                "ip": r.ip,
                "request_id": r.request_id,
                "prev_hash": r.prev_hash,
                "entry_hash": r.entry_hash,
            }
            for r in rows
        ]


__all__ = ["GENESIS", "AuditService", "compute_hash"]
