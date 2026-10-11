# Database

<p>
  <a href="../README.md#database"><img alt="docs: Database" src="https://img.shields.io/badge/docs-Database-4169E1?logo=readthedocs&logoColor=white"></a>
  <img alt="pages: 3" src="https://img.shields.io/badge/pages-3-4169E1">
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [Database](../README.md#database) › **Database** · page 34 of 50

**What SerpFlow keeps in PostgreSQL, how that schema changes, and how tenants are kept apart inside it.**

- **After reading it you can find any of the 33 tables and why its indexes exist,** run or write an Alembic revision that keeps tenant isolation, and prove that row-level security binds on your server
- **For anyone writing a migration, reading rows in `make psql`, or hardening a deployment.** Each table has its own heading in the [schema](schema.md), so `schema.md#runs` (or any other table name) links straight to it
- **Row-level security binds only when the connecting role lets it.** The tables' owner bypasses it unless they are forced, and a superuser, or a role with `BYPASSRLS`, bypasses it always, `FORCE` included. The compose stack connects as a superuser, so locally the policies exist but do not bind ([verifying it](rls.md#verifying-it))
- **New here? Read the [schema](schema.md) first**, then [how row-level security works](rls.md#how-it-works)

## Pages

| # | Page | Read it to |
| --- | --- | --- |
| 1 | [Database schema](schema.md) | find any of the 33 tables, its key columns and indexes, and the page that explains its behaviour |
| 2 | [Migrations](migrations.md) | run, write or roll back an Alembic revision, and know what each of the four revisions did |
| 3 | [Row-level security](rls.md) | see how 24 tables are tenant-isolated, what bypasses the policies, and how to check that they bind |

## Questions this section answers

| If you want to know | Go to |
| --- | --- |
| How an API key is found from its plaintext without scanning every key | [Schema: `api_keys`](schema.md#api_keys) |
| Whether any column holds a SerpApi key that could be read back | [Schema: `upstream_credentials`](schema.md#upstream_credentials) |
| Where a plan records that cache state changed which candidate won | [Schema: `plans`](schema.md#plans) |
| Why the losing candidate plans are stored too | [Schema: `plan_candidates`](schema.md#plan_candidates) |
| Which index a semantic cache lookup uses, and why the partition filter comes first | [Schema: `cache_entries`](schema.md#cache_entries) |
| With a shared cache, which project is charged and which is credited | [Schema: `budget_ledger`](schema.md#budget_ledger) |
| How to migrate to head, generate a revision or roll one back | [Migrations: commands](migrations.md#commands) |
| What each of the four revisions added | [Migrations: the revision chain](migrations.md#the-revision-chain) |
| What autogenerate will not write for you | [Migrations: writing a new revision](migrations.md#writing-a-new-revision) |
| How to reset the demo data, or start from an empty database | [Migrations: resetting](migrations.md#resetting) |
| Why a policy lets rows through when no tenant is set | [Row-level security: the empty-value clause](rls.md#the-empty-value-clause) |
| Which tables have no policy, and why | [Row-level security: covered tables](rls.md#covered-tables) |
| Why another organization's id is `404`, not `403` | [Row-level security: the application guards](rls.md#the-application-guards) |
| How to add a tenant-scoped table without leaving it unprotected | [Row-level security: adding a table](rls.md#adding-a-table) |
| Whether the policies bind on your server, and why they do not on the compose stack | [Row-level security: verifying it](rls.md#verifying-it) |
| Why an audit row cannot be updated, and when one can be deleted | [Row-level security: the audit log](rls.md#the-audit-log) |

## Where this section meets the others

| Section | The connection |
| --- | --- |
| [Product](../product/README.md) | a check constraint on `projects.execution_mode` is part of why `mock` cannot be selected ([execution modes](../product/execution-modes.md#why-mock-is-not-selectable)); a benchmark run from the UI lands in the [benchmark tables](schema.md#benchmark), which hold no tenant data ([benchmark: running it](../product/benchmark.md#running-it)) |
| [Deployment](../deployment/README.md) | [deployment guide, step 8](../deployment/deployment-guide.md#8-make-row-level-security-bind) and [production: before anything else](../deployment/production.md#before-anything-else) make RLS bind with a role that is not a superuser; [Docker: PostgreSQL](../deployment/docker.md#postgresql) creates the extensions and the empty `app.current_org` default; [step 14](../deployment/deployment-guide.md#14-upgrades-and-rollback) migrates a running server |
| [Architecture](../architecture/README.md) | [data stores](../architecture/overview.md#data-stores-and-what-each-is-for) names PostgreSQL the source of truth; the [planner](../architecture/planner.md#what-the-plan-stores), [executor](../architecture/executor.md#per-step-record) and [caching](../architecture/caching.md#partitioning) pages explain what writes `plans`, `steps` and `cache_entries`; [backend: identifiers](../architecture/backend.md#identifiers) defines the prefixed ULIDs |
| [API](../api/README.md) | [governance](../api/overview.md#governance): the savings waterfall sums `budget_ledger`, and `/verify` walks the `audit_log` hash chain; [errors](../api/overview.md#errors): a cross-tenant id is `NOT_FOUND` because of the application guards |
| [SDKs](../sdks/README.md) | the MCP server connects to this database directly, not to the API, and needs it migrated and seeded ([MCP: how it runs](../sdks/mcp.md#how-it-runs)); each agent session it opens is a [`service_sessions`](schema.md#service_sessions) row ([sessions and budgets](../sdks/mcp.md#sessions-and-budgets)) |
| [Security](../security/README.md) | [threat model: assets](../security/threat-model.md#assets) maps each asset to its table, and [cross-tenant data access](../security/threat-model.md#cross-tenant-data-access) is the threat RLS answers; [envelope encryption](../security/credentials.md#envelope-encryption) and [key resolution](../security/api-keys.md#resolution) are the behaviour behind `upstream_credentials` and `api_keys` |
| [Operations](../operations/README.md) | the [startup bootstrap](../operations/bootstrap.md#1-an-advisory-lock) can migrate on start, under an advisory lock; [troubleshooting: database](../operations/troubleshooting.md#database) covers `type "vector" does not exist` and the append-only error; [Redis](../operations/redis.md#why-none-of-it-is-authoritative) sits in front of PostgreSQL, not instead of it: lose Redis, and the durable cache index and key resolution still answer from here |
| [Decisions](../adr/README.md) | ADR 0006 and 0012 are implemented in [row-level security](rls.md); ten more bear on single tables, a revision or the driver, listed below |

## Related

- [Docs index](../README.md): every section, and the end-to-end reading order
- [Glossary](../product/glossary.md): every term in these pages, defined
- [SDKs](../sdks/README.md): the previous section, whose MCP server connects to this database directly
- [Security](../security/README.md): the next section, the threats these tables and policies answer
- [Deployment guide: make row-level security bind](../deployment/deployment-guide.md#8-make-row-level-security-bind): the role change production needs before the policies mean anything
- [Troubleshooting: database](../operations/troubleshooting.md#database): the database failures you are most likely to hit

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Releasing the SDKs](../sdks/releasing.md) | [Docs index](../README.md) | [Database schema](../database/schema.md) |
