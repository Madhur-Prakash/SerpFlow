# 0011. Tenant isolation enforced twice

**Status** Accepted

## Context

A multi-tenant system has to prevent one organization reading another's data.
There are two standard approaches and they are usually presented as
alternatives:

- **Application-level scoping.** Every query filters by `org_id`. Fast,
  explicit, visible in the code, and it fails the moment somebody writes a
  query that forgets.
- **PostgreSQL row-level security.** The database enforces it regardless of the
  query. Cannot be forgotten, and is invisible at the call site, which makes
  debugging a surprising empty result set unpleasant.

Each covers the other's failure mode.

## Decision

Both.

**Application guards are primary.** Every resource fetched by id is checked
against the caller's `org_id`:

```python
project = await session.get(Project, target)
if project is None or project.org_id != principal.org_id:
    # Cross-tenant access returns 404, not 403. Confirming that an id
    # exists in another organization is itself a leak.
    raise NotFoundError("Project not found.")
```

**RLS is the backstop.** 23 tables carry a policy reading
`current_setting('app.current_org')`, which the session sets per transaction
with `SET LOCAL` right after the principal resolves.

Three supporting rules:

- Cross-tenant access returns `404`, never `403`.
- `SET LOCAL` is transaction-scoped, so a pooled connection never carries one
  request's tenant into the next — and it still works through PgBouncer in
  transaction mode, which a session-level `SET` would not.
- Authorization is centralised in `require(Permission.X)`; no business-logic
  module performs its own check, and `can()` denies by default.

## Alternatives rejected

**Application scoping alone.** One forgotten `WHERE` clause is a cross-tenant
leak, in a codebase with hundreds of queries.

**RLS alone.** Every missing filter becomes an empty result set at runtime
instead of a visible bug, and the application has no idea why. It also makes
the isolation invisible to anyone reading the service layer, which is where
people look.

**Schema or database per tenant.** Strong isolation, and it makes the shared
cache — a feature, not an accident — impossible, along with cross-tenant
analytics and migrations that do not scale with tenant count.

## Cost

Duplicated enforcement, and a policy that has to be remembered when a table is
added. The checklist is in [row-level security](../database/rls.md), and new
tables must be added to `RLS_TABLES` in the migration.

One sharp edge, called out explicitly because it silently disables the
backstop: **a table owner bypasses RLS by default.** Running the application as
the role that owns the tables means the policies never apply. Production must
connect as a non-owner role, or mark the tables `FORCE ROW LEVEL SECURITY`.

A second, deliberate compromise: the policy also matches when
`app.current_org` is unset, for migrations, the seed script and cross-org
background workers. That is a trusted-path exemption, documented rather than
hidden, and it can be removed in favour of a `BYPASSRLS` role for a stricter
posture.

## See also

- [Row-level security](../database/rls.md)
- [Threat model](../security/threat-model.md)
- [Production](../deployment/production.md)
