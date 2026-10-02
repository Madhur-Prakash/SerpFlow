# Startup bootstrap

Two environment variables turn a container plus an empty database into a
working instance, with no orchestration step in between.

```bash
RUN_MIGRATIONS_ON_STARTUP=true    # apply Alembic migrations before serving
SEED_ON_STARTUP=true              # insert only the data that is missing
```

The **code** default for both is `false`, so a deployment that upgrades without
touching its environment behaves exactly as it did before. The **shipped**
`.env.example` sets both to `true`, which is why `docker compose up` and
`make backend` each produce a usable system with no extra step.

Those are different things on purpose: convenience belongs in the file you are
expected to edit, not in the fallback that applies when nobody has.

Implementation:
[`app/db/bootstrap.py`](../../backend/app/db/bootstrap.py),
[`app/db/seed.py`](../../backend/app/db/seed.py).

## What happens

```
lifespan starts
  |
  +- RUN_MIGRATIONS_ON_STARTUP -> take advisory lock -> alembic upgrade head
  |
  +- SEED_ON_STARTUP           -> refuse if staging/production
  |                            -> take advisory lock
  |                            -> catalog projected?   no -> project it
  |                            -> benchmarks loaded?   no -> load them
  |                            -> demo org exists?     no -> create it
  |
  +- catalog loads, Kafka consumers start, server serves
```

Migrations run first, because seeding writes to tables that may not exist yet.

```json
{"event": "bootstrap.migrations_done"}
{"event": "bootstrap.seed_done", "seeded": ["catalog", "benchmarks", "demo"]}
```

On the next start:

```json
{"event": "bootstrap.seed_skipped"}
```

## Three things make this safe to leave on

### An advisory lock

Several API replicas starting together would otherwise race: two concurrent
`alembic upgrade head` runs against one database, or two seeds inserting the
same demo organization.

```python
MIGRATION_LOCK_KEY = 0x5E89_F10C_0001
SEED_LOCK_KEY      = 0x5E89_F10C_0002
```

One process takes a PostgreSQL advisory lock; the rest **block** until it is
done, then find the work already complete. Blocking rather than skipping is
deliberate — a replica that skipped would start serving against a schema that
is still being changed.

The lock is session-scoped on a dedicated connection and released in a
`finally`, so a process that dies mid-migration frees it when its connection
drops.

The two keys are distinct, so seeding never blocks migrating.

This is also why migration moved out of the Dockerfile's `CMD`. A shell
`alembic upgrade head && exec ...` in front of the server cannot take a lock
that outlives it.

### Idempotence

The seed checks before it writes:

```python
if await catalog_is_projected(session): ...     # count of catalog_engines for this version
if await benchmarks_are_loaded(session): ...    # count of benchmark_tasks
if await demo_org_exists(session): ...          # the demo slug
```

A populated database costs three `SELECT count(*)` queries and no writes at
all. A half-seeded one is completed rather than duplicated — if the catalog
loaded but the process died before the demo org was created, the next start
creates only the demo org.

Asserted against a real database in
[`tests/integration/test_bootstrap_seed.py`](../../backend/tests/integration/test_bootstrap_seed.py),
which seeds three times in a row and compares row counts.

### An environment refusal

`SEED_ON_STARTUP` is ignored when `ENVIRONMENT` is `staging` or `production`:

```json
{"event": "bootstrap.seed_refused", "environment": "production"}
```

The seed creates demo accounts whose password is committed to this repository.
That is correct for a laptop and indefensible in a deployed environment, so the
refusal lives in the settings rather than in whoever writes the manifest. It is
a warning, not an error — the service carries on serving.

Migrations are **not** refused anywhere. Running them in production is a
legitimate, and common, deployment strategy.

## Failure behaviour

A migration failure is **fatal**: the lifespan raises and the container exits.

That is intentional. A service that silently starts against an un-migrated
database fails later, on a query, in a way that is much harder to read than a
refusal to boot.

One exception: missing benchmark fixtures are logged and skipped.

```json
{"event": "seed.benchmarks_skipped"}
```

The benchmark suite is reference data behind one dashboard. Nothing about
serving a search depends on it, so a missing fixture file is not worth refusing
to start over.

## Seeding by hand

The same code backs `make seed`:

```bash
make seed                       # seed everything
make seed ARGS=--reset          # delete the demo org and recreate it
make seed ARGS=--if-absent      # exactly what the startup bootstrap does
```

The implementation lives in `app/db/seed.py` rather than in `scripts/` so both
callers share it. `backend/scripts/seed.py` is the command line around it.

## Logging note

Alembic's `env.py` calls `fileConfig()`, which disables every existing logger by
default. Run in-process that would silence the application's own logging for
the rest of the process — including whatever error came next.

```python
config.attributes["configure_logger"] = False
```

`env.py` honours that, and passes `disable_existing_loggers=False` when it does
configure logging. This was not a theoretical concern: it hid a real startup
failure behind a silent exit during development.

## Related

- [Migrations](../database/migrations.md)
- [Docker](../deployment/docker.md)
- [Production](../deployment/production.md)
