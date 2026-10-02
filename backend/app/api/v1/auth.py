"""Authentication routes (section 62)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select

from app.api.deps import PrincipalDep, SessionDep, client_ip, get_session
from app.core.exceptions import InvalidCredentialsError, NotFoundError
from app.core.logging import get_logger
from app.core.security import (
    hash_opaque_token,
    hash_password,
)
from app.db.models.identity import Organization, Project, User
from app.schemas.common import OkResponse
from app.schemas.identity import (
    LoginRequest,
    MeResponse,
    OrganizationResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    ProjectResponse,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.audit.service import AuditService
from app.services.auth.service import AuthService
from app.services.budgets.service import ensure_budget
from app.services.email import (
    EmailSendError,
    RenderedEmail,
    render_password_reset,
    render_verify_email,
    send_rendered,
)

router = APIRouter(prefix="/auth", tags=["auth"])

log = get_logger("serpflow.api.auth")


async def deliver_email(to: str, rendered: RenderedEmail, *, context: str) -> None:
    """Send, and never fail the request because the mail did not go out.

    An account that was created successfully should not come back as a 500
    because Gmail was unreachable, and `forgot-password` deliberately returns
    the same response whether or not the address exists - so raising here would
    turn a delivery failure into an account-enumeration oracle. The failure is
    logged with the cause; the bodies, which carry single-use tokens, are not.
    """
    try:
        await send_rendered(to, rendered)
    except EmailSendError as exc:
        log.warning(
            "email delivery failed",
            extra={
                "event": "email.failed",
                "context": context,
                "to": to,
                "template": rendered.template,
                "error": str(exc),
            },
        )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: Annotated[object, Depends(get_session)],
) -> TokenResponse:
    """Create a user, their organization, a first project and a default budget.

    The default budget is 250 credits, matching the SerpApi free tier, so a new
    account cannot accidentally outspend it on day one.
    """
    auth = AuthService(session)  # type: ignore[arg-type]
    user, org, _membership = await auth.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        org_name=payload.organization_name,
    )
    project = await auth.create_project(
        org_id=org.id, name="Default", description="First project, created at sign-up."
    )
    await ensure_budget(
        session,  # type: ignore[arg-type]
        org_id=org.id,
        scope="organization",
        scope_id=org.id,
        limit_credits=250,
        name="Free tier guard",
    )
    await ensure_budget(
        session,  # type: ignore[arg-type]
        org_id=org.id,
        scope="project",
        scope_id=project.id,
        limit_credits=250,
        name="Default project budget",
    )
    if auth.last_verification_token:
        await deliver_email(
            user.email,
            render_verify_email(user.full_name or user.email, auth.last_verification_token),
            context="verification",
        )
    await AuditService(session, org_id=org.id).record(  # type: ignore[arg-type]
        action="user.registered",
        actor_id=user.id,
        actor_label=user.email,
        resource_type="user",
        resource_id=user.id,
        ip=client_ip(request),
    )
    tokens = await auth.issue_session(
        user, ip=client_ip(request), user_agent=request.headers.get("user-agent", "")
    )
    return TokenResponse.model_validate(tokens)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, session: SessionDep) -> TokenResponse:
    auth = AuthService(session)
    user = await auth.authenticate(payload.email, payload.password)
    tokens = await auth.issue_session(
        user, ip=client_ip(request), user_agent=request.headers.get("user-agent", "")
    )
    await AuditService(session, org_id=tokens["org_id"]).record(
        action="user.login",
        actor_id=user.id,
        actor_label=user.email,
        resource_type="user",
        resource_id=user.id,
        ip=client_ip(request),
    )
    return TokenResponse.model_validate(tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request, session: SessionDep) -> TokenResponse:
    """Refresh rotation: reusing a rotated token is rejected."""
    auth = AuthService(session)
    tokens = await auth.rotate_refresh(payload.refresh_token, ip=client_ip(request))
    return TokenResponse.model_validate(tokens)


@router.post("/logout", response_model=OkResponse)
async def logout(
    principal: PrincipalDep, session: SessionDep, session_id: str | None = None
) -> OkResponse:
    auth = AuthService(session)
    if session_id:
        await auth.revoke_session(session_id, principal.id)
        return OkResponse(message="Session revoked.")
    for row in await auth.list_sessions(principal.id):
        await auth.revoke_session(row.id, principal.id)
    return OkResponse(message="All sessions revoked.")


@router.get("/me", response_model=MeResponse)
async def me(principal: PrincipalDep, session: SessionDep) -> MeResponse:
    user = None
    if principal.type == "user":
        row = await session.get(User, principal.id)
        user = UserResponse.model_validate(row) if row else None

    org = await session.get(Organization, principal.org_id)
    projects = (
        await session.scalars(
            select(Project)
            .where(Project.org_id == principal.org_id)
            .order_by(Project.created_at.asc())
        )
    ).all()

    return MeResponse(
        user=user,
        principal_type=principal.type,
        org_id=principal.org_id,
        project_id=principal.project_id,
        role=principal.role,  # type: ignore[arg-type]
        permissions=sorted(str(p) for p in principal.permissions),
        organization=OrganizationResponse.model_validate(org) if org else None,
        projects=[ProjectResponse.model_validate(p) for p in projects],
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(principal: PrincipalDep, session: SessionDep) -> list[SessionResponse]:
    rows = await AuthService(session).list_sessions(principal.id)
    return [SessionResponse.model_validate(r) for r in rows]


@router.delete("/sessions/{session_id}", response_model=OkResponse)
async def revoke_session(
    session_id: str, principal: PrincipalDep, session: SessionDep
) -> OkResponse:
    await AuthService(session).revoke_session(session_id, principal.id)
    return OkResponse(message="Session revoked.")


@router.post("/verify-email", response_model=OkResponse)
async def verify_email(payload: VerifyEmailRequest, session: SessionDep) -> OkResponse:
    token_hash = hash_opaque_token(payload.token)
    user = await session.scalar(
        select(User).where(User.email_verification_token_hash == token_hash)
    )
    if user is None:
        raise NotFoundError("That verification link is invalid or already used.")
    user.email_verified = True
    user.email_verification_token_hash = None
    return OkResponse(message="Email verified.")


@router.post("/forgot-password", response_model=OkResponse)
async def forgot_password(payload: PasswordResetRequest, session: SessionDep) -> OkResponse:
    issued = await AuthService(session).issue_password_reset(payload.email)
    if issued is not None:
        user, token = issued
        await deliver_email(
            user.email,
            render_password_reset(user.full_name or user.email, token),
            context="password reset",
        )
    # Always the same response, and the same work either way as far as the
    # caller can tell: whether an address is registered is not something an
    # unauthenticated caller gets to learn.
    return OkResponse(message="If that address has an account, a reset link has been sent.")


@router.post("/reset-password", response_model=OkResponse)
async def reset_password(payload: PasswordResetConfirm, session: SessionDep) -> OkResponse:
    from datetime import UTC, datetime

    token_hash = hash_opaque_token(payload.token)
    user = await session.scalar(select(User).where(User.password_reset_token_hash == token_hash))
    if user is None or (
        user.password_reset_expires_at and user.password_reset_expires_at < datetime.now(UTC)
    ):
        raise InvalidCredentialsError("That reset link is invalid or has expired.")
    user.password_hash = hash_password(payload.password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    # Every existing session dies with the old password.
    for row in await AuthService(session).list_sessions(user.id):
        row.revoked_at = datetime.now(UTC)
    return OkResponse(message="Password updated. All sessions have been revoked.")


__all__ = ["router"]
