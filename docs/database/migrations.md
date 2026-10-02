# Migrations

Every schema change goes through Alembic. Nothing is created by hand, and
`make seed` runs only after `make upgrade` has brought the database to head.

Location: [`backend/alembic/`](../../backend/alembic).

## Commands

```bash
make upgrade                             # migrate to head
make migrate                             # alias for upgrade
make migration ARGS='-m "add column"'    # autogenerate a revision
make downgrade                           # roll back one revision
```

Behind those, the ordinary Alembic CLI works too:

```bash
cd backend
uv run alembic current
uv run alembic history --verbose
uv run alembic upgrade head
uv run alembic downgrade -1
```

## The revision chain

```
0001_initial   initial schema: 33 tables, extensions, indexes, RLS, audit trigger
0002_audit_purge   narrow the audit-log guard so legitimate deletes work
```

### 0001_initial

Creates the extensions first, because columns depend on them:

```sql
CREATE EXTENSION IF NOT EXISTS vector;     -- cache_entries.embedding
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- query_text fuzzy search
CREATE EXTENSION IF NOT EXISTS btree_gin;  -- composite GIN indexes
```

Then tables, then the indexes that autogenerate cannot express (HNSW, GIN
trigram), then row-level security on 23 tables, then the audit trigger.

Two details in that migration are not obvious:

**The circular foreign key.** `organizations.default_credential_id` points at
`upstream_credentials`, and `upstream_credentials.org_id` points back. Alembic
cannot emit that inline in either direction, so the column is created without a
constraint and the constraint is added after both tables exist:

```python
op.create_foreign_key(
    "fk_organizations_default_credential_id_upstream_credentials",
    "organizations", "upstream_credentials",
    ["default_credential_id"], ["id"], ondelete="SET NULL",
)
```

The model side carries `use_alter=True` so autogenerate does not try to put it
back inline on the next revision.

**The audit trigger runs `BEFORE`.** `entry_hash` is therefore computed by the
application before the INSERT, with an explicit `created_at`, rather than by a
trigger. A trigger that mutated the row would have to run `BEFORE INSERT` and
would then be inside the very surface the chain is supposed to protect.

### 0002_audit_purge

The original guard refused every `UPDATE` and `DELETE`, which broke two
legitimate paths: deleting an organization, and `make seed --reset`. Both fail
on the cascade rather than on an explicit delete, so neither could be
special-cased in application code alone.

`UPDATE` is still refused unconditionally. `DELETE` is permitted only inside a
transaction that has set `app.audit_purge = 'on'`:

```sql
IF TG_OP = 'DELETE'
   AND coalesce(current_setting('app.audit_purge', true), '') = 'on' THEN
    RETURN OLD;
END IF;
RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
```

That setting is transaction-scoped and set in exactly one place,
[`AuditService.allow_purge`](../../backend/app/services/audit/service.py). The
guarantee survives; the legitimate path works.

## Writing a new revision

```bash
make migration ARGS='-m "add engine deprecation flag"'
```

Then **read the generated file before running it**. Autogenerate is good at
columns and bad at everything else: it will not produce HNSW indexes, RLS
policies, triggers, data backfills, or the right order for a circular
constraint.

Checklist for a new table:

1. `org_id` with an index and a foreign key to `organizations`.
2. Added to `RLS_TABLES` so a policy is created.
3. `created_at` / `updated_at` with server defaults.
4. A prefixed-ULID primary key, matching the `id_column` helper.
5. A `downgrade()` that actually reverses it.

## Autogenerate configuration

[`env.py`](../../backend/alembic/env.py) sets:

- `compare_type=True` and `compare_server_default=True`, so a changed column
  type produces a diff instead of silent drift.
- `include_object` excluding `alembic_version` and `spatial_ref_sys`, which are
  owned by Alembic and PostGIS respectively.
- `sqlalchemy.url` from `settings.database_url`, so migrations and the
  application cannot point at different databases.

Constraint naming is set on the metadata
([`app/db/base.py`](../../backend/app/db/base.py)), which is what makes
autogenerate diffs stable across machines:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

Migrations run async, through `async_engine_from_config` with a `NullPool`, for
the same reason the application does: psycopg 3 async is the only driver
configured.

## Resetting

```bash
make seed ARGS=--reset              # delete the demo org and reload, keeping the schema
docker compose down -v && make up   # drop the volume and start from nothing
```

`--reset` goes through `AuditService.allow_purge`, which is why it works at all
given the trigger. `make down` stops the containers but keeps the volume, so it
is not a reset.

## Related

- [Schema](schema.md)
- [Row-level security](rls.md)
