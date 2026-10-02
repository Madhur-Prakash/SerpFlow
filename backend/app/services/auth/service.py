"""Authentication, API keys and principal resolution (sections 28-35, 62).

Two completely different principal kinds resolve through here:

* a human session, authenticated by a JWT pair with refresh rotation
* an API key principal - which may be a service principal with its own
  session identity and session cap (section 35)

An agent is not modelled as an ordinary human user holding a shared API key.
Every machine-originated execution resolves service principal + session_id +
project_id + session_cap so budget enforcement actually applies to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    InvalidApiKeyError,
    InvalidCredentialsError,
    NotFoundError,
    SessionCapExceededError,
)
from app.core.logging import get_logger
from app.core.permissions import (
    Permission,
    Role,
    has_permission,
    is_builtin_role,
    permissions_for,
)
from app.core.security import (
    MintedApiKey,
    create_token,
    generate_opaque_token,
    generate_project_prefix,
    hash_api_key,
    hash_opaque_token,
    hash_password,
    mint_api_key,
    parse_api_key,
    verify_api_key,
    verify_password,
)
from app.db.models.identity import (
    AuthSession,
    Membership,
    Organization,
    Project,
    ProjectMember,
    ServicePrincipalSession,
    User,
)
from app.db.models.keys import ApiKey
from app.services.cache.redis_client import (
    cache_principal,
    get_cached_principal,
    invalidate_principal,
)

log = get_logger("serpflow.auth")


@dataclass(slots=True)
class Principal:
    """Who is making this request, and what they may do."""

    id: str
    type: str  # user | api_key | service
    org_id: str
    role: str
    project_id: str | None = None
    email: str | None = None
    display: str = ""
    api_key_id: str | None = None
    key_environment: str | None = None
    session_id: str | None = None
    session_cap: int | None = None
    permissions: frozenset[Permission] = field(default_factory=frozenset)

    @property
    def is_test_key(self) -> bool:
        """Test keys always route to the deterministic mock (section 21)."""
        return self.key_environment == "test"

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "role": self.role,
            "email": self.email,
            "display": self.display,
            "api_key_id": self.api_key_id,
            "key_environment": self.key_environment,
            "session_id": self.session_id,
            "session_cap": self.session_cap,
            "permissions": sorted(str(p) for p in self.permissions),
        }


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        #: Set by `register`. The plaintext email-verification token, held just
        #: long enough for the endpoint to mail it. Never persisted.
        self.last_verification_token: str | None = None

    # ----------------------------------------------------------- user auth
    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str = "",
        org_name: str | None = None,
    ) -> tuple[User, Organization, Membership]:
        existing = await self.session.scalar(select(User).where(User.email == email.lower()))
        if existing is not None:
            raise ConflictError("An account with that email already exists.")

        # The plaintext is kept on the instance, not in the row, so the caller
        # can mail it and nothing else can read it back afterwards. Only the
        # hash is persisted.
        verification_token = generate_opaque_token()
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            full_name=full_name or email.split("@")[0],
            email_verification_token_hash=hash_opaque_token(verification_token),
        )
        self.session.add(user)
        await self.session.flush()

        name = org_name or (full_name or email.split("@")[0]) + "'s organization"
        org = Organization(name=name, slug=await self._unique_slug(name))
        self.session.add(org)
        await self.session.flush()

        membership = Membership(
            org_id=org.id, user_id=user.id, role=str(Role.OWNER), accepted_at=datetime.now(UTC)
        )
        self.session.add(membership)
        await self.session.flush()
        self.last_verification_token = verification_token
        return user, org, membership

    async def issue_password_reset(self, email: str) -> tuple[User, str] | None:
        """Mint a reset token and return it with the user, or None if unknown.

        The caller must respond identically either way: whether an address is
        registered is not something an unauthenticated caller gets to learn.
        """
        user = await self.session.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            return None
        token = generate_opaque_token()
        user.password_reset_token_hash = hash_opaque_token(token)
        user.password_reset_expires_at = datetime.now(UTC) + timedelta(
            seconds=settings.password_reset_ttl_seconds
        )
        return user, token

    async def _unique_slug(self, name: str) -> str:
        import re

        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
        slug = base
        suffix = 1
        while await self.session.scalar(select(Organization).where(Organization.slug == slug)):
            suffix += 1
            slug = base + "-" + str(suffix)
        return slug

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.session.scalar(select(User).where(User.email == email.lower()))
        if user is None or not user.is_active:
            # Same error either way: enumeration is a real attack surface.
            raise InvalidCredentialsError()
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()
        return user

    async def issue_session(
        self, user: User, *, ip: str = "", user_agent: str = ""
    ) -> dict[str, Any]:
        membership = await self.session.scalar(
            select(Membership).where(Membership.user_id == user.id)
        )
        org_id = membership.org_id if membership else ""
        role = membership.role if membership else str(Role.DEVELOPER)

        access, access_expires = create_token(
            user.id, "access", extra={"org_id": org_id, "role": role}
        )
        refresh_raw = generate_opaque_token()
        refresh_token, refresh_expires = create_token(
            user.id, "refresh", extra={"org_id": org_id, "jti_raw": hash_opaque_token(refresh_raw)}
        )
        auth_session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_opaque_token(refresh_token),
            user_agent=user_agent[:400],
            ip=ip[:64],
            expires_at=refresh_expires,
            last_seen_at=datetime.now(UTC),
        )
        self.session.add(auth_session)
        user.last_login_at = datetime.now(UTC)
        user.last_login_ip = ip[:64]
        await self.session.flush()

        return {
            "access_token": access,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_ttl_seconds,
            "expires_at": access_expires.isoformat(),
            "session_id": auth_session.id,
            "org_id": org_id,
            "role": role,
        }

    async def rotate_refresh(self, refresh_token: str, *, ip: str = "") -> dict[str, Any]:
        """Refresh rotation: the old handle is revoked as the new one is issued."""
        from app.core.security import decode_token

        try:
            payload = decode_token(refresh_token, "refresh")
        except Exception as exc:
            raise InvalidCredentialsError("The refresh token is invalid or expired.") from exc

        token_hash = hash_opaque_token(refresh_token)
        existing = await self.session.scalar(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )
        if existing is None or existing.revoked_at is not None:
            raise InvalidCredentialsError("This refresh token has already been used or revoked.")
        if existing.expires_at < datetime.now(UTC):
            raise InvalidCredentialsError("The refresh token has expired.")

        user = await self.session.get(User, payload["sub"])
        if user is None or not user.is_active:
            raise InvalidCredentialsError()

        existing.revoked_at = datetime.now(UTC)
        issued = await self.issue_session(user, ip=ip, user_agent=existing.user_agent)
        new_session = await self.session.get(AuthSession, issued["session_id"])
        if new_session is not None:
            new_session.rotated_from = existing.id
        return issued

    async def revoke_session(self, session_id: str, user_id: str) -> None:
        row = await self.session.get(AuthSession, session_id)
        if row is None or row.user_id != user_id:
            raise NotFoundError("Session not found.")
        row.revoked_at = datetime.now(UTC)

    async def list_sessions(self, user_id: str) -> list[AuthSession]:
        return list(
            (
                await self.session.scalars(
                    select(AuthSession)
                    .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                    .order_by(AuthSession.created_at.desc())
                )
            ).all()
        )

    # ---------------------------------------------------------- API keys
    async def create_api_key(
        self,
        *,
        org_id: str,
        project: Project,
        name: str,
        environment: str = "live",
        role: str = "developer",
        created_by: str | None = None,
        expires_in_days: int | None = None,
        is_service_principal: bool = False,
        session_cap: int | None = None,
    ) -> tuple[ApiKey, MintedApiKey]:
        """Mint a key. The plaintext is returned once and never stored."""
        minted = mint_api_key(environment, project.key_prefix)
        row = ApiKey(
            org_id=org_id,
            project_id=project.id,
            name=name,
            environment=environment,
            project_prefix=project.key_prefix,
            key_hash=minted.key_hash,
            display=minted.display,
            role=role,
            created_by=created_by,
            is_service_principal=is_service_principal,
            session_cap=session_cap,
            expires_at=(
                datetime.now(UTC) + timedelta(days=expires_in_days) if expires_in_days else None
            ),
        )
        self.session.add(row)
        await self.session.flush()
        return row, minted

    async def revoke_api_key(self, key_id: str, org_id: str, *, reason: str = "") -> ApiKey:
        row = await self.session.get(ApiKey, key_id)
        if row is None or row.org_id != org_id:
            raise NotFoundError("API key not found.")
        row.revoked_at = datetime.now(UTC)
        row.revoked_reason = reason[:200]
        # Immediate invalidation: a revoked key must stop working now, not when
        # the 60-second principal cache happens to expire.
        await invalidate_principal(row.key_hash)
        return row

    async def rotate_api_key(
        self, key_id: str, org_id: str, *, grace_minutes: int = 60, created_by: str | None = None
    ) -> tuple[ApiKey, MintedApiKey]:
        """Issue a replacement; both keys work during the grace window."""
        old = await self.session.get(ApiKey, key_id)
        if old is None or old.org_id != org_id:
            raise NotFoundError("API key not found.")
        project = await self.session.get(Project, old.project_id)
        if project is None:
            raise NotFoundError("Project not found.")

        new_row, minted = await self.create_api_key(
            org_id=org_id,
            project=project,
            name=old.name + " (rotated)",
            environment=old.environment,
            role=old.role,
            created_by=created_by,
            is_service_principal=old.is_service_principal,
            session_cap=old.session_cap,
        )
        new_row.rotated_from_id = old.id
        old.rotation_grace_until = datetime.now(UTC) + timedelta(minutes=grace_minutes)
        await self.session.flush()
        return new_row, minted

    async def resolve_api_key(self, plaintext: str, *, ip: str = "") -> Principal:
        """Verify a key and resolve its principal.

        Hot path: the resolved principal is cached in Redis for 60 seconds
        (section 33), so a PostgreSQL round trip is not paid on every request.
        Verification itself is HMAC-SHA256 plus ``compare_digest`` - constant
        time and sub-millisecond.
        """
        parsed = parse_api_key(plaintext)
        if parsed is None:
            raise InvalidApiKeyError("Malformed API key.")

        key_hash = hash_api_key(parsed.plaintext)
        cached = await get_cached_principal(key_hash)
        if cached:
            return Principal(
                id=cached["id"],
                type=cached["type"],
                org_id=cached["org_id"],
                project_id=cached.get("project_id"),
                role=cached["role"],
                display=cached.get("display", ""),
                api_key_id=cached.get("api_key_id"),
                key_environment=cached.get("key_environment"),
                session_cap=cached.get("session_cap"),
                permissions=await self._permissions_for(cached["org_id"], cached["role"]),
            )

        # The project prefix is plaintext and uniquely indexed, so this is an
        # indexed lookup rather than a scan over every key in the system.
        row = await self.session.scalar(
            select(ApiKey).where(
                ApiKey.project_prefix == parsed.project_prefix,
                ApiKey.environment == parsed.environment,
                ApiKey.key_hash == key_hash,
            )
        )
        if row is None or not verify_api_key(parsed.plaintext, row.key_hash):
            raise InvalidApiKeyError()

        now = datetime.now(UTC)
        if row.revoked_at is not None and (
            row.rotation_grace_until is None or row.rotation_grace_until < now
        ):
            raise InvalidApiKeyError("This API key has been revoked.")
        if row.expires_at is not None and row.expires_at < now:
            raise InvalidApiKeyError("This API key has expired.")

        row.last_used_at = now
        row.last_used_ip = ip[:64]
        row.use_count += 1

        principal = Principal(
            id=row.id,
            type="service" if row.is_service_principal else "api_key",
            org_id=row.org_id,
            project_id=row.project_id,
            role=row.role,
            display=row.display,
            api_key_id=row.id,
            key_environment=row.environment,
            session_cap=row.session_cap,
            permissions=await self._permissions_for(row.org_id, row.role),
        )
        await cache_principal(key_hash, principal.as_dict())
        return principal

    async def _permissions_for(self, org_id: str, role: str) -> frozenset[Permission]:
        """Permissions for a role name, built-in or custom.

        A custom role's set lives in the database, so this is the one place
        that has to look. A name matching neither resolves to nothing: a holder
        of a deleted role keeps their identity and loses their authority,
        rather than falling back to someone else's.
        """
        if is_builtin_role(role):
            return permissions_for(role)

        from app.services.roles.service import RoleService

        return await RoleService(self.session, org_id).resolve(role)

    # ------------------------------------------------- service sessions (35)
    async def open_service_session(
        self,
        principal: Principal,
        *,
        external_ref: str | None = None,
    ) -> ServicePrincipalSession:
        """Resolve or open the session identity a machine request runs under."""
        if principal.api_key_id is None or principal.project_id is None:
            raise InvalidApiKeyError("A service session requires a project-scoped API key.")

        if external_ref:
            existing = await self.session.scalar(
                select(ServicePrincipalSession).where(
                    ServicePrincipalSession.api_key_id == principal.api_key_id,
                    ServicePrincipalSession.external_session_ref == external_ref,
                    ServicePrincipalSession.closed_at.is_(None),
                )
            )
            if existing is not None:
                self._assert_session_cap(existing)
                return existing

        row = ServicePrincipalSession(
            org_id=principal.org_id,
            project_id=principal.project_id,
            api_key_id=principal.api_key_id,
            external_session_ref=external_ref,
            session_cap=principal.session_cap,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    @staticmethod
    def _assert_session_cap(row: ServicePrincipalSession) -> None:
        if row.session_cap is not None and row.credits_used >= row.session_cap:
            raise SessionCapExceededError(
                "This service session has used "
                + str(row.credits_used)
                + " of its "
                + str(row.session_cap)
                + "-credit cap.",
                details={"session_id": row.id, "session_cap": row.session_cap},
            )

    # ---------------------------------------------------------- membership
    async def resolve_user_principal(
        self, user_id: str, *, org_id: str | None = None, project_id: str | None = None
    ) -> Principal:
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise InvalidCredentialsError()

        query = select(Membership).where(Membership.user_id == user_id)
        if org_id:
            query = query.where(Membership.org_id == org_id)
        membership = await self.session.scalar(query)
        if membership is None:
            raise InvalidCredentialsError("This user is not a member of any organization.")

        role = membership.role
        if project_id:
            override = await self.session.scalar(
                select(ProjectMember).where(
                    ProjectMember.user_id == user_id, ProjectMember.project_id == project_id
                )
            )
            if override is not None:
                role = override.role

        return Principal(
            id=user.id,
            type="user",
            org_id=membership.org_id,
            project_id=project_id,
            role=role,
            email=user.email,
            display=user.full_name or user.email,
            permissions=await self._permissions_for(membership.org_id, role),
        )

    async def create_project(
        self,
        *,
        org_id: str,
        name: str,
        slug: str | None = None,
        description: str = "",
    ) -> Project:
        import re

        base = slug or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "project"
        candidate = base
        suffix = 1
        while await self.session.scalar(
            select(Project).where(Project.org_id == org_id, Project.slug == candidate)
        ):
            suffix += 1
            candidate = base + "-" + str(suffix)

        prefix = generate_project_prefix()
        while await self.session.scalar(select(Project).where(Project.key_prefix == prefix)):
            prefix = generate_project_prefix()

        project = Project(
            org_id=org_id,
            name=name,
            slug=candidate,
            description=description,
            key_prefix=prefix,
        )
        self.session.add(project)
        await self.session.flush()
        return project


def can(principal: Principal, permission: Permission) -> bool:
    return has_permission(principal.role, permission)


__all__ = ["AuthService", "Principal", "can"]
