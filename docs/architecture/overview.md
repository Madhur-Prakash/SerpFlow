# Architecture overview

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="FastAPI: 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka: 4.0 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <img alt="React: 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <a href="../../backend/app/api"><img alt="source: app/api" src="https://img.shields.io/badge/source-app%2Fapi-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **Architecture overview** · page 10 of 50

**SerpFlow sits between an application and SerpApi.** For each natural-language intent it:

- decides which engine, or chain of engines, answers it
- works out what that would cost, given what is already cached
- executes only the parts that still need a live call

## The shape of a request

```
                    POST /v1/search
                          |
                          v
   +----------------------------------------------+
   |  app/api/v1/search.py                         |   authenticate, resolve
   |  app/api/deps.py                              |   principal, scope the
   +----------------------------------------------+   transaction to org_id
                          |
                          v
   +----------------------------------------------+
   |  app/services/runs.py                         |   the one place a plan
   |  plan_and_execute()                           |   becomes a run
   +----------------------------------------------+
            |                             |
            v                             v
   +------------------+          +--------------------+
   | PlannerService   |          | ExecutorService    |
   | stages A-D       |          | exact -> semantic  |
   | marginal cost    |          | -> archive -> live |
   | budget reduction |          |                    |
   +------------------+          +--------------------+
            |                             |
            v                             v
   +------------------+          +--------------------+
   | CacheService     |<---------| SerpApiGateway     |
   | inspect()        |  store   | live/mock/replay   |
   | lookup()         |          |                    |
   +------------------+          +--------------------+
            |
            v
   Redis  |  PostgreSQL + pgvector  |  object storage
```

The planner and the executor share one `CacheService`, through **different doors**, and the difference is the product:

- **`inspect()`:** "is this step satisfiable without spending?" asked **before** the plan is chosen, for every step of every candidate
- **`lookup()`:** what the executor calls when it is about to run a step

> Executor-level caching alone saves credits on the plan you already picked.
> Inspection at planning time changes **which plan you pick**.

## Layers

| Layer | Responsibility | Code |
| --- | --- | --- |
| API | HTTP, authentication, authorization, provenance headers, error envelope | [`app/api/`](../../backend/app/api) |
| Orchestration | Plan then execute, in one place for REST, MCP, CLI and workers | [`app/services/runs.py`](../../backend/app/services/runs.py) |
| Planner | Retrieval, selection, synthesis, path-finding, cost model, budget | [`app/services/planner/`](../../backend/app/services/planner) |
| Executor | Four-layer execution, credential decryption, fan-out binding | [`app/services/executor/`](../../backend/app/services/executor) |
| Cache | Keys, guard, exact, semantic, archive, adaptive TTL | [`app/services/cache/`](../../backend/app/services/cache) |
| Catalog | Loading, the typed dependency graph, capability vocabulary | [`app/services/catalog/`](../../backend/app/services/catalog) |
| Governance | Budgets, analytics, audit, benchmark, auth, credentials | [`app/services/`](../../backend/app/services) |
| Integrations | SerpApi (real, mock, cassettes), LLM, object storage | [`app/integrations/`](../../backend/app/integrations) |
| Workers | Kafka producers and consumers, background work only | [`app/workers/`](../../backend/app/workers) |

## Data stores, and what each is for

```
PostgreSQL 17 + pgvector    source of truth
                            identity, plans, candidates, runs, steps,
                            the durable cache index, embeddings, budgets,
                            the audit chain, benchmark results

Redis                       hot cache, NOT the source of truth
                            exact-layer lookups, 60-second principal cache,
                            rate limit counters, SSE event mirror

Object storage              large SERP payloads, content addressed
                            filesystem by default, S3 or MinIO when configured

Kafka 4.x (KRaft)           background work only
                            scheduled runs, bulk operations, retries,
                            cache refresh, credential validation, analytics,
                            alerts, webhooks, quota reconciliation
```

- **A Redis restart repopulates lazily** from the durable index
  - no credits are lost, no durable state is destroyed
  - which is why the hot layer can evict aggressively
- **Interactive search never goes through Kafka**
  - `POST /v1/search` executes in-process and streams stage progress over SSE
  - a broker in that path would add latency and a failure mode for no benefit

## Execution modes

Most specific wins:

```
1. A `test` API key ALWAYS routes to the deterministic mock.
   Absolute, and not overridable.
2. Per-request `mode` on /v1/search or /v1/plan
3. The project's own execution mode
4. SERPFLOW_MODE, the instance default:
     live    normal billable execution against SerpApi
     record  execute live AND persist cassettes
     replay  serve from cassettes only; fail loudly on a miss (the default)
```

- **Rules 2-4 resolve in one function:** [`resolve_execution_mode`](../../backend/app/services/runs.py)
- **The gateway applies the result:** [`resolve_mode`](../../backend/app/integrations/serpapi/__init__.py), where rule 1 is enforced
- **The resolved mode travels on every response** as `X-SerpFlow-Mode`, and is always shown in the UI
- **Replay never reaches the network:** a miss raises `REPLAY_CASSETTE_MISS`, naming the exact file that is absent
- More: [execution modes](../product/execution-modes.md)

## Tenancy

```
Organization
 |- Projects
 |   |- Members          per-project role override
 |   |- API Keys         sf_<env>_<project prefix>_<secret>
 |   `- optional Credential
 `- Default Credential
```

- **Credentials resolve** project first, then the organization default, then refuse with `NO_UPSTREAM_CREDENTIAL`
  - small organizations configure one credential
  - organizations with several SerpApi accounts override per project or cost centre
- **Every tenant-scoped query is guarded twice:**
  - application checks in [`deps.py`](../../backend/app/api/deps.py)
  - PostgreSQL row-level security keyed on `app.current_org`, as a backstop. See [RLS](../database/rls.md)

## What makes this different from a cache

- **A cache in front of SerpApi** saves money on requests you have made before. Worth having, and SerpFlow does it
- **What a cache cannot do is change the plan**
  - given an intent with several valid routes, SerpFlow costs each against current cache state
  - it picks the cheapest route **on the margin**, which is often not the cheapest route in the abstract

```
Plan A    cold 4 credits    marginal 4 credits
Plan B    cold 8 credits    marginal 1 credit     <- selected
```

- A planner comparing only cold costs picks A, and **pays four credits to avoid paying one**
- More: [marginal replanning](marginal-replanning.md)

## Reading further

- [Catalog](catalog.md): how the engine catalog is authored and loaded
- [Planner](planner.md): stages A through D in detail
- [Marginal replanning](marginal-replanning.md): the cost model
- [Caching](caching.md): four layers, the guard, adaptive TTL
- [Executor](executor.md): execution order and credential handling
- [Backend](backend.md): module map, request lifecycle, error model
- [Frontend](frontend.md): the control plane UI
- [Web surface](web.md): the landing page, docs browser, theme and motion

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Production](../deployment/production.md) | [Docs index](../README.md) | [The engine catalog](../architecture/catalog.md) |
