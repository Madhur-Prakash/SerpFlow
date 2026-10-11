# Row-level security

<p>
  <a href="../database/README.md"><img alt="docs: Database" src="https://img.shields.io/badge/docs-Database-4169E1?logo=readthedocs&logoColor=white"></a>
  <img alt="RLS tables: 24" src="https://img.shields.io/badge/RLS%20tables-24-4169E1">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <a href="../../backend/app/db/session.py"><img alt="source: db/session.py" src="https://img.shields.io/badge/source-db%2Fsession.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Database](../database/README.md) › **Row-level security** · page 37 of 50

**Tenant isolation is enforced twice** ([ADR 0006](../adr/0006-rls-plus-application-guards.md)):

- **Application guards** are the primary check
- **PostgreSQL row-level security** is the backstop, for the query somebody forgets to scope

## How it works

Every tenant-scoped table carries an indexed `org_id` (see [schema: conventions](schema.md#conventions)), and a policy:

```sql
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY serpflow_tenant_isolation ON runs
  USING (org_id = current_setting('app.current_org', true)
         OR coalesce(current_setting('app.current_org', true), '') = '');
```

The setting is applied **per transaction**, right after the principal resolves, by [`set_tenant`](../../backend/app/db/session.py):

```python
# app/db/session.py
await session.execute(
    text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id}
)
```

- **`set_config(..., true)` is `SET LOCAL`:** it lasts for the transaction and unwinds with it
- So a pooled connection **never** carries one request's tenant into the next
- **Who calls it:**
  - `get_principal` in [`app/api/deps.py`](../../backend/app/api/deps.py), on every authenticated request
  - `session_scope(org_id)`, for every Kafka consumer: each handler scopes to the `org_id` in its message ([`handlers.py`](../../backend/app/workers/consumers/handlers.py))
  - the MCP server, once it has resolved its key ([`app/mcp/server.py`](../../backend/app/mcp/server.py))
- **The container's init script sets the database default to `''`** (`ALTER DATABASE serpflow SET "app.current_org" TO ''`, in [`01-extensions.sql`](../../docker/postgres/init/01-extensions.sql))

### The empty-value clause

The policy also matches when `app.current_org` is unset or empty. **That is deliberate**, and worth being explicit about, because it looks like a hole.

- **The setting is empty on these paths**, all of which either run before any caller is known or never serve a caller:
  - migrations
  - the seed script and the startup seed ([bootstrap](../operations/bootstrap.md))
  - **authentication itself:** `get_principal` reads `api_keys`, `memberships`, `project_members` and `custom_roles` to resolve the caller *before* it can call `set_tenant`, and the unauthenticated routes (register, login, refresh, password reset, email verification) never set it
  - the MCP server's key lookup, for the same reason
- **Kafka consumers are not on this list.** Every handler scopes its session to the organization named in the message
- **Every authenticated request path sets it**, because `get_principal` cannot return without doing so
- **Want the strict posture?** Drop the `OR` clause, and give migrations, the seed and the authentication lookups a role with `BYPASSRLS` (or a `SECURITY DEFINER` function for the key and membership lookups). Dropping the clause alone breaks every login and every API key

## Covered tables

**24 tables in total:**

- **22 listed as `RLS_TABLES`** in [`0001_initial_schema.py`](../../backend/alembic/versions/0001_initial_schema.py):

```
projects              project_members        memberships
api_keys              upstream_credentials   upstream_quota_snapshots
service_sessions      budgets                budget_ledger
plans                 plan_candidates        runs
steps                 cache_entries          archive_refs
ttl_observations      semantic_guard_rejections
false_hit_reports     audit_log              alerts
notification_channels webhook_deliveries
```

- **`organizations`** has its own policy, keyed on `id` rather than `org_id`
- **`custom_roles`** gets the same policy in [`0003_custom_roles.py`](../../backend/alembic/versions/0003_custom_roles.py)
- **22 + 1 + 1 = 24**, which is what the `pg_tables` query under [verifying it](#verifying-it) returns at head
- **Nine tables are not covered**, each for a reason:
  - **`users` is deliberately not scoped:** a user can belong to several organizations, and membership is what carries the tenancy
  - **`auth_sessions`** belongs to a user, not an organization
  - **the four catalog tables and the three benchmark tables** hold no tenant data: they are keyed by `catalog_version`, and `benchmark_runs.org_id` is nullable
- Per-table detail: [database schema](schema.md)

## The application guards

**RLS alone would be a thin story**, so the application checks first:

```python
# app/api/deps.py
async def get_project(principal, session, project_id=None, ...):
    project = await session.get(Project, target)
    if project is None or project.org_id != principal.org_id:
        # Cross-tenant access returns 404, not 403. Confirming that an id
        # exists in another organization is itself a leak.
        raise NotFoundError("Project not found.")
    return project
```

Three rules:

1. **Every resource fetched by id** is checked against the caller's `org_id`
2. **Cross-tenant access returns `404`** (`NOT_FOUND`, see [API errors](../api/overview.md#errors)), never `403`
3. **Authorization is centralised** in `require(Permission.X)`. No business-logic module performs its own check, and the default is **deny** ([API keys: checks are centralised](../security/api-keys.md#checks-are-centralised))

## Adding a table

1. Add `org_id`, with a foreign key to `organizations` and an index
2. Enable the policy in the new migration, as `0003_custom_roles` does. `RLS_TABLES` lives in `0001_initial`, which has already run on every database, so adding a name there does nothing ([migrations: writing a new revision](migrations.md#writing-a-new-revision))
3. **Scope every query by `org_id` in the service layer anyway.** RLS is the backstop, not the plan

## Verifying it

```bash
make psql
```

```sql
-- how many tables are protected (24)
SELECT count(*) FROM pg_tables WHERE rowsecurity AND schemaname = 'public';

-- the policy on one table
SELECT polname, pg_get_expr(polqual, polrelid)
FROM pg_policy WHERE polrelid = 'runs'::regclass;

-- behaviour with a tenant set
BEGIN;
SELECT set_config('app.current_org', 'org_does_not_exist', true);
SELECT count(*) FROM runs;   -- 0
ROLLBACK;
```

- **The table owner bypasses RLS by default**, and no migration sets `FORCE ROW LEVEL SECURITY`
- **A superuser, or a role with `BYPASSRLS`, bypasses it always, `FORCE` included.** The compose stack connects as `POSTGRES_USER`, which the official postgres image creates as a superuser, so locally the policies exist but do not bind
- In production, connect as a role that is **neither a superuser nor the tables' owner**; or, if it owns them but is not a superuser, mark them `FORCE ROW LEVEL SECURITY`. The `BEGIN ... ROLLBACK` check above returns `0` only when that holds
- See [deployment guide, step 8](../deployment/deployment-guide.md#8-make-row-level-security-bind) and [production deployment](../deployment/production.md#before-anything-else)

## The audit log

**`audit_log` has one more guarantee beyond isolation:** it is append-only at the database level.

```sql
CREATE TRIGGER serpflow_audit_no_update
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION serpflow_audit_append_only();
```

- **`UPDATE`** is refused unconditionally
- **`DELETE`** is refused unless the transaction set `app.audit_purge = 'on'`, which only [`AuditService.allow_purge`](../../backend/app/services/audit/service.py) does
  - its one caller at HEAD is the seed's `reset_demo` (`make seed ARGS=--reset`)
  - the `org:delete` permission exists, but no endpoint deletes an organization yet
  - the narrowing came in [migration `0002_audit_purge`](migrations.md#0002_audit_purge)
- **Combined with the per-organization hash chain**, tampering is both difficult and detectable
  - `GET /v1/audit/verify` walks the chain and reports the first break, by sequence number ([API: governance](../api/overview.md#governance))
- A refused write raises `audit_log is append-only; DELETE is not permitted`: [troubleshooting](../operations/troubleshooting.md#audit_log-is-append-only-delete-is-not-permitted)

## Related

- [ADR 0006: tenant isolation enforced twice](../adr/0006-rls-plus-application-guards.md): why RLS is the backstop, not the only check
- [Database schema](schema.md): every table, with the 24 covered ones marked
- [Migrations](migrations.md#0001_initial): where the policies and the trigger are created
- [Threat model: cross-tenant data access](../security/threat-model.md#cross-tenant-data-access): the threat this answers
- [Deployment guide: make row-level security bind](../deployment/deployment-guide.md#8-make-row-level-security-bind): the role change production needs
- [Backend: request lifecycle](../architecture/backend.md#request-lifecycle): where `get_principal` and `set_tenant` run in a request

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Migrations](../database/migrations.md) | [Docs index](../README.md) · [Database index](../database/README.md) | [Security index](../security/README.md) |
