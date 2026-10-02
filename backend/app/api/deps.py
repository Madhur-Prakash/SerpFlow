"""Request dependencies: principal resolution, tenant guard, authorization.

Section 34 requires centralised authorization. ``require(Permission.X)`` is the
only way a route asserts a permission - no business-logic module performs its
own check, and the default is deny.

Section 36 requires every query to be scoped to ``org_id``. The tenant guard
below sets ``app.current_org`` for the transaction, so PostgreSQL RLS applies
as a backstop underneath the application-level checks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
)
from app.core.logging import bind
from app.core.permissions import Permission
from app.core.security import decode_token
from app.db.models.identity import Organization, Project
from app.db.session import get_sessionmaker, set_tenant
from app.services.auth.service import AuthService, Principal
from app.services.cache.redis_client import incr_rate


async def get_session() -> AsyncIterator[AsyncSession]:
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def client_ip(request: Request) -> str:
    """The caller's address, counted back from the right of X-Forwarded-For.

    The whole header is client-supplied except for the entries our own proxies
    appended. Taking the *leftmost* entry - the common shortcut - means anyone
    can set ``X-Forwarded-For: 1.2.3.4`` and get a fresh rate-limit bucket on
    every request, and audit entries that name whoever they like.

    So ``TRUSTED_PROXY_HOPS`` says how many proxies in front of the API append
    to the header, and the address is read that many entries from the right.
    With the bundled nginx that is 1. With the API exposed directly it is 0,
    and the header is ignored entirely in favour of the socket peer.
    """
    peer = request.client.host if request.client else ""
    hops = settings.trusted_proxy_hops
    if hops <= 0:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    entries = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not entries:
        return peer
    # Fewer entries than configured hops means the header did not traverse the
    # proxies it was supposed to. The leftmost is then the most trustworthy
    # value available, and it is still not trusted enough to prefer over peer
    # when the count is short.
    if len(entries) < hops:
        return peer
    return entries[-hops]


async def get_principal(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    access_token: Annotated[str | None, Query()] = None,
) -> Principal:
    """Resolve the caller.

    Credential shapes, in precedence order:
      1. ``X-API-Key`` (or ``Authorization: Bearer sf_...``) - an API key
      2. ``Authorization: Bearer <jwt>`` - a human session
      3. ``?access_token=`` - the browser EventSource API cannot set headers,
         so the SSE endpoint accepts a short-lived access token as a query
         parameter. It is never accepted in place of an API key, and the
         refresh token is never accepted this way at all.

    Once resolved, the transaction is scoped to the principal's organization so
    RLS applies for every subsequent query on this request.
    """
    auth = AuthService(session)
    ip = client_ip(request)
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif access_token and not access_token.startswith("sf_"):
        token = access_token.strip()

    api_key = x_api_key or (token if token and token.startswith("sf_") else None)

    if api_key:
        principal = await auth.resolve_api_key(api_key, ip=ip)
    elif token:
        try:
            payload = decode_token(token, "access")
        except Exception as exc:
            raise AuthenticationError("The access token is invalid or expired.") from exc
        project_id = request.headers.get("x-serpflow-project") or request.query_params.get(
            "project_id"
        )
        principal = await auth.resolve_user_principal(
            payload["sub"], org_id=payload.get("org_id"), project_id=project_id
        )
    else:
        raise AuthenticationError(
            "Supply an API key in X-API-Key, or an access token in Authorization: Bearer."
        )

    await set_tenant(session, principal.org_id)
    bind(
        org_id=principal.org_id,
        project_id=principal.project_id,
        principal_id=principal.id,
    )
    request.state.principal = principal
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require(*permissions: Permission):
    """Authorization dependency. Deny by default."""

    async def _dependency(principal: PrincipalDep) -> Principal:
        for permission in permissions:
            if not principal.can(permission):
                raise PermissionDeniedError(
                    "Role " + principal.role + " is not permitted to " + str(permission) + ".",
                    details={
                        "role": principal.role,
                        "required_permission": str(permission),
                        "principal_type": principal.type,
                    },
                )
        return principal

    return _dependency


async def get_organization(principal: PrincipalDep, session: SessionDep) -> Organization:
    org = await session.get(Organization, principal.org_id)
    if org is None:
        raise NotFoundError("Organization not found.")
    return org


OrganizationDep = Annotated[Organization, Depends(get_organization)]


async def get_project(
    principal: PrincipalDep,
    session: SessionDep,
    project_id: Annotated[str | None, Query()] = None,
    x_serpflow_project: Annotated[str | None, Header(alias="X-SerpFlow-Project")] = None,
) -> Project:
    """Resolve the active project and assert it belongs to the caller's org."""
    target = project_id or x_serpflow_project or principal.project_id
    if target:
        project = await session.get(Project, target)
        if project is None:
            raise NotFoundError("Project not found.")
        if project.org_id != principal.org_id:
            # Cross-tenant access is reported as a 404, not a 403: confirming
            # that an id exists in another organization is itself a leak.
            raise NotFoundError("Project not found.")
        return project

    project = await session.scalar(
        select(Project).where(Project.org_id == principal.org_id).order_by(Project.created_at.asc())
    )
    if project is None:
        raise NotFoundError("This organization has no projects yet.")
    return project


ProjectDep = Annotated[Project, Depends(get_project)]


async def rate_limit(request: Request, principal: PrincipalDep) -> None:
    """Per-principal rate limit (section 67). Fails open if Redis is down."""

    bucket = principal.id + ":" + request.url.path
    count = await incr_rate(bucket, 60)
    if count > settings.rate_limit_per_minute:
        raise RateLimitedError(
            "Rate limit of "
            + str(settings.rate_limit_per_minute)
            + " requests per minute exceeded for this principal.",
            details={"limit": settings.rate_limit_per_minute, "window_seconds": 60},
        )


RateLimited = Annotated[None, Depends(rate_limit)]


def pagination(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> tuple[int, int]:
    return limit, offset


PaginationDep = Annotated[tuple[int, int], Depends(pagination)]


__all__ = [
    "OrganizationDep",
    "PaginationDep",
    "PrincipalDep",
    "ProjectDep",
    "RateLimited",
    "SessionDep",
    "client_ip",
    "get_organization",
    "get_principal",
    "get_project",
    "get_session",
    "pagination",
    "rate_limit",
    "require",
]
