# SerpFlow backend

<p>
  <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="SQLAlchemy 2 async" src="https://img.shields.io/badge/SQLAlchemy-2%20async-D71F00?logo=sqlalchemy&logoColor=white">
  <img alt="PostgreSQL 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka 4 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <img alt="tests: 216 passing" src="https://img.shields.io/badge/tests-216%20passing-3fcf8e?logo=pytest&logoColor=white">
</p>

[README](../README.md) › **Backend** · [Docs index](../docs/README.md) · [Backend architecture](../docs/architecture/backend.md)

---

**The FastAPI control plane for SerpApi:** planner, cache-aware marginal-cost replanning, executor, budgets and provenance.

## Layout

| Path | What it is |
| --- | --- |
| [`app/`](app) | the application: API, services, models, workers, integrations, CLI, MCP, SDK |
| [`alembic/`](alembic) | migrations, `0001` to `0004` |
| [`fixtures/`](fixtures) | the 120-task benchmark suite, committed results, replay cassettes |
| [`scripts/`](scripts) | `seed.py`, `demo.py`, `catalog_build.py`, `mint_gmail_token.py` |
| [`tests/`](tests) | unit (188), integration and e2e: 216 in total |
| [`serpflow.py`](serpflow.py) | re-exports the Python SDK as `from serpflow import SerpFlow` |

## Run it

```bash
make install-backend     # from the repository root
make up && make upgrade && make seed
make backend             # python -m app.server --reload, on :8000
make test                # 216 tests
```

- **Start the server with `python -m app.server`**, not `uvicorn app.main:app`: see [ADR 0013](../docs/adr/0013-explicit-event-loop-factory.md)
- **Entry points:** `serpflow` (CLI, `app.cli.main`) and `serpflow-mcp` (MCP server, `app.mcp.server`)

## Read more

- [Installation](../docs/deployment/installation.md)
- [Backend architecture](../docs/architecture/backend.md)
- [API overview](../docs/api/overview.md)
- [Database schema](../docs/database/schema.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [TypeScript SDK](../sdk/typescript/README.md) | [Docs index](../docs/README.md) | [Project README](../README.md) |
