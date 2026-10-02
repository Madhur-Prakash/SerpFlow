# Row-level security

Tenant isolation is enforced twice. Application guards are the primary check;
PostgreSQL row-level security is the backstop for the query somebody forgets to
scope.

## How it works

Every tenant-scoped table carries `org_id` with an index and a policy:

```sql
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY serpflow_tenant_isolation ON runs
  USING (org_id = current_setting('app.current_org', true)
         OR coalesce(current_setting('app.current_org', true), '') = '');
```

The setting is applied per transaction, right after the principal resolves:

```python
# app/db/session.py
await session.execute(
    text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id}
)
```

`set_config(..., true)` is `SET LOCAL`: it lasts for the transaction and
unwinds with it, so a pooled connection never carries one request's tenant into
the next.

### The empty-value clause

The policy also matches when `app.current_org` is unset. That is deliberate and
worth being explicit about, because it looks like a hole.

The setting is empty in exactly three situations: migrations, the seed script,
and background workers that legitimately operate across organizations (quota
reconciliation, catalog reload). All three are trusted code paths that never
serve a request.

Any request path sets it, because `get_principal` cannot return without doing
so. A handler that somehow queried without a resolved principal would have no
`org_id` to scope by in the first place and would fail earlier.

If you want the strict posture, drop the `OR` clause and give migrations and
workers a role with `BYPASSRLS`.

## Covered tables

23 tables, listed as `RLS_TABLES` in
[`0001_initial_schema.py`](../../backend/alembic/versions/0001_initial_schema.py):

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

`organizations` has its own policy keyed on `id` rather than `org_id`.

`users` is deliberately **not** scoped: a user can belong to several
organizations, and membership is what carries the tenancy.

## The application guards

RLS alone would be a thin story, so the application checks first:

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

1. Every resource fetched by id is checked against the caller's `org_id`.
2. Cross-tenant access returns `404`, never `403`.
3. Authorization is centralised in `require(Permission.X)`. No business-logic
   module performs its own check, and the default is deny.

## Adding a table

1. Add `org_id` with a foreign key to `organizations` and an index.
2. Add the table name to `RLS_TABLES` in the initial migration, or enable the
   policy in a new migration.
3. Scope every query by `org_id` in the service layer anyway. RLS is the
   backstop, not the plan.

## Verifying it

```bash
make psql
```

```sql
-- how many tables are protected
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

Note that the table owner bypasses RLS by default. In production the
application should connect as a role that does not own the tables, or the
tables should be marked `FORCE ROW LEVEL SECURITY`. See
[production deployment](../deployment/production.md).

## The audit log

`audit_log` carries an additional guarantee beyond isolation: it is append-only
at the database level.

```sql
CREATE TRIGGER serpflow_audit_no_update
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION serpflow_audit_append_only();
```

`UPDATE` is refused unconditionally. `DELETE` is refused unless the transaction
has explicitly set `app.audit_purge`, which only organization deletion does.
Combined with the per-organization hash chain, that makes tampering both
difficult and detectable: `GET /v1/audit/verify` walks the chain and reports
the first break by sequence number.
