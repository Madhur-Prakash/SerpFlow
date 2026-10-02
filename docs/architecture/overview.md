# Architecture overview

SerpFlow sits between an application and SerpApi. It takes a
natural-language intent, decides which engine or chain of engines answers it,
works out what that would cost given what is already cached, and executes only
the parts that still need a live call.

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

Both the planner and the executor talk to the same `CacheService`, but through
different doors, and the difference is the product:

- **`inspect()`** answers "is this step satisfiable without spending?" *before*
  the plan is chosen. The planner calls it for every step of every candidate.
- **`lookup()`** is what the executor calls when it is about to run a step.

Executor-level caching alone would save credits on the plan you already picked.
Inspection at planning time changes **which plan you pick**.

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
| Workers | Kafka producers and consumers for background work only | [`app/workers/`](../../backend/app/workers) |

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

A Redis restart repopulates lazily from the durable index. No credits are lost
and no durable state is destroyed, which is why the hot layer can be
aggressive about eviction.

Interactive search is **never** routed through Kafka. `POST /v1/search`
executes in-process and streams stage progress over SSE; routing an interactive
request through a broker would add latency and a failure mode for no benefit.

## Execution modes

```
1. A `test` API key ALWAYS routes to the deterministic mock, regardless of
   SERPFLOW_MODE. Absolute, and not overridable.

2. For `live` API keys, SERPFLOW_MODE decides:
     live    normal billable execution against SerpApi
     record  execute live AND persist cassettes
     replay  serve from cassettes only; fail loudly on a miss
```

Resolution lives in one function,
[`resolve_mode`](../../backend/app/integrations/serpapi/__init__.py), and the
resolved mode travels on every response as `X-SerpFlow-Mode` and is displayed
in the UI at all times. Replay never reaches the network: a miss raises
`REPLAY_CASSETTE_MISS` naming the exact file that is absent.

## Tenancy

```
Organization
 |- Projects
 |   |- Members          per-project role override
 |   |- API Keys         sf_<env>_<project prefix>_<secret>
 |   `- optional Credential
 `- Default Credential
```

Credentials resolve project first, then the organization default, then refuse
with `NO_UPSTREAM_CREDENTIAL`. Small organizations configure one credential;
organizations with several SerpApi accounts override per project or cost
centre.

Every tenant-scoped query is guarded twice: application checks in
[`deps.py`](../../backend/app/api/deps.py), and PostgreSQL row-level security
keyed on `app.current_org` as a backstop. See [RLS](../database/rls.md).

## What makes this different from a cache

A cache in front of SerpApi saves you money on requests you have made before.
That is worth having, and SerpFlow does it.

The thing SerpFlow does that a cache cannot is change the plan. Given an intent
with several valid routes, it costs each one against current cache state and
picks the cheapest route *on the margin*, which is frequently not the cheapest
route in the abstract:

```
Plan A    cold 4 credits    marginal 4 credits
Plan B    cold 8 credits    marginal 1 credit     <- selected
```

A planner that only compared cold costs picks A and pays four credits to avoid
paying one. See [marginal replanning](marginal-replanning.md).

## Reading further

- [Backend](backend.md) - module map, request lifecycle, error model
- [Frontend](frontend.md) - the control plane UI
- [Catalog](catalog.md) - how the engine catalog is authored and loaded
- [Planner](planner.md) - stages A through D in detail
- [Marginal replanning](marginal-replanning.md) - the cost model
- [Executor](executor.md) - execution order and credential handling
- [Caching](caching.md) - four layers, the guard, adaptive TTL
