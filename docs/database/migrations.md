# Migrations

<p>
  <a href="../README.md#database"><img alt="docs: Database" src="https://img.shields.io/badge/docs-Database-4169E1?logo=readthedocs&logoColor=white"></a>
  <img alt="revisions: 4" src="https://img.shields.io/badge/revisions-4-4169E1">
  <img alt="Alembic: migrations" src="https://img.shields.io/badge/Alembic-migrations-6BA81E">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <a href="../../backend/alembic"><img alt="source: backend/alembic" src="https://img.shields.io/badge/source-backend%2Falembic-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Database](../README.md#database) › **Migrations** · page 23 of 50

- **Every schema change goes through Alembic.** Nothing is created by hand
- `make seed` runs only **after** `make upgrade` has brought the database to head
- The backend can also migrate itself on startup, advisory-locked: see [bootstrap](../operations/bootstrap.md)
- Location: [`backend/alembic/`](../../backend/alembic)

## Commands

```bash
make upgrade                             # migrate to head
make migrate                             # alias for upgrade
make migration ARGS='-m "add column"'    # autogenerate a revision
make downgrade                           # roll back one revision
```

The ordinary Alembic CLI works too:

```bash
cd backend
uv run alembic current
uv run alembic history --verbose
uv run alembic upgrade head
uv run alembic downgrade -1
```

## The revision chain

| Revision | What it does |
| --- | --- |
| `0001_initial` | Initial schema: 32 tables, extensions, indexes, RLS, the audit trigger |
| `0002_audit_purge` | Narrows the audit-log guard so legitimate deletes work |
| `0003_custom_roles` | Adds `custom_roles`, with row-level security, for organization-defined roles |
| `0004_project_mode` | Adds `projects.execution_mode`, `NULL` meaning "inherit the instance default" |

### 0001_initial

Creates the **extensions first**, because columns depend on them:

```sql
CREATE EXTENSION IF NOT EXISTS vector;     -- cache_entries.embedding
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- query_text fuzzy search
CREATE EXTENSION IF NOT EXISTS btree_gin;  -- composite GIN indexes
```

- Then tables
- Then the indexes autogenerate cannot express (HNSW, GIN trigram)
- Then row-level security on 23 tables (the 22 in `RLS_TABLES`, plus `organizations`)
- Then the audit trigger

Two details are not obvious:

- **The circular foreign key**
  - `organizations.default_credential_id` points at `upstream_credentials`, and `upstream_credentials.org_id` points back
  - Alembic cannot emit that inline in either direction, so the column is created without a constraint, which is added once both tables exist:

```python
op.create_foreign_key(
    "fk_organizations_default_credential_id_upstream_credentials",
    "organizations", "upstream_credentials",
    ["default_credential_id"], ["id"], ondelete="SET NULL",
)
```

  - the model side carries `use_alter=True`, so autogenerate does not try to put it back inline next time
- **The audit trigger runs `BEFORE`**
  - so `entry_hash` is computed by the application before the INSERT, with an explicit `created_at`
  - a trigger that mutated the row would sit inside the very surface the chain is meant to protect

### 0002_audit_purge

- **The original guard refused every `UPDATE` and `DELETE`**, which broke two legitimate paths:
  - deleting an organization
  - `make seed --reset`
- Both fail on the **cascade**, not on an explicit delete, so neither could be special-cased in application code alone
- **`UPDATE` is still refused unconditionally. `DELETE` is allowed only inside a transaction that set `app.audit_purge = 'on'`:**

```sql
IF TG_OP = 'DELETE'
   AND coalesce(current_setting('app.audit_purge', true), '') = 'on' THEN
    RETURN OLD;
END IF;
RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
```

- That setting is transaction-scoped, and set in **exactly one place**: [`AuditService.allow_purge`](../../backend/app/services/audit/service.py)
- The guarantee survives; the legitimate path works

### 0003_custom_roles

- **An owner can define a role** with a permission set of their choosing, for shapes the five built-in roles do not cover
- **A membership's or API key's `role` column** holds either a built-in role name or a custom role's slug, so the slug is **unique per organization**
- **Row-level security applies**, like every tenant-scoped table: a role defined in one organization is invisible to another. That brings RLS to **24 tables**

### 0004_project_mode

- **The mode used to be server-wide**, so a project that only ever wanted recorded traffic could not say so while another ran live
- **`NULL` means "inherit the server default"**, deliberately distinct from writing today's default into every row
  - an operator who later changes `SERPFLOW_MODE` moves the projects that never expressed a preference, and leaves the rest alone
- **A check constraint** admits only `live`, `record` and `replay`. `mock` stays reachable only through a test key

## Writing a new revision

```bash
make migration ARGS='-m "add engine deprecation flag"'
```

- **Read the generated file before running it**
- Autogenerate is good at columns and bad at everything else. It will **not** produce:
  - HNSW indexes
  - RLS policies or triggers
  - data backfills
  - the right order for a circular constraint

**Checklist for a new table:**

1. `org_id` with an index and a foreign key to `organizations`
2. A row-level security policy: add it to `RLS_TABLES`, or enable it in the revision as `0003_custom_roles` does
3. `created_at` / `updated_at` with server defaults
4. A prefixed-ULID primary key, matching the `id_column` helper
5. A `downgrade()` that actually reverses it

## Autogenerate configuration

[`env.py`](../../backend/alembic/env.py) sets:

- **`compare_type=True` and `compare_server_default=True`:** a changed column type produces a diff, not silent drift
- **`include_object`** excluding `alembic_version` and `spatial_ref_sys` (owned by Alembic and PostGIS)
- **`sqlalchemy.url` from `settings.database_url`:** migrations and the application cannot point at different databases

Constraint naming is set on the metadata ([`app/db/base.py`](../../backend/app/db/base.py)), which keeps autogenerate diffs stable across machines:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

- **Migrations run async**, through `async_engine_from_config` with a `NullPool`, for the same reason the application does: psycopg 3 async is the only driver configured

## Resetting

```bash
make seed ARGS=--reset              # delete the demo org and reload, keeping the schema
docker compose down -v && make up   # drop the volume and start from nothing
```

- **`--reset` goes through `AuditService.allow_purge`**, which is why it works at all, given the trigger
- **`make down` is not a reset:** it stops the containers but keeps the volume

## Related

- [Schema](schema.md)
- [Row-level security](rls.md)
- [Bootstrap](../operations/bootstrap.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Database schema](../database/schema.md) | [Docs index](../README.md) | [Row-level security](../database/rls.md) |
