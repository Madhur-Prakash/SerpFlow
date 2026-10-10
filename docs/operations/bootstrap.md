# Startup bootstrap

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="bootstrap: advisory-locked" src="https://img.shields.io/badge/bootstrap-advisory--locked-3fcf8e">
  <img alt="Alembic: migrations" src="https://img.shields.io/badge/Alembic-migrations-6BA81E">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <a href="../../backend/app/db/bootstrap.py"><img alt="source: db/bootstrap.py" src="https://img.shields.io/badge/source-db%2Fbootstrap.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Startup bootstrap** · page 30 of 50

**Two environment variables turn a container plus an empty database into a working instance**, with no orchestration step in between:

```bash
RUN_MIGRATIONS_ON_STARTUP=true    # apply Alembic migrations before serving
SEED_ON_STARTUP=true              # insert only the data that is missing
```

| Where | Value | Why |
| --- | --- | --- |
| **Code default** | `false` for both | a deployment that upgrades without touching its environment behaves exactly as before |
| **Shipped `.env.example`** | `true` for both | `docker compose up` and `make backend` each produce a usable system with no extra step |

- **Different on purpose:** convenience belongs in the file you are expected to edit, not in the fallback that applies when nobody has
- Implementation: [`app/db/bootstrap.py`](../../backend/app/db/bootstrap.py) · [`app/db/seed.py`](../../backend/app/db/seed.py)

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

- **Migrations run first:** seeding writes to tables that may not exist yet

```json
{"event": "bootstrap.migrations_done"}
{"event": "bootstrap.seed_done", "seeded": ["catalog", "benchmarks", "demo"]}
```

On the next start:

```json
{"event": "bootstrap.seed_skipped"}
```

- **The bootstrap logs events, not secrets.** It never prints API keys. To get demo keys, run the seed script by hand (below)

## Three things make this safe to leave on

### 1. An advisory lock

- **Without it, several replicas starting together would race:** two concurrent `alembic upgrade head` runs on one database, or two seeds inserting the same demo organization

```python
MIGRATION_LOCK_KEY = 0x5E89_F10C_0001
SEED_LOCK_KEY      = 0x5E89_F10C_0002
```

- **One process takes a PostgreSQL advisory lock; the rest block** until it is done, then find the work already complete
- **Blocking rather than skipping is deliberate:** a replica that skipped would start serving against a schema still being changed
- **Session-scoped, on a dedicated connection, released in a `finally`:** a process that dies mid-migration frees it when its connection drops
- **The two keys are distinct**, so seeding never blocks migrating
- **This is why migration moved out of the Dockerfile's `CMD`:** a shell `alembic upgrade head && exec ...` in front of the server cannot take a lock that outlives it

### 2. Idempotence

The seed checks before it writes:

```python
if await catalog_is_projected(session): ...     # count of catalog_engines for this version
if await benchmarks_are_loaded(session): ...    # count of benchmark_tasks
if await demo_org_exists(session): ...          # the demo slug
```

- **A populated database costs three `SELECT count(*)` queries**, and no writes
- **A half-seeded one is completed, not duplicated:** if the catalog loaded but the process died before the demo org, the next start creates only the demo org
- Asserted against a real database in [`tests/integration/test_bootstrap_seed.py`](../../backend/tests/integration/test_bootstrap_seed.py), which seeds three times in a row and compares row counts

### 3. An environment refusal

`SEED_ON_STARTUP` is **ignored** when `ENVIRONMENT` is `staging` or `production`:

```json
{"event": "bootstrap.seed_refused", "environment": "production"}
```

- **The seed creates demo accounts whose password is committed to this repository:** right for a laptop, indefensible in a deployed environment
- So the refusal lives **in the settings**, not in whoever writes the manifest
- **A warning, not an error:** the service carries on serving
- **Migrations are not refused anywhere.** Running them in production is a legitimate, common deployment strategy

## Failure behaviour

- **A migration failure is fatal:** the lifespan raises and the container exits
  - intentional: a service that silently starts against an un-migrated database fails later, on a query, in a way that is much harder to read than a refusal to boot
- **One exception: missing benchmark fixtures are logged and skipped**

```json
{"event": "seed.benchmarks_skipped"}
```

- The benchmark suite is reference data behind one dashboard. Nothing about serving a search depends on it

## Seeding by hand

The same code backs `make seed`:

```bash
make seed                       # seed everything, print accounts and API keys
make seed ARGS=--reset          # delete the demo org, recreate it, print fresh keys
make seed ARGS=--if-absent      # exactly what the startup bootstrap does
```

In a container:

```bash
docker compose exec backend python scripts/seed.py --reset
```

- **The implementation lives in `app/db/seed.py`**, not in `scripts/`, so both callers share it
- `backend/scripts/seed.py` is the command line around it

## Logging note

- **Alembic's `env.py` calls `fileConfig()`, which disables every existing logger by default**
  - run in-process, that would silence the application's own logging for the rest of the process, including whatever error came next

```python
config.attributes["configure_logger"] = False
```

- `env.py` honours that, and passes `disable_existing_loggers=False` when it does configure logging
- **Not theoretical:** it hid a real startup failure behind a silent exit during development

## Related

- [Migrations](../database/migrations.md)
- [Docker](../deployment/docker.md)
- [Deployment guide](../deployment/deployment-guide.md)
- [Production](../deployment/production.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Secrets](../security/secrets.md) | [Docs index](../README.md) | [Email](../operations/email.md) |
