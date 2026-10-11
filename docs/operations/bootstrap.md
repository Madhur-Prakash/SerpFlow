# Startup bootstrap

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="bootstrap: advisory-locked" src="https://img.shields.io/badge/bootstrap-advisory--locked-3fcf8e">
  <img alt="Alembic: migrations" src="https://img.shields.io/badge/Alembic-migrations-6BA81E">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <a href="../../backend/app/db/bootstrap.py"><img alt="source: db/bootstrap.py" src="https://img.shields.io/badge/source-db%2Fbootstrap.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Startup bootstrap** · page 37 of 57

**Two [environment variables](../security/secrets.md#inventory) turn a container plus an empty database into a working instance**, with no orchestration step in between:

```bash
RUN_MIGRATIONS_ON_STARTUP=true    # apply Alembic migrations before serving
SEED_ON_STARTUP=true              # insert only the data that is missing
```

| Where | Value | Why |
| --- | --- | --- |
| **Code default** | `false` for both | a deployment that upgrades without touching its environment behaves exactly as before |
| **Shipped `.env.example`** | `true` for both | [`docker compose up`](../deployment/docker.md#running) and [`make backend`](../deployment/local.md#everyday-targets) each produce a usable system with no extra step |
| **`docker-compose.yml`** | `${...:-true}` for both | the backend container bootstraps itself even with the variables unset |

- **Different on purpose:** convenience belongs in the file you are expected to edit, not in the fallback that applies when nobody has
- The migrations are the [Alembic revision chain](../database/migrations.md#the-revision-chain); the seed is the same code `make seed` runs
- Implementation: [`app/db/bootstrap.py`](../../backend/app/db/bootstrap.py) · [`app/db/seed.py`](../../backend/app/db/seed.py) · called first thing in the lifespan in [`app/main.py`](../../backend/app/main.py)

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
- **The catalog then loads into memory** ([how it is loaded](../architecture/catalog.md#how-it-is-loaded)), and the in-process [Kafka consumers](kafka.md#running-consumers) start when `KAFKA_ENABLED` is true

```json
{"event": "bootstrap.migrations_start"}
{"event": "bootstrap.migrations_done"}
{"event": "bootstrap.seed_done", "seeded": ["catalog", "benchmarks", "demo"]}
```

- **`seeded` lists only the parts that were written**, so a half-seeded database reports, say, `["demo"]`

On the next start:

```json
{"event": "bootstrap.seed_skipped"}
```

What a first seed writes:

| Part | Rows |
| --- | --- |
| `catalog` | the committed YAML catalog projected into the [catalog tables](../database/schema.md#catalog-projection), with embeddings |
| `benchmarks` | the 120 [benchmark tasks](../product/benchmark.md#the-task-set) of suite `v1` |
| `demo` | organization `serpflow-demo`; an owner and an analyst; projects **Review Intelligence** and **Market Watch**; monthly budgets of 250 credits (organization, the SerpApi free tier), 60 and 150 (the two projects) and 20 (the service key); a placeholder vault credential that is never validated; four API keys (`test`, `live`, a `service` principal with a 20-credit session cap, and a second-project `test` key) |

- The demo org is what the [reference demo](../product/demo.md) runs against
- **The bootstrap logs events, not secrets.** It never prints API keys, so a container that seeded itself has keys nobody has seen. To get them, reset the demo org by hand (below)

## Three things make this safe to leave on

### 1. An advisory lock

- **Without it, several replicas starting together would race:** two concurrent `alembic upgrade head` runs on one database, or two seeds inserting the same demo organization

```python
MIGRATION_LOCK_KEY = 0x5E89_F10C_0001
SEED_LOCK_KEY      = 0x5E89_F10C_0002
```

- **One process takes a PostgreSQL advisory lock (`pg_advisory_lock`); the rest block** until it is done, then find the work already complete. Several replicas are how [production](../deployment/production.md#scaling) runs the API
- **The keys are fixed constants, not hashes:** advisory locks share one 64-bit namespace with everything else on the database
- **Blocking rather than skipping is deliberate:** a replica that skipped would start serving against a schema still being changed
- **Session-scoped, on a dedicated connection, released in a `finally`:** a process that dies mid-migration frees it when its connection drops
- **The two keys are distinct**, so seeding never blocks migrating
- **This is why migration moved out of the Dockerfile's `CMD`:** a shell `alembic upgrade head && exec ...` in front of the server cannot take a lock that outlives it

### 2. Idempotence

The seed checks before it writes:

```python
if await catalog_is_projected(session): ...     # count of catalog_engines for this version
if await benchmarks_are_loaded(session): ...    # count of benchmark_tasks for suite v1
if await demo_org_exists(session): ...          # the demo slug
```

- The tables are [`catalog_engines`](../database/schema.md#catalog-projection), [`benchmark_tasks`](../database/schema.md#benchmark) and [`organizations`](../database/schema.md#identity)
- **A new catalog version counts as "not projected"**, so bumping the catalog version re-projects it on the next start

- **A populated database costs three `SELECT count(*)` queries**, and no writes
- **A half-seeded one is completed, not duplicated:** if the catalog loaded but the process died before the demo org, the next start creates only the demo org
- Asserted against a real database in [`tests/integration/test_bootstrap_seed.py`](../../backend/tests/integration/test_bootstrap_seed.py), which seeds three times in a row and compares row counts

### 3. An environment refusal

`SEED_ON_STARTUP` is **ignored** when `ENVIRONMENT` is `staging` or `production` (`Settings.seeding_permitted` in [`app/core/config.py`](../../backend/app/core/config.py) allows only `local` and `dev`):

```json
{"event": "bootstrap.seed_refused", "environment": "production"}
```

- **The seed creates demo accounts whose password is committed to this repository:** right for a laptop, indefensible in a deployed environment
- So the refusal lives **in the settings**, not in whoever writes the manifest
- **A warning, not an error:** the service carries on serving
- **Migrations are not refused anywhere.** Running them in production is a legitimate, common deployment strategy, and the [deployment guide](../deployment/deployment-guide.md#4-configure-the-environment) sets it to `true` with `SEED_ON_STARTUP=false`

## Failure behaviour

- **A migration or seed failure is fatal:** the lifespan raises and the container exits
  - intentional: a service that silently starts against an un-migrated database fails later, on a query, in a way that is much harder to read than a refusal to boot
- **Exception: missing benchmark fixtures are logged and skipped**

```json
{"event": "seed.benchmarks_skipped"}
```

- The benchmark suite is reference data behind one dashboard. Nothing about serving a search depends on it
- **Exception: no `alembic.ini` next to the app** skips migrations with a warning instead of failing

```json
{"event": "bootstrap.migrations_skipped", "path": "/app/alembic.ini"}
```

- The backend image copies `alembic.ini` and `alembic/`, so this only happens in a hand-built image that left them out
- A `connection refused` here is the database not being up yet: [troubleshooting](troubleshooting.md#connection-refused-on-5432)

## Seeding by hand

The same code backs [`make seed`](../deployment/local.md#first-run):

```bash
make seed                       # seed everything, print accounts and API keys
make seed ARGS=--reset          # delete the demo org, recreate it, print fresh keys
make seed ARGS=--if-absent      # exactly what the startup bootstrap does
```

In a container:

```bash
docker compose exec backend python scripts/seed.py --reset
```

- **Keys are printed only when the demo org is created.** Against a database the bootstrap already seeded, plain `make seed` re-projects the catalog and says *Demo organization already present*; use `ARGS=--reset` to get keys you can see
- **`--reset` deletes the demo org and both demo users**, which removes their audit rows through [`AuditService.allow_purge`](../adr/0012-append-only-audit-log.md#the-exception-and-why-it-exists), the one sanctioned way past the append-only trigger
- **The printed `test` key is the one to export as `SERPFLOW_API_KEY`** for the [CLI](../sdks/cli.md) and the [Python SDK](../sdks/python.md#install). They read it from the shell, not from `.env` (the *CLI, SDK and MCP* block of `.env.example`; see [secrets](../security/secrets.md)):

```bash
export SERPFLOW_API_KEY=sf_test_...   # routes to the deterministic mock, spends 0 SerpApi credits
```

- The `service` key is the one for the [MCP server](../sdks/mcp.md#connect-a-client); the `live` key needs a real credential in the vault ([bring your own key](../security/byok.md)). See [SDKs: test keys](../sdks/overview.md#test-keys)
- **The implementation lives in `app/db/seed.py`**, not in `scripts/`, so both callers share it
- [`backend/scripts/seed.py`](../../backend/scripts/seed.py) is the command line around it

## Logging note

- **Alembic's `env.py` calls `fileConfig()`, which disables every existing logger by default**
  - run in-process, that would silence the application's own logging for the rest of the process, including whatever error came next

```python
config.attributes["configure_logger"] = False
```

- [`alembic/env.py`](../../backend/alembic/env.py) honours that, and passes `disable_existing_loggers=False` when it does configure logging
- **Not theoretical:** it hid a real startup failure behind a silent exit during development
- **Alembic runs in a worker thread** (`asyncio.to_thread`): its online path calls `asyncio.run` itself, which cannot happen on the running event loop
- The application's logging setup is described in [observability](observability.md#logging)

## Related

- [Migrations](../database/migrations.md#the-revision-chain): the revisions `alembic upgrade head` applies on start
- [Docker](../deployment/docker.md#running): the compose stack that sets both variables to `true`
- [Deployment guide](../deployment/deployment-guide.md#7-build-and-start): watching `bootstrap.migrations_done` on a server
- [Production](../deployment/production.md#scaling): the multi-replica case the advisory lock exists for
- [Local development](../deployment/local.md#first-run): `make seed` and the keys it prints
- [Secrets](../security/secrets.md#inventory): `ENVIRONMENT`, the two bootstrap flags and `SERPFLOW_API_KEY`
- [ADR 0012](../adr/0012-append-only-audit-log.md#the-exception-and-why-it-exists): why `--reset` has to opt in to deleting audit rows
- [Troubleshooting](troubleshooting.md#connection-refused-on-5432): when the database is not up yet at boot

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Secrets](../security/secrets.md) | [Docs index](../README.md) | [Email](../operations/email.md) |
