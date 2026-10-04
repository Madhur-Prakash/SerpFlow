"""Organizations, users, memberships, projects (section 22).

Organization
    |- Projects
    |     |- Members
    |     |- API Keys
    |     `- optional Credential
    `- Default Credential
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_id

if TYPE_CHECKING:
    from app.db.models.keys import ApiKey, UpstreamCredential


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("org"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    plan_tier: Mapped[str] = mapped_column(String(40), default="free", nullable=False)

    # section 23: organization-level default, inherited when a project has none.
    # use_alter breaks the organizations <-> upstream_credentials cycle so
    # Alembic can order the CREATE TABLE statements.
    default_credential_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("upstream_credentials.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    # section 37: project-level cache isolation by default.
    cache_scope: Mapped[str] = mapped_column(String(20), default="project", nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    projects: Mapped[list[Project]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", lazy="selectin"
    )
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    default_credential: Mapped[UpstreamCredential | None] = relationship(
        foreign_keys=[default_credential_id], lazy="selectin", post_update=True
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("usr"))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # Argon2id. Never serialised, never logged.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_token_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class Membership(Base, TimestampMixin):
    """A user's role inside an organization."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_memberships_org_user"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("mem"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="developer")
    invited_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_projects_org_slug"),
        Index("ix_projects_key_prefix", "key_prefix", unique=True),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("prj"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # 6-character prefix embedded in every API key issued for this project.
    # Stored in plaintext and uniquely indexed for O(1) key identification.
    key_prefix: Mapped[str] = mapped_column(String(6), nullable=False)

    # section 23: project credential wins over the org default.
    credential_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("upstream_credentials.id", ondelete="SET NULL"), nullable=True
    )

    # section 51 policy surface
    engine_allowlist: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    engine_denylist: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    semantic_threshold: Mapped[float | None] = mapped_column(nullable=True)
    ttl_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_high_pii_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shared_cache_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: The project's default execution mode. NULL means "inherit
    #: SERPFLOW_MODE", which is not the same as pinning the project to
    #: whatever that happens to be today: an operator changing the server
    #: default should move every project that never made its own choice,
    #: and should move none that did.
    execution_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="projects")
    credential: Mapped[UpstreamCredential | None] = relationship(
        foreign_keys=[credential_id], lazy="selectin"
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


class ProjectMember(Base, TimestampMixin):
    """Optional per-project role override, narrowing the org-level role."""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("pmem"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="developer")

    project: Mapped[Project] = relationship(back_populates="members")


class AuthSession(Base, TimestampMixin):
    """Refresh-token session with rotation and device revocation (section 62)."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("sess"))
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_agent: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_from: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServicePrincipalSession(Base, TimestampMixin):
    """Machine identity session (section 35).

    An agent is not an ordinary human user with a shared API key. Every
    MCP/service execution resolves service principal + session_id + project_id
    + session_cap so budget enforcement works on machine-originated requests.
    """

    __tablename__ = "service_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("svcs"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    api_key_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_session_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    session_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    runs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


__all__ = [
    "AuthSession",
    "Membership",
    "Organization",
    "Project",
    "ProjectMember",
    "ServicePrincipalSession",
    "User",
]


class CustomRole(Base, TimestampMixin):
    """A role an owner defines, with a permission set they choose.

    The five built-in roles cover the common shapes; this is for the ones they
    do not. A membership's or key's ``role`` column holds either a built-in
    role name or this table's ``slug``, which is why the slug is unique per
    organization and may not collide with a built-in name.

    Permissions are stored as the string values of ``Permission``. Anything
    unrecognised at read time is dropped rather than granted, so removing a
    permission from the enum cannot silently widen a role that referenced it.
    """

    __tablename__ = "custom_roles"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_custom_roles_org_slug"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("role"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
