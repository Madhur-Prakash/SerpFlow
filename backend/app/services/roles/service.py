"""Custom roles.

The five built-in roles cover the shapes most organizations need. This is for
the ones they do not: an owner names a role and picks its permissions, and a
member or an API key can then be assigned it by slug.

Two rules hold the design together:

**A custom role can never exceed the owner's own authority.** Permissions are
validated against the enum, so a role cannot name a capability the system does
not have; and because only an owner may write roles, there is no path by which
a lesser role defines a greater one.

**Unknown permissions are dropped, not granted.** A role that still names a
permission removed from the enum loses that grant on the next read rather than
failing to load or keeping it. See ``parse_permissions``.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import (
    Permission,
    Role,
    is_builtin_role,
    parse_permissions,
)
from app.db.models.identity import CustomRole, Membership
from app.db.models.keys import ApiKey

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return slug.strip("-")


class RoleService:
    def __init__(self, session: AsyncSession, org_id: str) -> None:
        self.session = session
        self.org_id = org_id

    # ----------------------------------------------------------------- read
    async def list_roles(self) -> list[CustomRole]:
        rows = await self.session.scalars(
            select(CustomRole)
            .where(CustomRole.org_id == self.org_id)
            .order_by(CustomRole.name.asc())
        )
        return list(rows.all())

    async def get(self, role_id: str) -> CustomRole:
        role = await self.session.get(CustomRole, role_id)
        # Cross-tenant reads answer 404, never 403: confirming that an id
        # exists in another organization is itself a leak.
        if role is None or role.org_id != self.org_id:
            raise NotFoundError("That role does not exist.")
        return role

    async def by_slug(self, slug: str) -> CustomRole | None:
        return await self.session.scalar(
            select(CustomRole).where(CustomRole.org_id == self.org_id, CustomRole.slug == slug)
        )

    # ---------------------------------------------------------------- write
    def _validate(self, name: str, permissions: list[str], slug: str) -> frozenset[Permission]:
        if not name.strip():
            raise ValidationError("A role needs a name.")
        if not SLUG_PATTERN.match(slug):
            raise ValidationError(
                "A role's identifier must be 3 to 40 characters of lowercase letters, "
                "numbers and hyphens."
            )
        if is_builtin_role(slug):
            raise ValidationError(
                "'" + slug + "' is a built-in role. Choose another name for a custom one."
            )

        resolved = parse_permissions(permissions)
        unknown = sorted(set(permissions or []) - {p.value for p in resolved})
        if unknown:
            raise ValidationError("Unknown permissions: " + ", ".join(unknown))
        if not resolved:
            raise ValidationError("A role needs at least one permission.")
        return resolved

    async def create(
        self,
        *,
        name: str,
        permissions: list[str],
        description: str = "",
        slug: str | None = None,
        created_by: str | None = None,
    ) -> CustomRole:
        candidate = (slug or slugify(name)).strip()
        resolved = self._validate(name, permissions, candidate)

        if await self.by_slug(candidate) is not None:
            raise ConflictError("A role with the identifier '" + candidate + "' already exists.")

        role = CustomRole(
            org_id=self.org_id,
            name=name.strip(),
            slug=candidate,
            description=description.strip()[:300],
            permissions=sorted(p.value for p in resolved),
            created_by=created_by,
        )
        self.session.add(role)
        await self.session.flush()
        return role

    async def update(
        self,
        role_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> CustomRole:
        role = await self.get(role_id)

        next_name = name.strip() if name is not None else role.name
        next_permissions = permissions if permissions is not None else list(role.permissions)
        # The slug is the identity a membership stores, so it does not move
        # when the display name changes - renaming a role must not silently
        # strip everyone who holds it.
        resolved = self._validate(next_name, next_permissions, role.slug)

        role.name = next_name
        if description is not None:
            role.description = description.strip()[:300]
        role.permissions = sorted(p.value for p in resolved)
        await self.session.flush()
        # `updated_at` carries an onupdate, so the flush leaves it expired and
        # the next read of it would be a lazy refresh - which fails outside the
        # async context. Refresh here, where awaiting is legal.
        await self.session.refresh(role)
        return role

    async def delete(self, role_id: str) -> int:
        """Remove a role. Refuses while anything still holds it."""
        role = await self.get(role_id)
        assigned = await self.assignment_count(role.slug)
        if assigned:
            raise ConflictError(
                "That role is assigned to "
                + str(assigned)
                + (" member or key." if assigned == 1 else " members or keys.")
                + " Move them to another role first."
            )
        await self.session.delete(role)
        await self.session.flush()
        return assigned

    async def assignment_count(self, slug: str) -> int:
        members = await self.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.org_id == self.org_id, Membership.role == slug)
        )
        keys = await self.session.scalar(
            select(func.count())
            .select_from(ApiKey)
            .where(ApiKey.org_id == self.org_id, ApiKey.role == slug)
        )
        return int(members or 0) + int(keys or 0)

    # ------------------------------------------------------------ resolving
    async def resolve(self, role: str) -> frozenset[Permission]:
        """Permissions for a role name, built-in or custom.

        Used when a principal is built. A name that matches neither resolves to
        nothing, which is the right answer for a role that has been deleted:
        the holder keeps their identity and loses their authority, rather than
        inheriting someone else's.
        """
        if is_builtin_role(role):
            from app.core.permissions import permissions_for

            return permissions_for(Role(role))

        custom = await self.by_slug(role)
        if custom is None:
            return frozenset()
        return parse_permissions(custom.permissions)

    async def view(self, role: CustomRole) -> dict[str, Any]:
        return {
            "id": role.id,
            "name": role.name,
            "slug": role.slug,
            "description": role.description,
            "permissions": list(role.permissions),
            "assigned_count": await self.assignment_count(role.slug),
            "created_at": role.created_at,
            "updated_at": role.updated_at,
        }


__all__ = ["RoleService", "slugify"]
