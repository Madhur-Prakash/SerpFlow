# Architecture overview

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="FastAPI: 0.118" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka: 4.0 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <img alt="React: 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <a href="../../backend/app/services/runs.py"><img alt="source: services/runs.py" src="https://img.shields.io/badge/source-services%2Fruns.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 9 min" src="https://img.shields.io/badge/read-9%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **Architecture overview** · page 11 of 57

**SerpFlow sits between an application and SerpApi.** For each natural-language intent it:

- decides which engine, or chain of engines, answers it
- works out what that would cost, given what is already cached
- executes only the parts that still need a live call

The problem it solves, and what it deliberately does not do: [product overview](../product/product-overview.md). The terms used below: [glossary](../product/glossary.md).

## The shape of a request

```
      REST / SDKs / CLI                    MCP server, Kafka worker
              |                            (in-process, no HTTP hop)
              v                                       |
   +------------------------------------+             |
   |  app/api/v1/search.py              |             |
   |  app/api/deps.py                   |             |
   |  authenticate, resolve principal,  |             |
   |  scope the transaction to org_id   |             |
   +------------------------------------+             |
              |                                       |
              v                                       v
   +--------------------------------------------------------------+
   |  app/services/runs.py   plan_and_execute()                    |   the one place
   |  mode, project, budget, credential, adapter                   |   a plan becomes a run
   +--------------------------------------------------------------+
            |                             |
            v                             v
   +------------------+          +--------------------+
   | PlannerService   |          | ExecutorService    |
   | stages A-D       |          | exact -> semantic  |
   | marginal cost    |          | -> archive -> live |
   | budget reduction |          |                    |
   +------------------+          +--------------------+
            |                       |              |
            | inspect()    lookup() |              | search()
            |              store()  |              |
            v                       v              v
   +---------------------------------------+   +--------------------+
   | CacheService                          |   | SerpApiGateway     |
   | same partition, same stores           |   | live / record /    |
   +---------------------------------------+   | replay / mock      |
            |                                  +--------------------+
            v
   Redis  |  PostgreSQL + pgvector  |  object storage
```

- **The SDKs and CLI call the REST API; the MCP server runs these services in-process** against the database. See [how they connect](../sdks/overview.md#how-they-connect)
- **The Kafka worker** handles scheduled, bulk, retried and webhook-triggered runs only ([topics](../operations/kafka.md#topics))
- **Every surface lands in [`runs.py`](../../backend/app/services/runs.py)**: `plan_and_execute`, or `create_plan` to plan alone. No surface duplicates planner or executor logic

The planner and the executor read the same cache, built with the same partition scope and threshold, through **different doors**, and the difference is the product:

- **`inspect()`:** "is this step satisfiable without spending?" asked **before** the plan is chosen, for every step of every candidate
- **`lookup()`:** what the executor calls when it is about to run a step; **`store()`** writes a live result back
- Both, in detail: [two entry points](caching.md#two-entry-points)

> Executor-level caching alone saves credits on the plan you already picked.
> Inspection at planning time changes **which plan you pick**.

### Request lifecycle

What `POST /v1/search` does, in order ([`search.py`](../../backend/app/api/v1/search.py), [`runs.py`](../../backend/app/services/runs.py)):

1. **Authenticate and scope.** [`deps.py`](../../backend/app/api/deps.py) resolves the principal from an API key or a session token, checks the `execute` permission, rate-limits, and sets `app.current_org` so [row-level security](../database/rls.md) binds the transaction. The middleware around it: [backend request lifecycle](backend.md#request-lifecycle)
2. **Resolve the execution mode** (`resolve_execution_mode`): see [execution modes](#execution-modes) below
3. **Open a run.** A `runs` row is written with status `planning`, and the [SSE](../api/streaming.md) buffer for it starts
   - with `stream: true` the API returns `202` and a `stream_url` first, then carries on in-process: interactive search never goes through Kafka ([ADR 0007](../adr/0007-interactive-search-bypasses-kafka.md))
4. **Plan** (`create_plan`): the tightest remaining [budget](../database/schema.md#governance), a cache scoped to the project's [partition](caching.md#partitioning), the organization's [planning adapter](planner.md#which-adapter-plans), then the [planner](planner.md). The `plans` and `plan_candidates` rows are written; ten stage frames stream as it goes
5. **Resolve the credential**, for `live` and `record` only: project, then organization default, else `NO_UPSTREAM_CREDENTIAL`, before anything is spent
6. **Execute.** The [executor](executor.md) runs each step through the four layers, writing `steps`, ledger and cache rows, and streams `executing` frames
7. **Record and finish.** Any routing saving goes to the ledger, a service session's usage is updated, `run.executed` is [audited](../database/rls.md#the-audit-log), and the stream closes with `complete`. The response carries [provenance headers](../api/overview.md#provenance-headers)

- **A failure at any step** marks the run `failed` with its error code, and the stream closes with an `error` frame
  - the request's transaction rolls back, so a failed run's plan, steps, ledger and cache writes are not kept
  - a streamed run's row is re-marked `failed` in a fresh transaction, so the search page can show the error and link to the [Run Inspector](frontend.md#routes). Details: [when a run fails](executor.md#when-a-run-fails)
- **`POST /v1/plan` runs steps 1, 2 and 4 only:** no run row, no credential, nothing spent ([plan without executing](../api/overview.md#plan-without-executing))

## Layers

| Layer | Responsibility | Code | Read more |
| --- | --- | --- | --- |
| API | HTTP, authentication, authorization, provenance headers, error envelope, SSE | [`app/api/`](../../backend/app/api) | [API overview](../api/overview.md), [streaming](../api/streaming.md) |
| Orchestration | Plan then execute, in one place for REST, MCP, CLI and workers | [`app/services/runs.py`](../../backend/app/services/runs.py) | [request lifecycle](#request-lifecycle) |
| Planner | Retrieval, selection, synthesis, path-finding, cost model, budget | [`app/services/planner/`](../../backend/app/services/planner) | [the planner](planner.md), [marginal replanning](marginal-replanning.md) |
| Executor | Four-layer execution, credential decryption, fan-out binding | [`app/services/executor/`](../../backend/app/services/executor) | [the executor](executor.md) |
| Cache | Keys, guard, exact, semantic, archive, adaptive TTL | [`app/services/cache/`](../../backend/app/services/cache) | [caching](caching.md) |
| Catalog | Loading, the typed dependency graph, capability vocabulary | [`app/services/catalog/`](../../backend/app/services/catalog) | [the engine catalog](catalog.md) |
| Governance | Budgets, analytics, audit, benchmark, auth, credentials | [`app/services/`](../../backend/app/services) | [API keys](../security/api-keys.md), [credentials](../security/credentials.md), [benchmark](../product/benchmark.md) |
| Integrations | SerpApi (real, mock, cassettes), LLM, object storage | [`app/integrations/`](../../backend/app/integrations) | [execution modes](../product/execution-modes.md), [bring your own key](../security/byok.md) |
| Workers | Kafka producers and consumers, background work only | [`app/workers/`](../../backend/app/workers) | [Kafka](../operations/kafka.md) |
| Console | The control plane UI: search, inspectors, dashboards | [`frontend/src/`](../../frontend/src) | [frontend](frontend.md), [web surface](web.md) |
| Clients | Python and TypeScript SDKs, the CLI, the MCP server | [`app/sdk/`](../../backend/app/sdk), [`sdk/typescript/`](../../sdk/typescript), [`app/cli/`](../../backend/app/cli), [`app/mcp/`](../../backend/app/mcp) | [SDKs and tools](../sdks/overview.md) |

- Package layout, sessions and the event loop: [backend](backend.md#module-map)

## Data stores, and what each is for

```
PostgreSQL 17 + pgvector    source of truth, 33 tables
                            identity, plans, candidates, runs, steps,
                            the durable cache index, embeddings, budgets,
                            the ledger, the audit chain, benchmark results

Redis                       hot cache, NOT the source of truth
                            exact-layer lookups, 60-second principal cache,
                            rate limit counters, SSE event mirror

Object storage              large SERP payloads, content addressed
                            filesystem by default, S3 or MinIO when configured

Kafka 4.x (KRaft)           background work only, 8 topics
                            scheduled runs, bulk operations, retries,
                            cache refresh, credential validation, analytics,
                            alerts, webhooks, quota reconciliation, catalog reload
```

| Store | Canonical page |
| --- | --- |
| PostgreSQL | [database schema](../database/schema.md), [migrations](../database/migrations.md), [row-level security](../database/rls.md) |
| Redis | [Redis](../operations/redis.md#what-lives-in-it) |
| Object storage | [caching: object storage](caching.md#object-storage) |
| Kafka | [Kafka topics](../operations/kafka.md#topics) |

- **A Redis restart repopulates lazily** from the durable index
  - no credits are lost, no durable state is destroyed
  - which is why the hot layer can evict aggressively. See [why none of it is authoritative](../operations/redis.md#why-none-of-it-is-authoritative)
- **Interactive search never goes through Kafka** ([ADR 0007](../adr/0007-interactive-search-bypasses-kafka.md))
  - `POST /v1/search` executes in-process and streams stage progress over [SSE](../api/streaming.md#the-stage-sequence)
  - a broker in that path would add latency and a failure mode for no benefit
- **Each dependency degrades on its own:** PostgreSQL is the only one whose loss fails readiness. See [degradation](backend.md#degradation)

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
- **The gateway applies the result:** [`resolve_mode`](../../backend/app/integrations/serpapi/__init__.py), where rule 1 is enforced ([ADR 0010](../adr/0010-test-key-mode-precedence.md))
- **A caller cannot ask for `mock`**, and asking for a billable mode needs `run:mode_override`: see [permission](../product/execution-modes.md#permission)
- **The resolved mode travels on every response** as `X-SerpFlow-Mode` ([provenance headers](../api/overview.md#provenance-headers)), and is always shown in the UI
- **Replay never reaches the network:** a miss raises `REPLAY_CASSETTE_MISS`, naming the exact file that is absent ([the fix](../operations/troubleshooting.md#replay_cassette_miss))
- More: [execution modes](../product/execution-modes.md), and running each one locally: [modes](../deployment/local.md#modes)

## Tenancy

```
Organization
 |- Projects
 |   |- Members          per-project role override
 |   |- API Keys         sf_<env>_<project prefix>_<secret>
 |   `- optional Credential
 `- Default Credential
```

- **API keys** carry their project and environment in the prefix: [key format](../security/api-keys.md#format). Roles and per-project overrides: [roles](../security/api-keys.md#roles)
- **Credentials resolve** project first, then the organization default, then refuse with `NO_UPSTREAM_CREDENTIAL` ([how a key is chosen](../security/byok.md#how-a-key-is-chosen-for-a-request))
  - small organizations configure one credential
  - organizations with several SerpApi accounts override per project or cost centre
  - stored under envelope encryption, decrypted only in the executor: [upstream credentials](../security/credentials.md)
- **Every tenant-scoped query is guarded twice** ([ADR 0011](../adr/0011-rls-plus-application-guards.md)):
  - application checks in [`deps.py`](../../backend/app/api/deps.py)
  - PostgreSQL row-level security keyed on `app.current_org`, as a backstop. See [RLS](../database/rls.md)
- What each boundary defends against: [threat model](../security/threat-model.md#trust-boundaries)

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
- More: [marginal replanning](marginal-replanning.md) ([ADR 0001](../adr/0001-marginal-cost-replanning.md)), and [the reference demo](../product/demo.md) that proves it with `make demo`

## Reading further

- [Catalog](catalog.md): how the engine catalog is authored and loaded
- [Planner](planner.md): stages A through D in detail
- [Marginal replanning](marginal-replanning.md): the cost model
- [Caching](caching.md): four layers, the guard, adaptive TTL
- [Executor](executor.md): execution order and credential handling
- [Backend](backend.md): module map, HTTP middleware order, error model
- [Frontend](frontend.md): the control plane UI
- [Web surface](web.md): the landing page, docs browser, theme and motion

## Related

- [Product overview](../product/product-overview.md#the-thesis): the thesis this architecture exists to make true
- [The reference demo](../product/demo.md): the whole request path, run three times, with the thesis asserted
- [API overview](../api/overview.md) and [streaming](../api/streaming.md): the HTTP and SSE contracts at the top of the diagram
- [Database schema](../database/schema.md): the 33 tables behind the PostgreSQL box
- [SDKs and tools](../sdks/overview.md#how-they-connect): how the SDKs, CLI and MCP server reach `plan_and_execute`
- [Threat model](../security/threat-model.md#trust-boundaries): the boundaries in this diagram, and what crosses them
- [Observability](../operations/observability.md#correlating-one-request): following one request through logs, metrics and traces
- [Architecture decision records](../adr/README.md): why each part is the way it is

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Production](../deployment/production.md) | [Docs index](../README.md) | [The engine catalog](../architecture/catalog.md) |
