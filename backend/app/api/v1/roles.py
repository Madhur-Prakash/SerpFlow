"""Custom roles (section 34).

An owner defines a role and the permissions it carries; members and API keys
are then assigned it by slug alongside the five built-in roles.

Writing a role is defining authority, so `ROLE_WRITE` belongs to the owner
alone. Reading the catalogue of roles is an admin concern, because that is who
assigns them.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import Field

from app.api.deps import SessionDep, client_ip, require
from app.core.permissions import (
    PERMISSION_GROUPS,
    PERMISSION_HELP,
    ROLE_PERMISSIONS,
    Permission,
    Role,
)
from app.schemas.common import APIModel, OkResponse
from app.services.audit.service import AuditService
from app.services.auth.service import Principal
from app.services.roles.service import RoleService

router = APIRouter(prefix="/roles", tags=["organizations"])


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class CustomRoleCreate(APIModel):
    name: str = Field(min_length=1, max_length=80)
    permissions: list[str] = Field(default_factory=list)
    description: str = ""
    #: Optional. Derived from the name when absent, and never changes after.
    slug: str | None = None


class CustomRoleUpdate(APIModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class PermissionView(APIModel):
    value: str
    label: str
    group: str


class RoleCatalogue(APIModel):
    """Everything the interface needs to build a role picker."""

    permissions: list[PermissionView]
    groups: list[str]
    builtin: list[dict[str, Any]]


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@router.get("/permissions", response_model=RoleCatalogue)
async def list_permissions(
    _: Annotated[Principal, Depends(require(Permission.ROLE_READ))],
) -> RoleCatalogue:
    """Every permission, grouped and described.

    The description matters: a checkbox labelled `payload:read` tells an owner
    nothing about what they are about to grant.
    """
    permissions = [
        PermissionView(
            value=permission.value,
            label=PERMISSION_HELP.get(permission, permission.value),
            group=group,
        )
        for group, members in PERMISSION_GROUPS
        for permission in members
    ]
    return RoleCatalogue(
        permissions=permissions,
        groups=[group for group, _ in PERMISSION_GROUPS],
        # The built-ins are shown beside the custom ones so an owner can see
        # what already exists before inventing something close to it.
        builtin=[
            {
                "slug": role.value,
                "name": role.value.capitalize(),
                "permissions": sorted(p.value for p in ROLE_PERMISSIONS[role]),
                "builtin": True,
            }
            for role in Role
        ],
    )


@router.get("")
async def list_roles(
    principal: Annotated[Principal, Depends(require(Permission.ROLE_READ))],
    session: SessionDep,
) -> dict[str, Any]:
    service = RoleService(session, principal.org_id)
    roles = await service.list_roles()
    return {"items": [await service.view(role) for role in roles], "total": len(roles)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: CustomRoleCreate,
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.ROLE_WRITE))],
    session: SessionDep,
) -> dict[str, Any]:
    service = RoleService(session, principal.org_id)
    role = await service.create(
        name=payload.name,
        permissions=payload.permissions,
        description=payload.description,
        slug=payload.slug,
        created_by=principal.id,
    )
    # Built before the audit write: recording flushes, which expires the row's
    # attributes, and reading them back afterwards needs a round trip.
    view = await service.view(role)
    await AuditService(session, org_id=principal.org_id).record(
        action="role.created",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="role",
        resource_id=role.id,
        after={"slug": role.slug, "permissions": list(role.permissions)},
        ip=client_ip(request),
    )
    return view


@router.patch("/{role_id}")
async def update_role(
    role_id: str,
    payload: CustomRoleUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.ROLE_WRITE))],
    session: SessionDep,
) -> dict[str, Any]:
    service = RoleService(session, principal.org_id)
    before = await service.get(role_id)
    previous = {"name": before.name, "permissions": list(before.permissions)}

    role = await service.update(
        role_id,
        name=payload.name,
        description=payload.description,
        permissions=payload.permissions,
    )
    view = await service.view(role)
    await AuditService(session, org_id=principal.org_id).record(
        action="role.updated",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="role",
        resource_id=role.id,
        before=previous,
        after={"name": role.name, "permissions": list(role.permissions)},
        ip=client_ip(request),
    )
    return view


@router.delete("/{role_id}", response_model=OkResponse)
async def delete_role(
    role_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.ROLE_WRITE))],
    session: SessionDep,
) -> OkResponse:
    service = RoleService(session, principal.org_id)
    role = await service.get(role_id)
    snapshot = {"slug": role.slug, "permissions": list(role.permissions)}

    await service.delete(role_id)
    await AuditService(session, org_id=principal.org_id).record(
        action="role.deleted",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="role",
        resource_id=role_id,
        before=snapshot,
        ip=client_ip(request),
    )
    return OkResponse(message="Role deleted.")


__all__ = ["router"]
