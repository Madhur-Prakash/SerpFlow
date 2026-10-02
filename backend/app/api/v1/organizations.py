"""Organizations, projects, members and API keys."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select

from app.api.deps import (
    OrganizationDep,
    PaginationDep,
    PrincipalDep,
    SessionDep,
    client_ip,
    require,
)
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.permissions import Permission, Role
from app.db.models.identity import Membership, Project, User
from app.db.models.keys import ApiKey
from app.schemas.common import OkResponse, Page
from app.schemas.identity import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    ApiKeyRotate,
    MemberInvite,
    MemberResponse,
    MemberUpdate,
    OrganizationResponse,
    OrganizationUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.audit.service import AuditService
from app.services.auth.service import AuthService, Principal
from app.services.budgets.service import ensure_budget

router = APIRouter(tags=["organizations"])


# --------------------------------------------------------------------------
# organization
# --------------------------------------------------------------------------
@router.get("/organizations/current", response_model=OrganizationResponse)
async def get_current_org(
    org: OrganizationDep,
    principal: Annotated[Principal, Depends(require(Permission.ORG_READ))],
) -> OrganizationResponse:
    return OrganizationResponse.model_validate(org)


@router.patch("/organizations/current", response_model=OrganizationResponse)
async def update_org(
    payload: OrganizationUpdate,
    request: Request,
    org: OrganizationDep,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ORG_UPDATE))],
) -> OrganizationResponse:
    before = {"name": org.name, "cache_scope": org.cache_scope}
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(org, field, value)
    await AuditService(session, org_id=org.id).record(
        action="organization.updated",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="organization",
        resource_id=org.id,
        before=before,
        after=data,
        ip=client_ip(request),
    )
    return OrganizationResponse.model_validate(org)


# --------------------------------------------------------------------------
# projects
# --------------------------------------------------------------------------
@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.PROJECT_READ))],
) -> list[ProjectResponse]:
    rows = (
        await session.scalars(
            select(Project)
            .where(Project.org_id == principal.org_id)
            .order_by(Project.created_at.asc())
        )
    ).all()
    return [ProjectResponse.model_validate(r) for r in rows]


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.PROJECT_WRITE))],
) -> ProjectResponse:
    project = await AuthService(session).create_project(
        org_id=principal.org_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
    )
    await ensure_budget(
        session,
        org_id=principal.org_id,
        scope="project",
        scope_id=project.id,
        limit_credits=250,
        name=payload.name + " budget",
    )
    await AuditService(session, org_id=principal.org_id).record(
        action="project.created",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="project",
        resource_id=project.id,
        after={"name": project.name, "key_prefix": project.key_prefix},
        ip=client_ip(request),
    )
    return ProjectResponse.model_validate(project)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project_detail(
    project_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.PROJECT_READ))],
) -> ProjectResponse:
    project = await session.get(Project, project_id)
    if project is None or project.org_id != principal.org_id:
        raise NotFoundError("Project not found.")
    return ProjectResponse.model_validate(project)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.PROJECT_WRITE))],
) -> ProjectResponse:
    project = await session.get(Project, project_id)
    if project is None or project.org_id != principal.org_id:
        raise NotFoundError("Project not found.")

    data = payload.model_dump(exclude_unset=True)
    before = {k: getattr(project, k) for k in data}

    if data.get("credential_id"):
        from app.db.models.keys import UpstreamCredential

        credential = await session.get(UpstreamCredential, data["credential_id"])
        if credential is None or credential.org_id != principal.org_id:
            raise NotFoundError("Credential not found.")

    for field, value in data.items():
        setattr(project, field, value)

    await AuditService(session, org_id=principal.org_id).record(
        action="project.updated",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="project",
        resource_id=project.id,
        before=before,
        after=data,
        project_id=project.id,
        ip=client_ip(request),
    )
    return ProjectResponse.model_validate(project)


# --------------------------------------------------------------------------
# members
# --------------------------------------------------------------------------
@router.get("/members", response_model=list[MemberResponse])
async def list_members(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.MEMBER_READ))],
) -> list[MemberResponse]:
    rows = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.org_id == principal.org_id)
            .order_by(Membership.created_at.asc())
        )
    ).all()
    return [
        MemberResponse(
            id=membership.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,  # type: ignore[arg-type]
            accepted_at=membership.accepted_at,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post("/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    payload: MemberInvite,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.MEMBER_WRITE))],
) -> MemberResponse:
    """Invite an existing user into this organization."""
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None:
        raise NotFoundError(
            "No SerpFlow account exists for that address. Ask them to register first."
        )
    existing = await session.scalar(
        select(Membership).where(
            Membership.org_id == principal.org_id, Membership.user_id == user.id
        )
    )
    if existing is not None:
        raise ConflictError("That user is already a member of this organization.")

    membership = Membership(
        org_id=principal.org_id,
        user_id=user.id,
        role=payload.role,
        invited_by=principal.id,
        accepted_at=datetime.now(UTC),
    )
    session.add(membership)
    await session.flush()

    await AuditService(session, org_id=principal.org_id).record(
        action="member.invited",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="membership",
        resource_id=membership.id,
        after={"email": user.email, "role": payload.role},
        ip=client_ip(request),
    )
    return MemberResponse(
        id=membership.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,  # type: ignore[arg-type]
        accepted_at=membership.accepted_at,
        created_at=membership.created_at,
    )


@router.patch("/members/{membership_id}", response_model=MemberResponse)
async def update_member(
    membership_id: str,
    payload: MemberUpdate,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.MEMBER_WRITE))],
) -> MemberResponse:
    membership = await session.get(Membership, membership_id)
    if membership is None or membership.org_id != principal.org_id:
        raise NotFoundError("Member not found.")

    # Only an owner may create another owner.
    if payload.role == Role.OWNER and principal.role != Role.OWNER:
        raise PermissionDeniedError("Only an owner can grant the owner role.")
    if membership.role == Role.OWNER and principal.role != Role.OWNER:
        raise PermissionDeniedError("Only an owner can change another owner's role.")
    if membership.role == Role.OWNER and payload.role != Role.OWNER:
        remaining = int(
            await session.scalar(
                select(func.count(Membership.id)).where(
                    Membership.org_id == principal.org_id, Membership.role == Role.OWNER
                )
            )
            or 0
        )
        if remaining <= 1:
            raise ConflictError("An organization must keep at least one owner.")

    before = {"role": membership.role}
    membership.role = payload.role
    user = await session.get(User, membership.user_id)

    await AuditService(session, org_id=principal.org_id).record(
        action="member.role_changed",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="membership",
        resource_id=membership.id,
        before=before,
        after={"role": payload.role},
        ip=client_ip(request),
    )
    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        email=user.email if user else "",
        full_name=user.full_name if user else "",
        role=membership.role,  # type: ignore[arg-type]
        accepted_at=membership.accepted_at,
        created_at=membership.created_at,
    )


@router.delete("/members/{membership_id}", response_model=OkResponse)
async def remove_member(
    membership_id: str,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.MEMBER_WRITE))],
) -> OkResponse:
    membership = await session.get(Membership, membership_id)
    if membership is None or membership.org_id != principal.org_id:
        raise NotFoundError("Member not found.")
    if membership.role == Role.OWNER:
        remaining = int(
            await session.scalar(
                select(func.count(Membership.id)).where(
                    Membership.org_id == principal.org_id, Membership.role == Role.OWNER
                )
            )
            or 0
        )
        if remaining <= 1:
            raise ConflictError("An organization must keep at least one owner.")
    await session.delete(membership)
    await AuditService(session, org_id=principal.org_id).record(
        action="member.removed",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="membership",
        resource_id=membership_id,
        ip=client_ip(request),
    )
    return OkResponse(message="Member removed.")


# --------------------------------------------------------------------------
# API keys
# --------------------------------------------------------------------------
@router.get("/keys", response_model=Page[ApiKeyResponse])
async def list_keys(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.KEY_READ))],
    pagination: PaginationDep,
    project_id: Annotated[str | None, Query()] = None,
) -> Page[ApiKeyResponse]:
    limit, offset = pagination
    query = select(ApiKey).where(ApiKey.org_id == principal.org_id)
    count_query = select(func.count(ApiKey.id)).where(ApiKey.org_id == principal.org_id)
    if project_id:
        query = query.where(ApiKey.project_id == project_id)
        count_query = count_query.where(ApiKey.project_id == project_id)
    total = int(await session.scalar(count_query) or 0)
    rows = (
        await session.scalars(query.order_by(ApiKey.created_at.desc()).limit(limit).offset(offset))
    ).all()
    return Page(
        items=[ApiKeyResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_key(
    project_id: str,
    payload: ApiKeyCreate,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
) -> ApiKeyCreated:
    """Mint a key. The plaintext is returned exactly once and never stored.

    A ``test`` key routes to the deterministic mock and consumes zero SerpApi
    credits, which is how a new user integrates before connecting a paid
    account (section 29).
    """
    if not (principal.can(Permission.KEY_WRITE) or principal.can(Permission.KEY_PROJECT_WRITE)):
        raise PermissionDeniedError("This role may not create API keys.")

    project = await session.get(Project, project_id)
    if project is None or project.org_id != principal.org_id:
        raise NotFoundError("Project not found.")

    # A key may never grant more than its creator holds.
    from app.core.permissions import ROLE_ORDER

    if ROLE_ORDER.get(Role(payload.role), 99) > ROLE_ORDER.get(Role(principal.role), 0):
        raise PermissionDeniedError(
            "You cannot issue a key with a role higher than your own (" + principal.role + ")."
        )

    row, minted = await AuthService(session).create_api_key(
        org_id=principal.org_id,
        project=project,
        name=payload.name,
        environment=payload.environment,
        role=payload.role,
        created_by=principal.id,
        expires_in_days=payload.expires_in_days,
        is_service_principal=payload.is_service_principal,
        session_cap=payload.session_cap,
    )
    if payload.is_service_principal and payload.session_cap:
        await ensure_budget(
            session,
            org_id=principal.org_id,
            scope="api_key",
            scope_id=row.id,
            limit_credits=payload.session_cap,
            name=payload.name + " key budget",
        )

    await AuditService(session, org_id=principal.org_id).record(
        action="api_key.created",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="api_key",
        resource_id=row.id,
        project_id=project.id,
        after={
            "name": row.name,
            "environment": row.environment,
            "role": row.role,
            "display": row.display,
        },
        ip=client_ip(request),
    )
    return ApiKeyCreated(key=ApiKeyResponse.model_validate(row), plaintext=minted.plaintext)


@router.post("/keys/{key_id}/rotate", response_model=ApiKeyCreated)
async def rotate_key(
    key_id: str,
    payload: ApiKeyRotate,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.KEY_WRITE))],
) -> ApiKeyCreated:
    """Issue a replacement. Both keys work during the grace window."""
    row, minted = await AuthService(session).rotate_api_key(
        key_id, principal.org_id, grace_minutes=payload.grace_minutes, created_by=principal.id
    )
    await AuditService(session, org_id=principal.org_id).record(
        action="api_key.rotated",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="api_key",
        resource_id=row.id,
        after={"rotated_from": key_id, "grace_minutes": payload.grace_minutes},
        ip=client_ip(request),
    )
    return ApiKeyCreated(key=ApiKeyResponse.model_validate(row), plaintext=minted.plaintext)


@router.delete("/keys/{key_id}", response_model=OkResponse)
async def revoke_key(
    key_id: str,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.KEY_WRITE))],
    reason: Annotated[str, Query(max_length=200)] = "",
) -> OkResponse:
    row = await AuthService(session).revoke_api_key(key_id, principal.org_id, reason=reason)
    await AuditService(session, org_id=principal.org_id).record(
        action="api_key.revoked",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="api_key",
        resource_id=row.id,
        after={"reason": reason},
        ip=client_ip(request),
    )
    return OkResponse(message="API key revoked. The principal cache was invalidated immediately.")


__all__ = ["router"]
