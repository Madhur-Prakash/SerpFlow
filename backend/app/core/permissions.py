"""Centralised authorization (section 34).

Deny by default. Permission checks live here and are applied by the
``require`` dependency in ``app/api/deps.py`` - never scattered through
business logic.

The analyst role deserves a note: planning calls an LLM, not SerpApi, so a dry
run consumes zero credits. Analysts can therefore plan but not execute, which
is exactly what makes the role useful.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.exceptions import PermissionDeniedError


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    ANALYST = "analyst"
    SERVICE = "service"


class Permission(StrEnum):
    # organization
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    ORG_DELETE = "org:delete"
    ORG_BILLING = "org:billing"

    # members
    MEMBER_READ = "member:read"
    MEMBER_WRITE = "member:write"

    # projects
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"

    # api keys
    KEY_READ = "key:read"
    KEY_WRITE = "key:write"
    KEY_PROJECT_WRITE = "key:project_write"

    # upstream credentials
    CREDENTIAL_READ = "credential:read"
    CREDENTIAL_WRITE = "credential:write"
    CREDENTIAL_ROTATE = "credential:rotate"

    # budgets and policy
    BUDGET_READ = "budget:read"
    BUDGET_WRITE = "budget:write"
    POLICY_WRITE = "policy:write"

    # planning and execution
    PLAN_CREATE = "plan:create"
    EXECUTE = "run:execute"
    RUN_READ = "run:read"
    RUN_REPLAY = "run:replay"
    PAYLOAD_READ = "payload:read"

    # cache
    CACHE_READ = "cache:read"
    CACHE_INVALIDATE = "cache:invalidate"

    # analytics, benchmarks, audit, alerts
    ANALYTICS_READ = "analytics:read"
    BENCHMARK_READ = "benchmark:read"
    BENCHMARK_RUN = "benchmark:run"
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    ALERT_READ = "alert:read"
    ALERT_WRITE = "alert:write"
    CATALOG_READ = "catalog:read"

    # custom roles
    ROLE_READ = "role:read"
    ROLE_WRITE = "role:write"


_ANALYST: frozenset[Permission] = frozenset(
    {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.RUN_READ,
        # Planning is a dry run: it calls the LLM, not SerpApi, and spends nothing.
        Permission.PLAN_CREATE,
        Permission.BUDGET_READ,
        Permission.CACHE_READ,
        Permission.ANALYTICS_READ,
        Permission.BENCHMARK_READ,
        Permission.CATALOG_READ,
        Permission.ALERT_READ,
        Permission.KEY_READ,
    }
)

_DEVELOPER: frozenset[Permission] = _ANALYST | frozenset(
    {
        Permission.EXECUTE,
        Permission.RUN_REPLAY,
        Permission.PAYLOAD_READ,
        Permission.KEY_PROJECT_WRITE,
        Permission.CACHE_INVALIDATE,
        Permission.CREDENTIAL_READ,
        Permission.BENCHMARK_RUN,
    }
)

_SERVICE: frozenset[Permission] = frozenset(
    {
        Permission.PLAN_CREATE,
        Permission.EXECUTE,
        Permission.RUN_READ,
        Permission.PAYLOAD_READ,
        Permission.CATALOG_READ,
        Permission.BUDGET_READ,
        Permission.CACHE_READ,
    }
)

_ADMIN: frozenset[Permission] = _DEVELOPER | frozenset(
    {
        Permission.MEMBER_READ,
        Permission.MEMBER_WRITE,
        Permission.ROLE_READ,
        Permission.PROJECT_WRITE,
        Permission.BUDGET_WRITE,
        Permission.POLICY_WRITE,
        Permission.KEY_WRITE,
        Permission.AUDIT_READ,
        Permission.AUDIT_EXPORT,
        Permission.ALERT_WRITE,
        Permission.ORG_UPDATE,
        Permission.CREDENTIAL_WRITE,
    }
)

_OWNER: frozenset[Permission] = _ADMIN | frozenset(
    {
        Permission.ORG_BILLING,
        Permission.ORG_DELETE,
        Permission.CREDENTIAL_ROTATE,
        # Defining a role is defining authority, so it stays with the owner.
        Permission.ROLE_WRITE,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _OWNER,
    Role.ADMIN: _ADMIN,
    Role.DEVELOPER: _DEVELOPER,
    Role.ANALYST: _ANALYST,
    Role.SERVICE: _SERVICE,
}

ROLE_ORDER: dict[Role, int] = {
    Role.SERVICE: 0,
    Role.ANALYST: 1,
    Role.DEVELOPER: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}


def permissions_for(role: Role | str) -> frozenset[Permission]:
    """The permission set for a built-in role.

    A name that is not a built-in role returns the empty set, not a guess. A
    custom role's permissions live in the database and are resolved by
    ``AuthService``; this function stays pure so it can be used anywhere.
    """
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except (ValueError, KeyError):
        return frozenset()


def is_builtin_role(role: str) -> bool:
    try:
        Role(role)
    except ValueError:
        return False
    return True


def parse_permissions(values: list[str] | None) -> frozenset[Permission]:
    """Turn stored strings into permissions, dropping anything unrecognised.

    Dropping rather than raising matters: if a permission is removed from the
    enum, a stored role that still names it must lose that grant, not fail to
    load and not keep it.
    """
    known: set[Permission] = set()
    for value in values or []:
        try:
            known.add(Permission(value))
        except ValueError:
            continue
    return frozenset(known)


#: Grouped for the interface that builds a custom role. The grouping is
#: presentation; the permission strings are the contract.
PERMISSION_GROUPS: list[tuple[str, tuple[Permission, ...]]] = [
    (
        "Organization",
        (Permission.ORG_READ, Permission.ORG_UPDATE, Permission.ORG_BILLING, Permission.ORG_DELETE),
    ),
    ("Members", (Permission.MEMBER_READ, Permission.MEMBER_WRITE)),
    ("Projects", (Permission.PROJECT_READ, Permission.PROJECT_WRITE, Permission.POLICY_WRITE)),
    ("API keys", (Permission.KEY_READ, Permission.KEY_WRITE, Permission.KEY_PROJECT_WRITE)),
    (
        "Credentials",
        (Permission.CREDENTIAL_READ, Permission.CREDENTIAL_WRITE, Permission.CREDENTIAL_ROTATE),
    ),
    ("Budgets", (Permission.BUDGET_READ, Permission.BUDGET_WRITE)),
    (
        "Search and runs",
        (
            Permission.PLAN_CREATE,
            Permission.EXECUTE,
            Permission.RUN_READ,
            Permission.RUN_REPLAY,
            Permission.PAYLOAD_READ,
        ),
    ),
    ("Cache", (Permission.CACHE_READ, Permission.CACHE_INVALIDATE)),
    ("Catalog", (Permission.CATALOG_READ,)),
    (
        "Evidence",
        (
            Permission.ANALYTICS_READ,
            Permission.BENCHMARK_READ,
            Permission.BENCHMARK_RUN,
            Permission.AUDIT_READ,
            Permission.AUDIT_EXPORT,
        ),
    ),
    ("Alerts", (Permission.ALERT_READ, Permission.ALERT_WRITE)),
    ("Roles", (Permission.ROLE_READ, Permission.ROLE_WRITE)),
]

#: One line per permission, for the picker. A checkbox labelled "payload:read"
#: tells an owner nothing about what they are granting.
PERMISSION_HELP: dict[Permission, str] = {
    Permission.ORG_READ: "See organization settings",
    Permission.ORG_UPDATE: "Change organization settings",
    Permission.ORG_BILLING: "See and change billing",
    Permission.ORG_DELETE: "Delete the organization",
    Permission.MEMBER_READ: "See who is in the organization",
    Permission.MEMBER_WRITE: "Invite, change and remove members",
    Permission.PROJECT_READ: "See projects",
    Permission.PROJECT_WRITE: "Create and change projects",
    Permission.POLICY_WRITE: "Change engine policy and cache settings",
    Permission.KEY_READ: "See API keys (never their secrets)",
    Permission.KEY_WRITE: "Create, rotate and revoke any API key",
    Permission.KEY_PROJECT_WRITE: "Create keys within their own project",
    Permission.CREDENTIAL_READ: "See which SerpApi credentials exist",
    Permission.CREDENTIAL_WRITE: "Attach and remove SerpApi credentials",
    Permission.CREDENTIAL_ROTATE: "Rotate a SerpApi credential",
    Permission.BUDGET_READ: "See budgets and remaining quota",
    Permission.BUDGET_WRITE: "Set and change budgets",
    Permission.PLAN_CREATE: "Plan a search without executing it (spends nothing)",
    Permission.EXECUTE: "Execute searches (spends credits)",
    Permission.RUN_READ: "See run history and how each plan was chosen",
    Permission.RUN_REPLAY: "Replay a previous run",
    Permission.PAYLOAD_READ: "Read raw result payloads, which can contain personal data",
    Permission.CACHE_READ: "See cache contents and hit rates",
    Permission.CACHE_INVALIDATE: "Invalidate cached entries",
    Permission.CATALOG_READ: "Browse the engine catalog",
    Permission.ANALYTICS_READ: "See spend, savings and attribution",
    Permission.BENCHMARK_READ: "See benchmark results",
    Permission.BENCHMARK_RUN: "Run the benchmark (makes real model calls)",
    Permission.AUDIT_READ: "Read the audit log",
    Permission.AUDIT_EXPORT: "Export the audit log",
    Permission.ALERT_READ: "See alerts",
    Permission.ALERT_WRITE: "Acknowledge alerts and manage channels",
    Permission.ROLE_READ: "See the roles defined in this organization",
    Permission.ROLE_WRITE: "Define, change and delete custom roles",
}


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in permissions_for(role)


def require_permission(role: Role | str, permission: Permission) -> None:
    """Deny by default. Raises rather than returning False so no call site can
    forget to branch on the result."""
    if not has_permission(role, permission):
        raise PermissionDeniedError(
            "Role " + str(role) + " is not permitted to perform " + str(permission) + ".",
            details={"role": str(role), "required_permission": str(permission)},
        )


def role_at_least(role: Role | str, minimum: Role) -> bool:
    try:
        return ROLE_ORDER[Role(role)] >= ROLE_ORDER[minimum]
    except (ValueError, KeyError):
        return False


def describe_role(role: Role | str) -> dict[str, object]:
    r = Role(role)
    return {
        "role": str(r),
        "permissions": sorted(str(p) for p in permissions_for(r)),
        "can_execute": has_permission(r, Permission.EXECUTE),
        "can_plan": has_permission(r, Permission.PLAN_CREATE),
        "can_read_payloads": has_permission(r, Permission.PAYLOAD_READ),
    }


__all__ = [
    "ROLE_ORDER",
    "ROLE_PERMISSIONS",
    "Permission",
    "Role",
    "describe_role",
    "has_permission",
    "permissions_for",
    "require_permission",
    "role_at_least",
]
