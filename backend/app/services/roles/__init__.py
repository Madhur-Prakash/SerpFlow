"""Custom roles: an owner-defined name with a permission set."""

from app.services.roles.service import RoleService, slugify

__all__ = ["RoleService", "slugify"]
