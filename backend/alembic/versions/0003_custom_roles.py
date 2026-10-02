"""Custom roles.

An owner can define a role with a permission set of their choosing, for the
shapes the five built-in roles do not cover. A membership's or an API key's
``role`` column holds either a built-in role name or a custom role's slug, so
the slug is unique per organization.

Row-level security applies, like every other tenant-scoped table: a role
defined in one organization is invisible to another.

Revision ID: 0003_custom_roles
Revises: 0002_audit_purge
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_custom_roles"
down_revision: str | None = "0002_audit_purge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custom_roles",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=300), server_default="", nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name="fk_custom_roles_org_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_custom_roles"),
        sa.UniqueConstraint("org_id", "slug", name="uq_custom_roles_org_slug"),
    )
    op.create_index("ix_custom_roles_org_id", "custom_roles", ["org_id"])
    op.create_index("ix_custom_roles_slug", "custom_roles", ["slug"])

    # Same policy as every other tenant-scoped table: see 0001_initial_schema.
    op.execute("ALTER TABLE custom_roles ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY serpflow_tenant_isolation ON custom_roles
          USING (org_id = current_setting('app.current_org', true)
                 OR coalesce(current_setting('app.current_org', true), '') = '')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS serpflow_tenant_isolation ON custom_roles")
    op.drop_index("ix_custom_roles_slug", table_name="custom_roles")
    op.drop_index("ix_custom_roles_org_id", table_name="custom_roles")
    op.drop_table("custom_roles")
