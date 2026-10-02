"""Narrow the audit-log append-only guard.

The original trigger refused every UPDATE and DELETE, which is the right
default: ordinary application code must never be able to rewrite history.

But two legitimate operations do delete audit rows - deleting an organization
(section 34 gives owners that right) and the seed script's ``--reset`` - and
both were failing on the cascade.

So: UPDATE stays forbidden unconditionally, and DELETE is permitted only inside
a transaction that has explicitly set ``app.audit_purge = 'on'``. That setting
is transaction-scoped via SET LOCAL and is used in exactly one place,
``app/services/audit/service.py:AuditService.purge``, so the guarantee survives
while the legitimate path works.

Revision ID: 0002_audit_purge
Revises: 0001_initial
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_audit_purge"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION serpflow_audit_append_only()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
               AND coalesce(current_setting('app.audit_purge', true), '') = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION
                'audit_log is append-only; % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION serpflow_audit_append_only()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
