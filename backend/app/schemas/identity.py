"""Auth, organization, project, member, API key and credential schemas.

Section 25 is enforced structurally here: there is no field anywhere in this
module that could carry an upstream SerpApi secret. Not excluded - absent.
``exclude=True`` leaks through serialisation bugs; a field that does not exist
cannot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import APIModel

Role = Literal["owner", "admin", "developer", "analyst", "service"]
KeyEnvironment = Literal["live", "test"]


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
class RegisterRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(default="", max_length=200)
    organization_name: str | None = Field(default=None, max_length=200)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        if value.isdigit() or value.isalpha():
            raise ValueError("password must mix letters with digits or symbols")
        return value


class LoginRequest(APIModel):
    email: EmailStr
    password: str


class RefreshRequest(APIModel):
    refresh_token: str


class TokenResponse(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: datetime
    session_id: str
    org_id: str
    role: Role


class UserResponse(APIModel):
    id: str
    email: str
    full_name: str
    email_verified: bool
    mfa_enabled: bool
    last_login_at: datetime | None = None
    created_at: datetime


class SessionResponse(APIModel):
    id: str
    user_agent: str
    ip: str
    created_at: datetime
    last_seen_at: datetime | None = None
    expires_at: datetime


class MeResponse(APIModel):
    user: UserResponse | None = None
    principal_type: str
    org_id: str
    project_id: str | None = None
    role: Role
    permissions: list[str]
    organization: OrganizationResponse | None = None
    projects: list[ProjectResponse] = Field(default_factory=list)


class PasswordResetRequest(APIModel):
    email: EmailStr


class PasswordResetConfirm(APIModel):
    token: str
    password: str = Field(min_length=10, max_length=128)


class VerifyEmailRequest(APIModel):
    token: str


# --------------------------------------------------------------------------
# organizations and projects
# --------------------------------------------------------------------------
class OrganizationResponse(APIModel):
    id: str
    name: str
    slug: str
    plan_tier: str
    cache_scope: Literal["project", "organization"]
    default_credential_id: str | None = None
    created_at: datetime


class OrganizationUpdate(APIModel):
    name: str | None = Field(default=None, max_length=200)
    cache_scope: Literal["project", "organization"] | None = None
    default_credential_id: str | None = None


class ProjectResponse(APIModel):
    id: str
    org_id: str
    name: str
    slug: str
    description: str
    key_prefix: str
    credential_id: str | None = None
    engine_allowlist: list[str] = Field(default_factory=list)
    engine_denylist: list[str] = Field(default_factory=list)
    semantic_threshold: float | None = None
    ttl_overrides: dict[str, Any] = Field(default_factory=dict)
    retention_days: int | None = None
    retention_high_pii_days: int | None = None
    shared_cache_enabled: bool = False
    created_at: datetime


class ProjectCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=2000)


class ProjectUpdate(APIModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    credential_id: str | None = None
    engine_allowlist: list[str] | None = None
    engine_denylist: list[str] | None = None
    semantic_threshold: float | None = Field(default=None, ge=0.5, le=1.0)
    ttl_overrides: dict[str, int] | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    retention_high_pii_days: int | None = Field(default=None, ge=1, le=365)
    # Enabling this crosses a billing and data boundary; the UI states that at
    # the point of toggling it (section 51).
    shared_cache_enabled: bool | None = None


class MemberResponse(APIModel):
    id: str
    user_id: str
    email: str
    full_name: str
    role: Role
    accepted_at: datetime | None = None
    created_at: datetime


class MemberInvite(APIModel):
    email: EmailStr
    role: Role = "developer"


class MemberUpdate(APIModel):
    role: Role


# --------------------------------------------------------------------------
# API keys
# --------------------------------------------------------------------------
class ApiKeyResponse(APIModel):
    """Never carries the secret. ``display`` is ``sf_live_pm8kd3_****``."""

    id: str
    project_id: str
    name: str
    environment: KeyEnvironment
    project_prefix: str
    display: str
    role: Role
    is_service_principal: bool
    session_cap: int | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    use_count: int
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    rotation_grace_until: datetime | None = None
    created_at: datetime


class ApiKeyCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    environment: KeyEnvironment = "test"
    role: Role = "developer"
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    is_service_principal: bool = False
    session_cap: int | None = Field(default=None, ge=1)


class ApiKeyCreated(APIModel):
    """The only response that ever contains a plaintext key, shown once."""

    key: ApiKeyResponse
    plaintext: str
    warning: str = (
        "Copy this key now. It is stored only as an HMAC-SHA256 hash and cannot be shown again."
    )


class ApiKeyRotate(APIModel):
    grace_minutes: int = Field(default=60, ge=0, le=10080)


# --------------------------------------------------------------------------
# upstream credentials
# --------------------------------------------------------------------------
class CredentialCreate(APIModel):
    """Request only. The secret is accepted, encrypted, and never echoed."""

    name: str = Field(min_length=1, max_length=160)
    api_key: str = Field(min_length=8, max_length=256)
    project_id: str | None = None
    set_as_org_default: bool = False
    validate_now: bool = True


class CredentialRotate(APIModel):
    api_key: str = Field(min_length=8, max_length=256)
    grace_minutes: int = Field(default=15, ge=0, le=1440)


class CredentialResponse(APIModel):
    """Everything a client may see about a credential.

    There is deliberately no ``api_key``, ``secret`` or ``ciphertext`` field in
    this model. Renders as ``...a3f9 - added Sep 12 - validated 2h ago``.
    """

    id: str
    name: str
    provider: str
    project_id: str | None = None
    fingerprint: str
    display: str
    kek_id: str
    algo: str
    validation_status: str
    validation_error: str | None = None
    last_validated_at: datetime | None = None
    created_at: datetime
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    upstream_plan: str | None = None
    upstream_searches_left: int | None = None
    upstream_checked_at: datetime | None = None


MeResponse.model_rebuild()


__all__ = [
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyResponse",
    "ApiKeyRotate",
    "CredentialCreate",
    "CredentialResponse",
    "CredentialRotate",
    "KeyEnvironment",
    "LoginRequest",
    "MeResponse",
    "MemberInvite",
    "MemberResponse",
    "MemberUpdate",
    "OrganizationResponse",
    "OrganizationUpdate",
    "PasswordResetConfirm",
    "PasswordResetRequest",
    "ProjectCreate",
    "ProjectResponse",
    "ProjectUpdate",
    "RefreshRequest",
    "RegisterRequest",
    "Role",
    "SessionResponse",
    "TokenResponse",
    "UserResponse",
    "VerifyEmailRequest",
]
