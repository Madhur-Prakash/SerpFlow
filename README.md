<div align="center">

<h1>SerpFlow</h1>

<p align="center">
  <strong>The cache should change which plan wins, not just make the same plan cheaper.</strong><br>
  A search control plane for SerpApi with cache-aware marginal-cost replanning.
</p>

<p align="center">
  <a href="docs/product/product-overview.md"><img alt="thesis: marginal-cost replanning" src="https://img.shields.io/badge/thesis-marginal--cost%20replanning-2F6BFF"></a>
  <a href="docs/product/benchmark.md"><img alt="routing accuracy 38.3%" src="https://img.shields.io/badge/routing%20accuracy-38.3%25-3fcf8e"></a>
  <a href="backend/tests"><img alt="tests: 180 passing" src="https://img.shields.io/badge/tests-180%20passing-3fcf8e"></a>
  <a href="docs/product/demo.md"><img alt="demo: proven" src="https://img.shields.io/badge/make%20demo-PROVEN-3fcf8e"></a>
  <a href="LICENSE"><img alt="licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-D22128"></a>
</p>

<p align="center">
  <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white">
  <img alt="PostgreSQL 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Apache Kafka 4 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <img alt="SQLAlchemy 2" src="https://img.shields.io/badge/SQLAlchemy-2-D71F00?logo=sqlalchemy&logoColor=white">
  <img alt="React 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <img alt="TypeScript 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="Vite 6" src="https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white">
  <img alt="Tailwind CSS 4" src="https://img.shields.io/badge/Tailwind%20CSS-4-06B6D4?logo=tailwindcss&logoColor=white">
  <img alt="GSAP" src="https://img.shields.io/badge/GSAP-ScrollTrigger-88CE02?logo=greensock&logoColor=black">
  <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
</p>

<p align="center">
  <a href="#the-evidence">Evidence</a> &middot;
  <a href="#the-thesis">Thesis</a> &middot;
  <a href="#how-it-works">How it works</a> &middot;
  <a href="#quick-start">Quick start</a> &middot;
  <a href="#make-targets">Commands</a> &middot;
  <a href="#api">API</a> &middot;
  <a href="#documentation">Documentation</a> &middot;
  <a href="#security">Security</a> &middot;
  <a href="#contributing">Contributing</a> &middot;
  <a href="#license">License</a>
</p>

</div>

**A search control plane for SerpApi.** SerpFlow takes a natural-language
intent, discovers the engine or engine chain that answers it, inspects what is
already cached, computes the **marginal** cost of every candidate plan,
re-ranks on that, and executes only the searches that still need a live call.

> The claim is falsifiable, and the build checks it. `make demo` exits non-zero
> unless cache-aware replanning **changed the selected plan** - a cache hit on
> the same plan is explicitly not sufficient.

---

## Contents

| Understand it | Run it | Build on it |
| --- | --- | --- |
| [The evidence](#the-evidence) | [Quick start](#quick-start) | [API](#api) |
| [The problem](#the-problem) | [Modes](#modes-live-mock-replay) | [MCP](#mcp) |
| [The thesis](#the-thesis) | [Make targets](#make-targets) | [SDKs](#sdks) |
| [How it works](#how-it-works) | [Project structure](#project-structure) | [Observability](#observability) |
| [Features](#features) | [Testing](#testing) | [Documentation](#documentation) |

| Before you trust it | | |
| --- | --- | --- |
| [Security](#security) | [The free tier](#the-free-tier) | [AI tool disclosure](#ai-tool-disclosure) |
| [Contributing](#contributing) | [License](#license) | |

---

## The evidence

### 1. Routing accuracy

Measured on **120 hand-authored labelled tasks**, committed as versioned
fixtures in [`backend/fixtures/benchmark/tasks_v1.json`](backend/fixtures/benchmark/tasks_v1.json),
against catalog `v1.0.0`.

| System | Accuracy | Engine chain | Locale params | Freshness |
| --- | ---: | ---: | ---: | ---: |
| Unaided model, no catalog | **0.0%** | 10.8% | 4.2% | 0.0% |
| Embedding retrieval only | **0.0%** | 11.7% | 4.2% | 0.0% |
| **SerpFlow planner** | **38.3%** | **46.7%** | **79.2%** | **55.0%** |

That 38.3% is the honest number for the **deterministic adapter**, the one that
runs with no API keys at all. It is not a ceiling and it is not a marketing
figure: the dominant failure mode is still wrong-engine selection on 58 of 120
tasks, and the full error analysis is in
[`docs/product/benchmark.md`](docs/product/benchmark.md) along with how to
reproduce every number.

The two baselines score zero on exact chain match because neither can do what
the task set requires. An unaided model has no dependency edges, so it cannot
discover that reviewer identity is reachable only through
`google_maps_reviews.reviews[].user.contributor_id`. Embedding retrieval has no
selector and no path-finding, so it can only ever return one engine.

Reproduce: `make benchmark`. Results commit per catalog version under
[`backend/fixtures/benchmark/results/`](backend/fixtures/benchmark/results).

### 2. Marginal cost reduction

The reference demo asks a question that needs a three-hop chain:

```
find coordinated review rings among Koramangala cafes

google_maps  ->  google_maps_reviews  ->  google_maps_contributor_reviews
     1 call          20 calls                   80 calls
   1 credit         20 credits                 80 credits        = 101 credits cold
```

Run it twice. The second run selects a **different plan**:

```
cold ranking would have chosen   google_local -> google_maps_reviews -> google_maps_contributor_reviews
marginal ranking chose           google_maps  -> google_maps_reviews -> google_maps_contributor_reviews

                                 naive 101 credits    marginal 0 credits    actually spent 0
```

Same intent. Same catalog version. The only thing that changed between the two
runs was cache state, and it changed which plan won. That is the whole product
thesis, and `make demo` exits non-zero if it stops being true.

Reproduce: `make demo`. Walkthrough in [`docs/product/demo.md`](docs/product/demo.md).

---

## The problem

In the SerpApi community showcase, **111 of 185 projects use only
`engine=google`** out of 62 available engines.

That is not because the other engines are bad. It is because nothing tells you
which engine answers your question, nothing tells you that two engines can be
chained, and nothing tells you what a chain will cost before you run it. So
people reach for the one engine they already know, and the long tail stays
unused.

SerpFlow is the missing layer: a catalog that knows what each engine does and
what it produces, a planner that computes valid chains over typed dependency
edges instead of guessing, and a cost model that knows what you already have.

## The thesis

> SerpFlow does not merely cache search results. It **re-plans execution based
> on what is already warm**, optimizing marginal cost rather than cold cost.

A conventional system does this:

```
intent -> plan -> execute -> cache
```

SerpFlow does this:

```
intent
 -> multiple candidate plans
 -> inspect cache state for every step of every candidate
 -> calculate marginal cost
 -> re-rank plans
 -> select the cheapest valid warm-aware plan
 -> execute
```

Caching inside the executor would save credits on the plan you already picked.
Re-planning changes **which plan you pick**. Those are different products.

---

## How it works

### The catalog is the substrate

54 engines, hand-reviewed, committed as YAML under
[`backend/app/services/catalog/data/v1/`](backend/app/services/catalog/data/v1).
Every engine declares two different kinds of relationship, and both are
mandatory:

```yaml
- engine: google_maps_reviews
  purpose: Reviews for a specific place.
  capability_tags: [place_reviews]        # how engines COMPETE
  substitutes:
    - engine: yelp_reviews
      coverage: partial
      note: >
        Sparse coverage outside US metros, and the reviewer identity shape
        differs, so contributor-history chaining is not available downstream.
  requires:
    data_id:                              # how engines CHAIN
      type: string
      satisfied_by:
        - google_maps.local_results[].data_id
  produces:
    "reviews[].user.contributor_id":
      feeds: [google_maps_contributor_reviews.contributor_id]
      fan_out_hint: 4
  cost: 1
  volatility_prior: 7d
  pii_risk: high
```

Dependency edges make multi-hop chains **computable**. Capability tags and
substitutes make alternative plans **generatable**. Remove either and the
thesis has nothing to operate on.

30 dependency edges, 69 substitute edges, 28 capability tags.
See [`docs/architecture/catalog.md`](docs/architecture/catalog.md).

### The planner has four stages

| Stage | What it does | Code |
| --- | --- | --- |
| **A. Retrieve** | Top 8 candidates by capability affinity and embedding similarity, expanded to include substitutes of strong matches so competing engines enter the set | [`retrieval.py`](backend/app/services/planner/retrieval.py) |
| **B. Select** | Chooses engines and records why each rejected one lost | [`mock.py`](backend/app/integrations/llm/mock.py), [`groq.py`](backend/app/integrations/llm/groq.py) |
| **C. Synthesize** | Date normalisation, locale inference, entity resolution, parameter binding, **freshness inference** | [`text.py`](backend/app/core/text.py) |
| **D. Path-find** | Computes valid chains over typed edges and emits **multiple candidate plans** | [`graph.py`](backend/app/services/catalog/graph.py), [`candidates.py`](backend/app/services/planner/candidates.py) |

The model never invents a chain. It picks a target capability; the graph
algorithm decides what is actually reachable.

Freshness inference is what makes the cost model honest. A cached entry being
*available* is not the same as it being *acceptable*:

```
realtime  < 15m      fresh  < 24h      recent  < 7d      stable  any valid TTL
```

A warm entry counts toward marginal savings only if it also satisfies the
step's freshness requirement. See
[`docs/architecture/planner.md`](docs/architecture/planner.md).

### Marginal cost is the ranking key

```
Plan A    cold 4    marginal 4
Plan B    cold 8    marginal 1      <- SerpFlow selects B
```

Candidates are ranked twice: once on cold cost, once on marginal cost. When
the two disagree, that fact is persisted on the Plan and counted in
`serpflow_marginal_replan_changed_selection_total`. The Plan Inspector renders
the stored decision; nothing is recomputed in the browser.

Coverage outranks price: a narrow-coverage substitute being cheaper is not a
reason to answer a different question.
See [`docs/architecture/marginal-replanning.md`](docs/architecture/marginal-replanning.md).

### Four cache layers

```
EXACT     Redis            hot, TTL-based, NOT the source of truth
SEMANTIC  PostgreSQL       pgvector + HNSW, partition-filtered, guard-protected
ARCHIVE   SerpApi Archive  re-reads cost no credit
LIVE      SerpApi          the only layer that spends
```

The semantic layer is protected by a **deterministic entity and numeral
guard**. Before any semantic hit is accepted, numerals, version identifiers and
named entities are extracted from both queries and must match as exact sets:

```
iphone 16              never matches   iphone 17
restaurants in Koramangala   never matches   restaurants in Indiranagar
```

regardless of cosine score. This is a mechanism, not a model judgement, and
every rejection is logged so the threshold can be tuned with evidence.
See [`docs/architecture/caching.md`](docs/architecture/caching.md).

---

## Quick start

```bash
git clone https://github.com/serpflow/serpflow.git
cd serpflow
cp .env.example .env

make install        # uv venv on Python 3.13 + npm install
make up             # postgres (pgvector), redis, kafka (KRaft)
make upgrade        # alembic migrations
make seed           # catalog, 120 benchmark tasks, demo org, API keys
make demo           # prove the thesis
make dev            # API on :8000, frontend on :5173
```

**No API keys are required for any of that.** Planning falls back to a
deterministic adapter, and `test` API keys route to a deterministic SerpApi
mock that consumes zero credits.

When you do want real searches, SerpFlow is
[bring-your-own-key](docs/security/byok.md): your SerpApi and Groq keys are
stored encrypted per organization, and the platform holds none of its own that
your work could fall back to.

`make seed` prints sign-in details and a test API key. Then:

```bash
export SERPFLOW_API_KEY=sf_test_...
serpflow search "find coordinated review rings among Koramangala cafes"
serpflow plan --budget 20 "recent reviews for a ramen shop in Seoul called Ichiran"
serpflow catalog explore google_maps_contributor_reviews
serpflow benchmark compare
```

### Everything in containers

```bash
make docker-up      # frontend :5173, API :8000, postgres, redis, kafka
```

Optional profiles: `docker compose --profile observability up -d` adds
Prometheus and Grafana; `--profile storage` adds MinIO.

---

## Modes: live, mock, replay

```
SERPFLOW_MODE=live | record | replay
```

Precedence is absolute and is enforced in one place
([`serpapi/__init__.py`](backend/app/integrations/serpapi/__init__.py)):

1. A **`test` API key always routes to the deterministic mock**, whatever
   `SERPFLOW_MODE` says. This cannot be overridden. It is how you integrate
   before connecting a paid account.
2. For `live` keys, `SERPFLOW_MODE` decides: `live` executes normally,
   `record` executes and persists cassettes, `replay` serves cassettes only.

**Replay never touches the network.** A miss fails loudly, naming the exact
cassette file that is missing.

The resolved mode travels on every response as `X-SerpFlow-Mode` and is shown
in the UI at all times. Replayed or mocked data is never presented as live.

---

## Features

| | |
| --- | --- |
| **Routing** | 54-engine catalog, typed dependency edges, substitute groups, multi-hop path-finding, multiple candidate plans per intent |
| **Cost** | Marginal-cost replanning, budget-aware fan-out reduction with impact notes, full-scale projections that are never executed live |
| **Cache** | Exact (Redis), semantic (pgvector + HNSW, partition-filtered), SerpApi Searches Archive, adaptive TTL learned per engine and query class |
| **Correctness** | Deterministic entity and numeral guard, freshness inference, guard-rejection logging, operator false-hit reporting |
| **Multi-tenant** | Organizations, projects, members, RBAC with five roles, PostgreSQL RLS, project-level cache isolation with opt-in organization sharing |
| **Security** | Argon2id passwords, HMAC-SHA256 API keys, envelope-encrypted upstream credentials, credential redaction filter with tests, append-only hash-chained audit log |
| **Budgets** | Four scopes, four periods, three exhaustion modes, upstream quota reconciliation that never conflates your cap with SerpApi's |
| **Operations** | OpenTelemetry traces, 20 Prometheus metrics, Kafka background workers in KRaft mode, SSE streaming, webhooks, alerts |
| **Interfaces** | REST API, SSE, MCP server, Python and TypeScript SDKs, CLI, control-plane UI |

---

## Stack

**Backend** Python 3.13, FastAPI, Uvicorn, PostgreSQL 17 + pgvector, Redis,
Apache Kafka 4.x (KRaft, no ZooKeeper), SQLAlchemy 2, Alembic, Pydantic v2,
Logifyx, OpenTelemetry, Prometheus, Docker.

**Frontend** React 19, TypeScript, Vite, Tailwind CSS v4, Radix primitives,
Lucide, Framer Motion, GSAP, Lenis, Recharts, TanStack Query, Zustand.

**LLM** Groq, through a key the organization brings, with a deterministic
adapter whenever it has not - so nothing requires a key. Embeddings are a local deterministic feature-hashing
model: no network, no key, identical across processes and CI.

---

## Project structure

```
serpflow/
├── backend/
│   ├── app/
│   │   ├── api/v1/            auth, organizations, credentials, search,
│   │   │                      runs, catalog, governance
│   │   ├── core/              config, security, permissions, logging,
│   │   │                      telemetry, metrics, text, routes
│   │   ├── db/models/         identity, keys, planning, caching, catalog,
│   │   │                      governance, benchmark
│   │   ├── services/
│   │   │   ├── catalog/       loader, typed graph, vocabulary, data/v1/*.yaml
│   │   │   ├── planner/       retrieval, candidates, cost, budget, service
│   │   │   ├── executor/      four-layer execution, field extraction
│   │   │   ├── cache/         keys, guard, exact, semantic, archive, TTL
│   │   │   ├── budgets/ analytics/ benchmark/ auth/ credentials/ audit/
│   │   │   └── runs.py        the one place a plan becomes a run
│   │   ├── workers/           Kafka producers and consumers
│   │   ├── integrations/      serpapi (real, mock, cassettes), llm, storage
│   │   ├── mcp/ cli/ sdk/     MCP server, CLI, Python SDK
│   │   └── main.py
│   ├── alembic/versions/      0001 initial schema, 0002 audit purge guard
│   ├── fixtures/benchmark/    120 labelled tasks + committed results
│   ├── scripts/               seed.py, demo.py, catalog_build.py
│   └── tests/                 unit, integration, e2e
├── frontend/src/
│   ├── components/            ui, layout, charts, graphs, shared
│   ├── pages/                 overview, search, runs, plan inspector,
│   │                          catalog, cache, budgets, analytics,
│   │                          benchmarks, audit, settings, auth
│   ├── hooks/ lib/ stores/ types/ animations/ styles/
│   └── routes/
├── sdk/typescript/            TypeScript SDK
├── docs/                      architecture, api, database, security,
│                              deployment, operations, product, adr
├── docker/                    postgres, redis, prometheus, grafana config
├── docker-compose.yml
└── Makefile
```

---

## Make targets

| Target | What it does |
| --- | --- |
| `make install` | Create the Python 3.13 venv with uv, install backend and frontend |
| `make dev` | Run the API and the Vite dev server together |
| `make backend` / `make frontend` | Run one of them |
| `make worker` | Run the Kafka consumers as a separate process |
| `make mcp` | Run the MCP server over stdio |
| `make up` / `make down` / `make restart` | Start, stop, restart postgres, redis, kafka |
| `make logs` / `make ps` | Tail service logs, show status |
| `make migrate` / `make upgrade` | Apply migrations |
| `make migration ARGS="-m 'message'"` | Autogenerate a migration from the models |
| `make downgrade` | Roll back one migration |
| `make seed` / `make seed ARGS=--reset` | Load catalog, benchmarks and demo data |
| `make demo` / `make demo ARGS=--reset-cache` | Run the reference demo and prove the thesis |
| `make kafka-topics` | Create every Kafka topic |
| `make catalog-build` / `ARGS=--diff` | Regenerate catalog drafts from the SerpApi docs |
| `make catalog-validate` | Lint the committed catalog |
| `make benchmark` | Run all three systems on the 120-task suite |
| `make test` / `test-unit` / `test-integration` / `test-e2e` | Run tests |
| `make lint` / `format` / `typecheck` | Quality gates |
| `make build` | Build the frontend bundle |
| `make docker-build` / `docker-up` / `docker-down` | Full stack in containers |
| `make psql` / `redis-cli` | Open a shell on a datastore |
| `make health` | Check the service and every dependency |
| `make clean` | Remove build artefacts and caches |

---

## API

```
POST /v1/plan                       plan without executing (costs no credits)
POST /v1/search                     plan with replanning, then execute
POST /v1/run                        alias of /search

GET  /v1/runs                       list, filter by engine, status, replan-changed
GET  /v1/runs/{id}                  the Run Inspector payload
GET  /v1/runs/{id}/stream           Server-Sent Events
POST /v1/runs/{id}/replay           re-run against current cache state
POST /v1/runs/{id}/report-false-hit report a bad semantic hit

GET  /v1/catalog                    engines, both edge kinds, capability tags
GET  /v1/catalog/graph              nodes plus dependency and substitute edges
GET  /v1/catalog/engines/{e}/paths  every valid chain reaching an engine

GET  /v1/benchmarks                 accuracy per catalog version
GET  /v1/analytics/*                dashboard, savings, attribution, routing,
                                    volatility, engine reach, cross-project

CRUD /v1/budgets  /v1/projects  /v1/keys  /v1/members  /v1/credentials

GET  /healthz  /readyz  /metrics
```

Full OpenAPI at `/docs`. Details in [`docs/api/overview.md`](docs/api/overview.md),
streaming in [`docs/api/streaming.md`](docs/api/streaming.md), worked requests
in [`docs/api/examples.md`](docs/api/examples.md).

### Provenance on every response

```
X-SerpFlow-Cache            X-SerpFlow-Budget-Remaining
X-SerpFlow-Matched-Query    X-SerpFlow-Run-Id
X-SerpFlow-Age              X-SerpFlow-Trace-Id
X-SerpFlow-TTL-Source       X-SerpFlow-Mode
```

### Server-Sent Events

`GET /v1/runs/{id}/stream` emits one frame per real backend stage transition:

```
analyzing intent -> finding candidate engines -> synthesizing parameters ->
inferring freshness requirements -> finding valid paths ->
generating candidate plans -> inspecting cache state ->
calculating marginal cost -> re-ranking plans -> checking budget ->
executing required steps
```

Each frame carries `stage`, `status`, `elapsed_ms` and `detail`. The UI
pipeline animation is driven entirely by these frames. There is no timer and no
simulated sequence anywhere in the frontend.

---

## MCP

```bash
SERPFLOW_API_KEY=sf_test_... serpflow-mcp
```

Three tools on the same service layer the REST API uses, with no duplicated
planner or executor logic:

```
search(intent, budget?)   plan with replanning, then execute
plan(intent)              plan only, costs nothing
explain(run_id)           the Plan Inspector as structured data
catalog(engine?)          browse the catalog
```

Every call resolves a full principal: service principal, session, project,
budget and permissions. An agent is not modelled as a human holding a shared
key, and its session cap is enforced the same way a project budget is.

## SDKs

```python
from serpflow import SerpFlow

client = SerpFlow(api_key="sf_test_...")
result = client.search("flights from Hyderabad to Da Nang in late November")
print(result.plan.marginal_cost, "credits on the margin")
```

```typescript
import { SerpFlow } from "@serpflow/sdk";

const client = new SerpFlow({ apiKey: "sf_test_..." });
for await (const event of client.stream("review rings among Koramangala cafes")) {
  console.log(event.stage, event.status);
}
```

Both ship a **SerpApi-compatible drop-in**: change only the base URL and
existing SerpApi code routes through SerpFlow, gaining caching and budget
enforcement without adopting routing.
See [`docs/api/examples.md`](docs/api/examples.md).

---

## Observability

**Traces** `serpflow.plan` spans `catalog.retrieve`, `plan.select`,
`plan.pathfind`, `plan.candidates`, `plan.marginal_cost`, then `execute` ->
`execute.step` -> `upstream.call`.

**Metrics** 20 Prometheus series, every one with a real producer. The one that
matters:

```
serpflow_marginal_replan_changed_selection_total
```

That is the thesis, instrumented. It counts how often cache-aware replanning
actually changed the chosen plan, and the e2e suite asserts it is greater than
zero.

**Logs** Logifyx structured JSON with a credential redaction filter that runs
on the record, the formatted message and the exception path.
`tests/unit/test_security.py` asserts secrets never reach a sink.

See [`docs/operations/observability.md`](docs/operations/observability.md).

## Security

| Concern | Approach |
| --- | --- |
| Passwords | Argon2id |
| API keys | HMAC-SHA256 under a server-side pepper, `hmac.compare_digest`, sub-millisecond and constant time |
| Upstream credentials | Envelope encryption, random per-credential DEK wrapped by a KEK, absent from every response schema |
| Tenant isolation | `org_id` on every scoped table, application guards, PostgreSQL RLS as a backstop |
| Audit | Append-only at the database level, hash chained, verifiable, exportable |
| Retention | 30 days standard, 7 days for high PII risk, configurable per project |

API keys are deliberately **not** Argon2 hashed: they carry 190+ bits of
entropy, so there is no brute-force surface to stretch against, and Argon2
would add 50-100 ms to every single request for no security gain.

See [`docs/security/threat-model.md`](docs/security/threat-model.md),
[`credentials.md`](docs/security/credentials.md),
[`api-keys.md`](docs/security/api-keys.md),
[`secrets.md`](docs/security/secrets.md).

## Testing

```bash
make test             # 115 tests
make test-unit        # no services needed
make test-integration # postgres + redis
make test-e2e         # includes the thesis assertion
```

The e2e suite contains an explicit test asserting that cache state changed
which plan was selected. If marginal replanning stops working, that test fails.

The benchmark makes real LLM calls and is deliberately **not** part of CI.

---

## Documentation

Everything is in [`docs/`](docs/README.md), and the running app serves the same
pages at `/docs` with a sidebar, search and an on-page contents. The API
reference at `/api` is generated from the OpenAPI schema.

| | |
| --- | --- |
| **Architecture** | [overview](docs/architecture/overview.md) · [backend](docs/architecture/backend.md) · [frontend](docs/architecture/frontend.md) · [web surface](docs/architecture/web.md) · [catalog](docs/architecture/catalog.md) · [planner](docs/architecture/planner.md) · [marginal replanning](docs/architecture/marginal-replanning.md) · [executor](docs/architecture/executor.md) · [caching](docs/architecture/caching.md) |
| **API** | [overview](docs/api/overview.md) · [streaming](docs/api/streaming.md) · [examples](docs/api/examples.md) |
| **Database** | [schema](docs/database/schema.md) · [migrations](docs/database/migrations.md) · [RLS](docs/database/rls.md) |
| **Security** | [threat model](docs/security/threat-model.md) · [credentials](docs/security/credentials.md) · [API keys](docs/security/api-keys.md) · [secrets](docs/security/secrets.md) |
| **Deployment** | [local](docs/deployment/local.md) · [docker](docs/deployment/docker.md) · [production](docs/deployment/production.md) |
| **Operations** | [bootstrap](docs/operations/bootstrap.md) · [email](docs/operations/email.md) · [observability](docs/operations/observability.md) · [kafka](docs/operations/kafka.md) · [redis](docs/operations/redis.md) · [troubleshooting](docs/operations/troubleshooting.md) |
| **Product** | [overview](docs/product/product-overview.md) · [benchmark](docs/product/benchmark.md) · [demo](docs/product/demo.md) |
| **SDKs** | [overview](sdk/README.md) · [TypeScript](sdk/typescript/README.md) |
| **Decisions** | [ADR index](docs/adr/README.md) - fourteen records, each with the alternative rejected and the cost accepted |

---

## The free tier

The SerpApi free tier is 250 searches a month, and every default here respects
it. `make seed` creates a 250-credit organization guard. The reference demo
runs entirely against the deterministic mock and spends **zero** credits. The
101-credit full-scale chain is displayed as a projection and is never executed
live, because one run would consume 40% of a month's allowance.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md). Security reports:
[SECURITY.md](SECURITY.md). Changes: [CHANGELOG.md](CHANGELOG.md).

## AI tool disclosure

This project was built with AI assistance (Claude). The engine catalog's
dependency edges and substitute groups were reviewed by hand, as
[`docs/architecture/catalog.md`](docs/architecture/catalog.md) describes: a
scraper can see that `google_maps_reviews` takes a `data_id`, but only a human
decides that `google_maps.local_results[].data_id` is the field that satisfies
it, or that Yelp's coverage collapses outside US metros.

## License

[Apache-2.0](LICENSE).

---

<div align="center">

<strong>SerpFlow</strong><br>
<sub>A search control plane for SerpApi.</sub>

<p align="center">
  <a href="docs/README.md">Documentation</a> &middot;
  <a href="docs/architecture/overview.md">Architecture</a> &middot;
  <a href="docs/api/overview.md">API</a> &middot;
  <a href="docs/adr/README.md">Decisions</a> &middot;
  <a href="sdk/README.md">SDKs</a> &middot;
  <a href="CONTRIBUTING.md">Contributing</a> &middot;
  <a href="SECURITY.md">Security</a> &middot;
  <a href="CHANGELOG.md">Changelog</a>
</p>

<sub>&copy; 2026 SerpFlow. All rights reserved. Released under the Apache-2.0 licence.</sub>

</div>
