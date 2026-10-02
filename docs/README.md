# SerpFlow documentation

[![Docs](https://img.shields.io/badge/docs-complete-3fcf8e)](.)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128)](../LICENSE)

Every page here links to the implementation it describes. If a path in these
docs does not exist in the repository, that is a bug.

## Start here

| If you want to | Read |
| --- | --- |
| Understand what this is and why | [Product overview](product/product-overview.md) |
| Get it running | [Local development](deployment/local.md) |
| See the central claim proved | [Demo walkthrough](product/demo.md) |
| Call the API | [API overview](api/overview.md) |
| Understand the design | [Architecture overview](architecture/overview.md) |
| Know why something is the way it is | [Decision records](adr/README.md) |

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

## API

| Page | Covers |
| --- | --- |
| [Overview](api/overview.md) | authentication, endpoints, errors, headers |
| [Streaming](api/streaming.md) | the SSE contract, stages, reconnection |
| [Examples](api/examples.md) | worked requests, SDKs, CLI, MCP, the SerpApi drop-in |

## Database

| Page | Covers |
| --- | --- |
| [Schema](database/schema.md) | 33 tables, indexes, conventions |
| [Migrations](database/migrations.md) | Alembic, the revision chain, writing one |
| [Row-level security](database/rls.md) | tenant isolation, policies, the audit trigger |

## Security

| Page | Covers |
| --- | --- |
| [Threat model](security/threat-model.md) | assets, boundaries, threats, what is out of scope |
| [Credentials](security/credentials.md) | envelope encryption, decryption boundary, rotation |
| [API keys](security/api-keys.md) | format, hashing, roles, service sessions |
| [Secrets](security/secrets.md) | the full inventory, rotation, production checklist |

## Deployment

| Page | Covers |
| --- | --- |
| [Local](deployment/local.md) | prerequisites, first run, modes, proving the thesis |
| [Docker](deployment/docker.md) | images, compose, profiles, listeners |
| [Production](deployment/production.md) | scaling, hardening, zero-downtime deploys |

## Operations

| Page | Covers |
| --- | --- |
| [Bootstrap](operations/bootstrap.md) | migrations and seeding on startup, advisory locks |
| [Email](operations/email.md) | Gmail transport, templates, what gets sent |
| [Observability](operations/observability.md) | logs, metrics, traces, alerting rules |
| [Kafka](operations/kafka.md) | topics, workers, degradation, listeners |
| [Redis](operations/redis.md) | what is in it, why none of it is authoritative |
| [Troubleshooting](operations/troubleshooting.md) | the failures you will actually hit |

## Product

| Page | Covers |
| --- | --- |
| [Product overview](product/product-overview.md) | the problem, the thesis, the boundaries |
| [Benchmark](product/benchmark.md) | 120 labelled tasks, measured results, error analysis |
| [Demo](product/demo.md) | the reference scenario, step by step |

## Decisions

[Architecture decision records](adr/README.md) — the choices that were not
obvious, with the alternative that was rejected and the cost that was accepted.

## Repository

- [README](../README.md)
- [Contributing](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Changelog](../CHANGELOG.md)
- [SDKs](../sdk/README.md) — TypeScript and Python clients
- [License](../LICENSE) — Apache-2.0
