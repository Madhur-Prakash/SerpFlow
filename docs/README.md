<div align="center">

<h1>SerpFlow documentation</h1>

<p align="center">
  Every page links to the implementation it describes.<br>
  If a path in these docs does not exist in the repository, that is a bug.
</p>

<p align="center">
  <a href="#read-it-end-to-end"><img alt="pages: 55" src="https://img.shields.io/badge/pages-55-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <a href="adr/README.md"><img alt="decision records: 14" src="https://img.shields.io/badge/decision%20records-14-555555"></a>
  <a href="api/overview.md"><img alt="API: 85 operations" src="https://img.shields.io/badge/API-85%20operations-009688?logo=fastapi&logoColor=white"></a>
  <a href="architecture/catalog.md"><img alt="catalog: 54 engines" src="https://img.shields.io/badge/catalog-54%20engines-2F6BFF"></a>
  <a href="product/benchmark.md"><img alt="routing accuracy 38.3%" src="https://img.shields.io/badge/routing%20accuracy-38.3%25-3fcf8e"></a>
  <a href="../backend/tests"><img alt="tests: 216 passing" src="https://img.shields.io/badge/tests-216%20passing-3fcf8e?logo=pytest&logoColor=white"></a>
  <a href="../LICENSE"><img alt="licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-D22128"></a>
</p>

<p align="center">
  <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="PostgreSQL 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka 4 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <img alt="React 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <img alt="TypeScript 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
</p>

<p align="center">
  <a href="#start-here">Start here</a> &middot;
  <a href="#product">Product</a> &middot;
  <a href="#deployment">Deployment</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#api">API</a> &middot;
  <a href="#database">Database</a> &middot;
  <a href="#security">Security</a> &middot;
  <a href="#operations">Operations</a> &middot;
  <a href="#decisions">Decisions</a>
</p>

</div>

> **These pages are also served by the running app at `/docs`**, with a sidebar, filtering and on-page contents.
> The API reference at **`/api`** is generated from the OpenAPI schema, not written by hand.

## Start here

| If you want to | Read |
| --- | --- |
| Understand what this is and why | [Product overview](product/product-overview.md) |
| **Install it, step by step** | [**Installation**](deployment/installation.md) |
| **Put it on a server** | [**Deployment guide**](deployment/deployment-guide.md) |
| See the central claim proved | [Demo walkthrough](product/demo.md) |
| Call the API | [API overview](api/overview.md) |
| Understand the design | [Architecture overview](architecture/overview.md) |
| Know why something is the way it is | [Decision records](adr/README.md) |
| Fix something | [Troubleshooting](operations/troubleshooting.md) |

## Read it end to end

**Every page ends with previous / index / next links in this order**, and opens with a badge header and a breadcrumb. Start at [Product overview](product/product-overview.md) and keep pressing **Next**.

1. **Product:** [overview](product/product-overview.md) → [demo](product/demo.md) → [execution modes](product/execution-modes.md) → [benchmark](product/benchmark.md)
2. **Deployment:** [installation](deployment/installation.md) → [local](deployment/local.md) → [docker](deployment/docker.md) → [deployment guide](deployment/deployment-guide.md) → [production](deployment/production.md)
3. **Architecture:** [overview](architecture/overview.md) → [catalog](architecture/catalog.md) → [planner](architecture/planner.md) → [marginal replanning](architecture/marginal-replanning.md) → [caching](architecture/caching.md) → [executor](architecture/executor.md) → [backend](architecture/backend.md) → [frontend](architecture/frontend.md) → [web](architecture/web.md)
4. **API:** [overview](api/overview.md) → [streaming](api/streaming.md) → [examples](api/examples.md)
5. **Database:** [schema](database/schema.md) → [migrations](database/migrations.md) → [RLS](database/rls.md)
6. **Security:** [threat model](security/threat-model.md) → [BYOK](security/byok.md) → [credentials](security/credentials.md) → [API keys](security/api-keys.md) → [secrets](security/secrets.md)
7. **Operations:** [bootstrap](operations/bootstrap.md) → [email](operations/email.md) → [observability](operations/observability.md) → [kafka](operations/kafka.md) → [redis](operations/redis.md) → [troubleshooting](operations/troubleshooting.md)
8. **Decisions:** [index](adr/README.md) → ADR [0001](adr/0001-marginal-cost-replanning.md) to [0014](adr/0014-persist-every-candidate.md)

- **The navigation is generated:** run `make docs-nav` after adding or renaming a page, and `make docs-check` to verify every link

## Product

| Page | Covers |
| --- | --- |
| [Product overview](product/product-overview.md) | the problem, the thesis, the boundaries |
| [Demo](product/demo.md) | the reference scenario, step by step |
| [Execution modes](product/execution-modes.md) | live, record, replay; who chooses and in what order |
| [Benchmark](product/benchmark.md) | 120 labelled tasks, measured results, error analysis |

## Deployment

| Page | Covers |
| --- | --- |
| [**Installation**](deployment/installation.md) | prerequisites per OS, developer and Docker installs, verifying it, uninstalling |
| [Local development](deployment/local.md) | everyday targets, modes, real keys, proving the thesis |
| [Docker](deployment/docker.md) | images, compose, profiles, listeners, the `/docs` known issue |
| [**Deployment guide**](deployment/deployment-guide.md) | a 15-step runbook: server, secrets, ports, TLS, first admin, backups, upgrades |
| [Production](deployment/production.md) | scaling, pooling, hardening, zero-downtime deploys |

## Architecture

| Page | Covers |
| --- | --- |
| [Overview](architecture/overview.md) | how the pieces fit together |
| [Catalog](architecture/catalog.md) | 54 engines, dependency edges, substitute edges |
| [Planner](architecture/planner.md) | the four stages, retrieval through candidate generation |
| [Marginal replanning](architecture/marginal-replanning.md) | the thesis, in detail |
| [Caching](architecture/caching.md) | four layers, the guard, adaptive TTL |
| [Executor](architecture/executor.md) | execution, modes, provenance |
| [Backend](architecture/backend.md) | FastAPI structure, services, sessions |
| [Frontend](architecture/frontend.md) | React, the pipeline, the inspectors |
| [Web surface](architecture/web.md) | the landing page, docs browser, theme and motion |

## API

| Page | Covers |
| --- | --- |
| [Overview](api/overview.md) | authentication, all 85 operations, errors, headers |
| [Streaming](api/streaming.md) | the SSE contract, stages, reconnection |
| [Examples](api/examples.md) | worked requests, SDKs, CLI, MCP, the SerpApi drop-in |

## Database

| Page | Covers |
| --- | --- |
| [Schema](database/schema.md) | 33 tables, indexes, conventions |
| [Migrations](database/migrations.md) | Alembic, the four-revision chain, writing one |
| [Row-level security](database/rls.md) | tenant isolation on 24 tables, policies, the audit trigger |

## Security

| Page | Covers |
| --- | --- |
| [Threat model](security/threat-model.md) | assets, boundaries, threats, what is out of scope |
| [Bring your own key](security/byok.md) | which keys you supply, what each does, what happens without them |
| [Credentials](security/credentials.md) | envelope encryption, decryption boundary, rotation |
| [API keys](security/api-keys.md) | format, hashing, built-in and custom roles, service sessions |
| [Secrets](security/secrets.md) | the full inventory, generation, rotation, production checklist |

## Operations

| Page | Covers |
| --- | --- |
| [Bootstrap](operations/bootstrap.md) | migrations and seeding on startup, advisory locks |
| [Email](operations/email.md) | Gmail transport, templates, what gets sent |
| [Observability](operations/observability.md) | logs, 22 metrics, traces, alerting rules |
| [Kafka](operations/kafka.md) | eight topics, workers, degradation, listeners |
| [Redis](operations/redis.md) | what is in it, why none of it is authoritative |
| [Troubleshooting](operations/troubleshooting.md) | the failures you will actually hit |

## Decisions

- [Architecture decision records](adr/README.md): the 14 choices that were not obvious, each with the alternative rejected and the cost accepted

## Repository

| File | What it is |
| --- | --- |
| [README](../README.md) | the project overview, the product film, the evidence and the quick start |
| [Contributing](../CONTRIBUTING.md) | how to work on it, and what the bar is |
| [Security policy](../SECURITY.md) | how to report something, and who maintains it |
| [Changelog](../CHANGELOG.md) | what changed, and why |
| [SDKs](../sdk/README.md) | the TypeScript and Python clients |
| [Backend](../backend/README.md) | the backend package |
| [License](../LICENSE) | Apache-2.0 |

## Who maintains this

- **SerpFlow is built and maintained by one person, in their own time**
- It began as a hackathon entry, and grew into a full-scale project with production-ready development
- Support is best-effort: see [maintenance and support](../SECURITY.md#maintenance-and-support)

---

<div align="center">

<p align="center">
  <a href="../README.md">Project README</a> &middot;
  <a href="deployment/installation.md">Installation</a> &middot;
  <a href="deployment/deployment-guide.md">Deployment</a> &middot;
  <a href="architecture/overview.md">Architecture</a> &middot;
  <a href="api/overview.md">API</a> &middot;
  <a href="adr/README.md">Decisions</a> &middot;
  <a href="operations/troubleshooting.md">Troubleshooting</a>
</p>

<sub>&copy; 2026 SerpFlow. All rights reserved. Released under the Apache-2.0 licence.</sub>

</div>
