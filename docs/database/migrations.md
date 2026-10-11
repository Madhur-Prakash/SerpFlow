# Migrations

<p>
  <a href="../database/README.md"><img alt="docs: Database" src="https://img.shields.io/badge/docs-Database-4169E1?logo=readthedocs&logoColor=white"></a>
  <img alt="revisions: 4" src="https://img.shields.io/badge/revisions-4-4169E1">
  <img alt="Alembic: migrations" src="https://img.shields.io/badge/Alembic-migrations-6BA81E">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <a href="../../backend/alembic"><img alt="source: backend/alembic" src="https://img.shields.io/badge/source-backend%2Falembic-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [Database](../database/README.md) › **Migrations** · page 36 of 50

- **Every schema change goes through Alembic.** Nothing is created by hand
- `make seed` runs only **after** `make upgrade` has brought the database to head ([everyday targets](../deployment/local.md#everyday-targets))
- The backend can also migrate itself on startup, advisory-locked, when `RUN_MIGRATIONS_ON_STARTUP=true`: see [bootstrap](../operations/bootstrap.md#1-an-advisory-lock)
- **Four revisions, one linear chain**, producing the [33 tables](schema.md) at head
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
| `0001_initial` | Initial schema: 32 tables, the `vector` and `pg_trgm` extensions, indexes, RLS on 23 tables, the audit trigger |
| `0002_audit_purge` | Narrows the audit-log guard so legitimate deletes work |
| `0003_custom_roles` | Adds `custom_roles`, with row-level security, for organization-defined roles |
| `0004_project_mode` | Adds `projects.execution_mode`, `NULL` meaning "inherit the instance default" |

### 0001_initial

Code: [`0001_initial_schema.py`](../../backend/alembic/versions/0001_initial_schema.py)

Creates the **extensions first**, because columns depend on them:

```sql
CREATE EXTENSION IF NOT EXISTS vector;     -- cache_entries.embedding, catalog_engines.embedding
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- query_text and search_text trigram search
```

- **`btree_gin` is not created by any migration.** Only the container's [`01-extensions.sql`](../../docker/postgres/init/01-extensions.sql) creates it, as the superuser, alongside the other two. `0001_initial` also runs `CREATE EXTENSION IF NOT EXISTS` for `vector` and `pg_trgm`: a no-op once the init script has run, and one that needs a superuser on a database where it has not
- Then tables
- Then the three indexes autogenerate cannot express:
  - `ix_cache_entries_embedding_hnsw`: HNSW over cosine distance, `m = 16`, `ef_construction = 64`
  - `ix_cache_entries_query_trgm` and `ix_catalog_engines_search_trgm`: GIN trigram
- Then row-level security on 23 tables (the 22 in `RLS_TABLES`, plus `organizations`): see [row-level security](rls.md#covered-tables) and [ADR 0006](../adr/0006-rls-plus-application-guards.md)
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
- **The audit trigger fires `BEFORE UPDATE OR DELETE`, never on `INSERT`**
  - so the database never rewrites an audit row: `entry_hash` is computed by the application before the INSERT, with an explicit `created_at` instead of the server default ([`AuditService.record`](../../backend/app/services/audit/service.py))
  - a trigger that mutated the row would sit inside the very surface the chain is meant to protect

### 0002_audit_purge

Code: [`0002_audit_purge_guard.py`](../../backend/alembic/versions/0002_audit_purge_guard.py)

- **The original guard refused every `UPDATE` and `DELETE`**, which broke two legitimate paths:
  - deleting an organization, which the `org:delete` permission anticipates (no endpoint deletes an organization at HEAD)
  - `make seed ARGS=--reset`, which deletes the demo organization
- Both fail on the **cascade** from `organizations`, not on an explicit delete, so neither could be special-cased in application code alone
- **`UPDATE` is still refused unconditionally. `DELETE` is allowed only inside a transaction that set `app.audit_purge = 'on'`:**

```sql
IF TG_OP = 'DELETE'
   AND coalesce(current_setting('app.audit_purge', true), '') = 'on' THEN
    RETURN OLD;
END IF;
RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
```

- That setting is transaction-scoped (`set_config(..., true)`), and set in **exactly one place**: [`AuditService.allow_purge`](../../backend/app/services/audit/service.py). Its only caller at HEAD is the seed's `reset_demo` ([`app/db/seed.py`](../../backend/app/db/seed.py))
- The guarantee survives; the legitimate path works
- `downgrade()` restores the unconditional refusal
- The error a refused write raises, and what to do about it: [troubleshooting](../operations/troubleshooting.md#audit_log-is-append-only-delete-is-not-permitted)

### 0003_custom_roles

Code: [`0003_custom_roles.py`](../../backend/alembic/versions/0003_custom_roles.py)

- **An owner can define a role** with a permission set of their choosing, for shapes the five built-in roles do not cover ([API keys: custom roles](../security/api-keys.md#custom-roles))
- **A membership's or API key's `role` column** holds either a built-in role name or a custom role's slug, so the slug is **unique per organization** (`uq_custom_roles_org_slug`)
- **Row-level security applies**, like every tenant-scoped table: a role defined in one organization is invisible to another. That brings RLS to **24 tables**

### 0004_project_mode

Code: [`0004_project_execution_mode.py`](../../backend/alembic/versions/0004_project_execution_mode.py)

- **The mode used to be server-wide**, so a project that only ever wanted recorded traffic could not say so while another ran live
- **`NULL` means "inherit the server default"**, deliberately distinct from writing today's default into every row
  - an operator who later changes `SERPFLOW_MODE` moves the projects that never expressed a preference, and leaves the rest alone
- **A check constraint** admits only `live`, `record` and `replay`. `mock` stays reachable only through a test key ([execution modes](../product/execution-modes.md#why-mock-is-not-selectable), [ADR 0005](../adr/0005-test-key-mode-precedence.md#update-per-project-and-per-request-modes))

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
2. A row-level security policy: enable it in the new revision as `0003_custom_roles` does (`RLS_TABLES` belongs to `0001_initial`, which has already run everywhere). See [row-level security: adding a table](rls.md#adding-a-table)
3. `created_at` / `updated_at` with server defaults: the model inherits `TimestampMixin`
4. A prefixed-ULID primary key, defaulting to `new_id("<prefix>")` from [`app/db/base.py`](../../backend/app/db/base.py)
5. A `downgrade()` that actually reverses it

## Autogenerate configuration

[`env.py`](../../backend/alembic/env.py) sets:

- **`compare_type=True` and `compare_server_default=True`:** a changed column type produces a diff, not silent drift
- **`include_object`** excluding `alembic_version` and `spatial_ref_sys` (owned by Alembic and PostGIS)
- **`sqlalchemy.url` from `settings.database_url`:** migrations and the application cannot point at different databases (`DATABASE_URL`, see [secrets](../security/secrets.md#inventory))

Constraint naming is set on the metadata ([`app/db/base.py`](../../backend/app/db/base.py)), which keeps autogenerate diffs stable across machines:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

- **Composite indexes and constraints are named explicitly** in the models (`ix_cache_entries_partition`, `uq_custom_roles_org_slug`), since the convention only names from the first column
- **Migrations run async**, through `async_engine_from_config` with a `NullPool`, for the same reason the application does: psycopg 3 async is the only driver configured
- **`fileConfig()` is skipped when the startup bootstrap runs Alembic in-process** (`configure_logger = False`), and otherwise called with `disable_existing_loggers=False`, so migrating never silences the application's logging ([bootstrap: logging note](../operations/bootstrap.md#logging-note))

## Resetting

```bash
make seed ARGS=--reset              # delete the demo org and reload, keeping the schema
docker compose down -v && make up   # drop the volume and start from nothing
```

- **`--reset` goes through `AuditService.allow_purge`**, which is why it works at all, given the trigger
- **`make down` is not a reset:** it stops the containers but keeps the volume ([local development: resetting](../deployment/local.md#resetting))

## Related

- [Database schema](schema.md): the 33 tables these revisions produce
- [Row-level security](rls.md): the policies `0001_initial` and `0003_custom_roles` create
- [Startup bootstrap](../operations/bootstrap.md): running `alembic upgrade head` on API start, under an advisory lock
- [Deployment guide: upgrades and rollback](../deployment/deployment-guide.md#14-upgrades-and-rollback): migrating a running server
- [ADR 0006](../adr/0006-rls-plus-application-guards.md): why every new tenant table needs a policy
- [Troubleshooting: `type "vector" does not exist`](../operations/troubleshooting.md#type-vector-does-not-exist): a database provisioned without the extension

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Database schema](../database/schema.md) | [Docs index](../README.md) · [Database index](../database/README.md) | [Row-level security](../database/rls.md) |
