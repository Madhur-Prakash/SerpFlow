"""Per-project execution mode.

The mode was a server-wide environment variable, so every project in every
organization executed the same way. A project that only ever wants recorded
traffic could not say so while another on the same instance ran live.

NULL means "inherit the server default". That is deliberately distinct from
writing today's default into every row: an operator who later changes
SERPFLOW_MODE should move the projects that never expressed a preference, and
leave alone the ones that did.

Revision ID: 0004_project_mode
Revises: 0003_custom_roles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_project_mode"
down_revision: str | None = "0003_custom_roles"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("execution_mode", sa.String(length=10), nullable=True),
    )
    # `mock` is absent on purpose: it is reachable only through a test API key,
    # so that "this cost nothing" cannot be asserted by configuration.
    op.create_check_constraint(
        "ck_projects_execution_mode",
        "projects",
        "execution_mode IS NULL OR execution_mode IN ('live', 'record', 'replay')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_projects_execution_mode", "projects", type_="check")
    op.drop_column("projects", "execution_mode")
