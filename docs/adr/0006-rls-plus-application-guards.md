# 0006. Tenant isolation enforced twice

<p>
  <a href="../adr/README.md"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/db/session.py"><img alt="source: db/session.py" src="https://img.shields.io/badge/source-db%2Fsession.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../adr/README.md) › **0006. Tenant isolation enforced twice** · page 57 of 57

**Status** Accepted

## Context

**A [multi-tenant](../architecture/overview.md#tenancy) system must stop one organization reading another's data.** The two standard approaches are usually presented as alternatives:

| Approach | Strength | Weakness |
| --- | --- | --- |
| **Application-level scoping**: every query filters by `org_id` | fast, explicit, visible in the code | fails the moment somebody writes a query that forgets |
| **PostgreSQL [row-level security](../database/rls.md#how-it-works)**: the database enforces it | cannot be forgotten | invisible at the call site; a surprising empty result set is unpleasant to debug |

- **Each covers the other's failure mode**

## Decision

**Both.**

- **[Application guards](../database/rls.md#the-application-guards) are primary.** Every resource fetched by id is checked against the caller's `org_id`:

```python
# app/api/deps.py: get_project, condensed
project = await session.get(Project, target)
if project is None or project.org_id != principal.org_id:
    # Cross-tenant access returns 404, not 403. Confirming that an id
    # exists in another organization is itself a leak.
    raise NotFoundError("Project not found.")
```

- **RLS is the backstop.** [24 tables](../database/rls.md#covered-tables) carry a policy reading `current_setting('app.current_org')`, which the session sets per transaction with `SET LOCAL` right after the principal resolves
  - 23 from the [initial migration](../database/migrations.md#0001_initial), plus `custom_roles` from [`0002`](../database/migrations.md#0003_custom_roles)
  - the call is `set_config('app.current_org', :org, true)`, the function form of `SET LOCAL` that takes a bound parameter ([`set_tenant`](../../backend/app/db/session.py))
- **Three supporting rules:**
  - cross-tenant access returns `404`, never `403`
  - **`SET LOCAL` is transaction-scoped**, so a pooled connection never carries one request's tenant into the next. It also works through [PgBouncer in transaction mode](../deployment/production.md#postgresql), which a session-level `SET` would not
  - **authorization is [centralised](../security/api-keys.md#checks-are-centralised)** in `require(Permission.X)` ([`app/api/deps.py`](../../backend/app/api/deps.py)): no business-logic module runs its own check, and `can()` denies by default

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Application scoping alone** | One forgotten `WHERE` clause is a cross-tenant leak, in a codebase with hundreds of queries |
| **RLS alone** | Every missing filter becomes an empty result at runtime instead of a visible bug, and the application has no idea why. Isolation also becomes invisible to anyone reading the service layer, which is where people look |
| **Schema or database per tenant** | Strong isolation, but makes the shared cache (a feature, not an accident) impossible, along with cross-tenant analytics, and migrations stop scaling with tenant count |

## Cost

- **Duplicated enforcement**, and a policy that must be remembered whenever a table is added
  - the checklist is in [row-level security](../database/rls.md#adding-a-table)
- **One sharp edge, called out because it silently disables the backstop: a table owner bypasses RLS by default**
  - run the application as the role that owns the tables, and the policies never apply
  - production must connect as a non-owner role, or mark the tables `FORCE ROW LEVEL SECURITY`: see [deployment guide, step 8](../deployment/deployment-guide.md#8-make-row-level-security-bind)
- **A deliberate compromise:** the policy also matches when `app.current_org` is **[unset](../database/rls.md#the-empty-value-clause)**
  - for migrations, the seed script and cross-org background workers
  - a trusted-path exemption, documented rather than hidden
  - removable in favour of a `BYPASSRLS` role, for a stricter posture

## Related

- [Row-level security: how it works](../database/rls.md#how-it-works): the policy, `set_tenant` and the empty-value clause as implemented
- [Row-level security: verifying it](../database/rls.md#verifying-it): the queries that prove the policies bind; no automated test covers RLS today
- [Threat model: cross-tenant data access](../security/threat-model.md#cross-tenant-data-access): the threat both layers answer
- [Production: before anything else](../deployment/production.md#before-anything-else): the non-owner database role, without which the backstop is silently off
- [Deployment guide, step 8](../deployment/deployment-guide.md#8-make-row-level-security-bind): the same role change on a single server
- [`test_security.py`](../../backend/tests/unit/test_security.py): `test_permission_check_denies_by_default` and the role tests behind `require()`

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0005: A test key overrides the execution mode,…](../adr/0005-test-key-mode-precedence.md) | [Docs index](../README.md) · [Decisions index](../adr/README.md) | [Back to the start](../README.md) |
