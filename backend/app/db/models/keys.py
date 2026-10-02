"""SerpFlow API keys and the upstream SerpApi credential vault.

Two completely separate things (section 23):

* ``ApiKey``            - how a caller authenticates *to* SerpFlow.
* ``UpstreamCredential`` - the SerpApi key SerpFlow spends *on behalf of* a project.

The credential secret only exists here as ciphertext. It is decrypted in
exactly one place: the executor (section 25). It appears in no response schema
anywhere in ``app/schemas``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_id


class ApiKey(Base, TimestampMixin):
    """``sf_<env>_<project_prefix>_<secret>`` (sections 28-32).

    ``key_hash`` is HMAC-SHA256 under a server-side pepper, not Argon2: these
    secrets carry 190+ bits of entropy so there is no brute-force surface, and
    Argon2 would cost 50-100 ms on every single request.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_hash", "key_hash", unique=True),
        Index("ix_api_keys_prefix_env", "project_prefix", "environment"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("key"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)

    environment: Mapped[str] = mapped_column(String(8), nullable=False)  # live | test
    # plaintext and indexed: enables O(1) identification without scanning keys
    project_prefix: Mapped[str] = mapped_column(String(6), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    display: Mapped[str] = mapped_column(String(64), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False, default="developer")
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_used_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # rotation: both keys valid during the grace window (section 32)
    rotated_from_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rotation_grace_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # section 35: machine identity
    is_service_principal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    session_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)

    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    project = relationship("Project", back_populates="api_keys", lazy="selectin")

    @property
    def is_test(self) -> bool:
        """Test keys route to the deterministic mock and spend zero credits."""
        return self.environment == "test"


class UpstreamCredential(Base, TimestampMixin):
    """Envelope-encrypted SerpApi credential (sections 24-27).

    Per credential: a random DEK, itself encrypted under a KEK. Only
    ``ciphertext`` + ``encrypted_dek`` are stored; there is no column holding a
    recoverable plaintext key, and no Pydantic response model exposes either.
    """

    __tablename__ = "upstream_credentials"
    __table_args__ = (Index("ix_upstream_credentials_org_active", "org_id", "revoked_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("cred"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL means an organization-level credential available for inheritance.
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="serpapi", nullable=False)

    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_dek: Mapped[str] = mapped_column(Text, nullable=False)
    kek_id: Mapped[str] = mapped_column(String(80), nullable=False)
    algo: Mapped[str] = mapped_column(String(40), nullable=False)
    # sha256(key)[:8] - non-reversible, safe to render
    fingerprint: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    validation_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    validation_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_from_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # old credential stays usable for in-flight runs until this moment
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # last reconciled upstream account state (section 40)
    upstream_plan: Mapped[str | None] = mapped_column(String(80), nullable=True)
    upstream_searches_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upstream_total_searches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upstream_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class UpstreamQuotaSnapshot(Base, TimestampMixin):
    """Periodic reconciliation of SerpFlow's ledger against SerpApi's account
    endpoint (section 40). The two diverge the moment the credential is used
    outside SerpFlow, and the dashboard must show that rather than hide it."""

    __tablename__ = "upstream_quota_snapshots"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id("quota"))
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("upstream_credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(16), nullable=False)
    plan_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    searches_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_searches_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    this_month_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    internal_spend_since_last: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    upstream_spend_since_last: Mapped[int | None] = mapped_column(Integer, nullable=True)
    divergence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


__all__ = ["ApiKey", "UpstreamCredential", "UpstreamQuotaSnapshot"]
