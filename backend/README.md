# SerpFlow backend

<p>
  <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="SQLAlchemy 2 async" src="https://img.shields.io/badge/SQLAlchemy-2%20async-D71F00?logo=sqlalchemy&logoColor=white">
  <img alt="PostgreSQL 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka 4 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <img alt="tests: 236 passing" src="https://img.shields.io/badge/tests-236%20passing-3fcf8e?logo=pytest&logoColor=white">
</p>

[README](../README.md) › **Backend** · [Docs index](../docs/README.md) · [Backend architecture](../docs/architecture/backend.md)

---

**The FastAPI control plane for SerpApi:** planner, cache-aware marginal-cost replanning, executor, budgets and provenance.

## Layout

| Path | What it is |
| --- | --- |
| [`app/`](app) | the application: API, services, models, workers, integrations, CLI, MCP, SDK. Module map: [backend architecture](../docs/architecture/backend.md#module-map) |
| [`alembic/`](alembic) | migrations, `0001` to `0004`: [the revision chain](../docs/database/migrations.md#the-revision-chain) |
| [`fixtures/`](fixtures) | the 120-task benchmark suite and its committed results. `record` mode writes cassettes under `fixtures/cassettes/`, which `replay` serves |
| [`scripts/`](scripts) | `seed.py`, `demo.py`, `catalog_build.py`, `mint_gmail_token.py` |
| [`tests/`](tests) | unit (208), integration (25) and e2e (3): 236 in total |
| [`serpflow.py`](serpflow.py) | re-exports the Python SDK as `from serpflow import SerpFlow`; it resolves with an editable install only: [Python SDK: install](../docs/sdks/python.md#install) |

## Run it

```bash
make install-backend     # from the repository root
make up && make upgrade && make seed
make backend             # python -m app.server --reload, on :8000
make test                # 236 tests
```

- **Start the server with `python -m app.server`**, not `uvicorn app.main:app`: see [ADR 0013](../docs/adr/0013-explicit-event-loop-factory.md)
- **Entry points:** `serpflow` (CLI, `app.cli.main`) and `serpflow-mcp` (MCP server, `app.mcp.server`): see [CLI](../docs/sdks/cli.md) and [MCP server](../docs/sdks/mcp.md)
- **Settings** come from the environment, then from `.env` and `../.env` relative to the working directory: [`app/core/config.py`](app/core/config.py). The secrets among them: [secrets](../docs/security/secrets.md#inventory)
- **Migrations and seeding can run on startup**, under an advisory lock: [startup bootstrap](../docs/operations/bootstrap.md)
- Everyday targets and modes: [local development](../docs/deployment/local.md)

## Where each part is documented

| Code | Page |
| --- | --- |
| [`app/api/`](app/api) | [API overview](../docs/api/overview.md) · [streaming](../docs/api/streaming.md) · [request lifecycle](../docs/architecture/backend.md#request-lifecycle) |
| [`app/services/runs.py`](app/services/runs.py) | [architecture overview](../docs/architecture/overview.md#the-shape-of-a-request) · [execution modes](../docs/product/execution-modes.md#who-chooses-and-precedence) |
| [`app/services/catalog/`](app/services/catalog) | [the engine catalog](../docs/architecture/catalog.md) |
| [`app/services/planner/`](app/services/planner) | [the planner](../docs/architecture/planner.md) · [marginal-cost replanning](../docs/architecture/marginal-replanning.md) |
| [`app/services/cache/`](app/services/cache) | [caching](../docs/architecture/caching.md) · [Redis](../docs/operations/redis.md) |
| [`app/services/executor/`](app/services/executor) | [the executor](../docs/architecture/executor.md) |
| [`app/services/budgets/`](app/services/budgets) | [budget enforcement](../docs/architecture/executor.md#budget-enforcement) |
| [`app/services/auth/`](app/services/auth) · [`roles/`](app/services/roles) | [API keys and roles](../docs/security/api-keys.md) |
| [`app/services/credentials/`](app/services/credentials) | [upstream credentials](../docs/security/credentials.md) · [bring your own key](../docs/security/byok.md) |
| [`app/services/audit/`](app/services/audit) | [the audit log](../docs/database/rls.md#the-audit-log) |
| [`app/services/email/`](app/services/email) · [`notifications/`](app/services/notifications) | [email](../docs/operations/email.md) · [alerting](../docs/operations/observability.md#alerting) |
| [`app/services/benchmark/`](app/services/benchmark) | [routing benchmark](../docs/product/benchmark.md) |
| [`app/services/stream.py`](app/services/stream.py) | [streaming: reconnecting](../docs/api/streaming.md#reconnecting) |
| [`app/workers/`](app/workers) | [Kafka](../docs/operations/kafka.md) |
| [`app/integrations/serpapi/`](app/integrations/serpapi) | [execution modes](../docs/product/execution-modes.md) |
| [`app/integrations/llm/`](app/integrations/llm) | [planner stage B](../docs/architecture/planner.md#stage-b-select) · [bring your own key](../docs/security/byok.md#what-happens-without-each-key) |
| [`app/db/`](app/db) | [schema](../docs/database/schema.md) · [migrations](../docs/database/migrations.md) · [row-level security](../docs/database/rls.md) · [bootstrap](../docs/operations/bootstrap.md) |
| [`app/core/`](app/core) | [observability](../docs/operations/observability.md) · [secrets](../docs/security/secrets.md) · [error model](../docs/architecture/backend.md#error-model) |
| [`app/sdk/`](app/sdk) · [`app/cli/`](app/cli) · [`app/mcp/`](app/mcp) | [SDKs and tools](../docs/sdks/overview.md) |

## Read more

- [Installation](../docs/deployment/installation.md)
- [Backend architecture](../docs/architecture/backend.md)
- [API overview](../docs/api/overview.md)
- [Database schema](../docs/database/schema.md)
- [Glossary](../docs/product/glossary.md): every term these pages use
- [Troubleshooting](../docs/operations/troubleshooting.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [TypeScript SDK](../sdk/typescript/README.md) | [Docs index](../docs/README.md) | [Project README](../README.md) |
