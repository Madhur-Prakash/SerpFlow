# Product overview

<p>
  <a href="../product/README.md"><img alt="docs: Product" src="https://img.shields.io/badge/docs-Product-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="thesis: marginal-cost replanning" src="https://img.shields.io/badge/thesis-marginal--cost%20replanning-2F6BFF">
  <img alt="SerpApi: 54 engines" src="https://img.shields.io/badge/SerpApi-54%20engines-2F6BFF">
  <a href="../../backend/app/sdk/__init__.py"><img alt="source: sdk/__init__.py" src="https://img.shields.io/badge/source-sdk%2F____init____.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 9 min" src="https://img.shields.io/badge/read-9%20min-555555">
</p>

[Docs](../README.md) › [Product](../product/README.md) › **Product overview** · page 2 of 50

**SerpFlow is a search control plane for SerpApi.** Given a natural-language intent, it:

- works out which engine, or engine chain, answers it: the [planner](../architecture/planner.md)
- inspects what is already [cached](../architecture/caching.md#two-entry-points)
- computes the **marginal** cost of every candidate plan, and re-ranks on that: [marginal-cost replanning](../architecture/marginal-replanning.md)
- executes only the searches that still need a live call: the [executor](../architecture/executor.md)

> This page is the **why**. The [architecture docs](../architecture/overview.md) are the **how**. Every term used here is defined in the [glossary](glossary.md).

- **You run it yourself, for now.** SerpFlow is self-hosted by the author's decision: there is no public hosted instance yet, and the author will host one once enough people ask ([hosting](../../README.md#hosting))

## The problem

A team using SerpApi at any scale ends up building four things, badly, in the application layer:

| Concern | What goes wrong |
| --- | --- |
| **Engine selection** | Dozens of engines with different parameters, result shapes and costs. Which one answers "what is Nvidia trading at right now" gets hardcoded into whichever service needed it first |
| **Chaining** | Some questions need several engines. Reviewer identity is only reachable through `google_maps_reviews.reviews[].user.contributor_id`: [Maps, then reviews, then contributor reviews](../architecture/catalog.md#the-reference-demo-chain). That chain lives in one script nobody else can discover |
| **Caching** | Results get cached by request hash. A paraphrase of yesterday's question is a full-price miss, and a stale entry for a volatile query is served as if live |
| **Cost control** | Spend is one number on the SerpApi dashboard at month end. Which team, feature or query shape: unknown |

- Each is solvable on its own
- **Solved separately, they do not compose:**
  - the cache does not know what the router is choosing between
  - so the router keeps picking a cheaper-but-cold plan over an expensive-but-already-cached one

## The thesis

> **Cache state should change which plan is selected, not just make the selected plan faster.**

- That is the one claim this system makes, and it is **deliberately falsifiable**: [the demo](demo.md) fails if it stops being true
- **Conventional caching:** rank plans on cold cost, pick a winner, then check the cache. Savings only happen if the winner is cached
- **SerpFlow:** rank on **marginal** cost, the cost of the steps that still need a live call
  - a plan costing 101 credits cold but fully warm costs **0**
  - it beats a plan costing 51 cold that is actually cold

```
cold ranking         google_local -> google_maps_reviews -> contributor_reviews   51 credits
marginal ranking     google_maps  -> google_maps_reviews -> contributor_reviews    0 credits

same intent, same catalog version, different selected plan
```

- The metric: [`serpflow_marginal_replan_changed_selection_total`](../operations/observability.md#the-thesis-metric)
- [`make demo`](demo.md) **exits non-zero if the warm run did not change the selection**
- A cache hit on the same plan is explicitly **not** enough: everyone already has that
- Detail: [marginal replanning](../architecture/marginal-replanning.md#the-distinction)

## What makes it work

Four pieces, none of them optional.

### 1. A typed catalog

- **54 engines**, each [described](../architecture/catalog.md#what-an-engine-entry-declares) with required parameters, produced fields, cost, volatility prior and capability tags (28 in the [vocabulary](../architecture/catalog.md#the-capability-vocabulary))
- **Two edge sets** on top, both mandatory:
  - **Dependency edges** (`satisfied_by` / `feeds`, 30 of them): how engines **chain**. Without them, multi-hop chains are not computable and [`/paths`](../api/overview.md#catalog) has nothing to answer
  - **Substitute edges** (`capability_tags` / `substitutes`, 69 of them): how engines **compete**. Without them there is only ever one candidate plan, and a one-entry ranking cannot change
- The thesis needs alternatives to choose between
- More: [catalog architecture](../architecture/catalog.md)

### 2. A four-stage planner

```
A  retrieve      candidate engines, by tag affinity and embedding similarity
B  select        which capability actually answers this
C  synthesize    dates, locale, entities, parameter binding
D  generate      multiple competing plans, via substitutes and path-finding
```

- **[Stage D](../architecture/planner.md#stage-d-path-find-and-generate-candidates) matters most for the thesis:** it produces a candidate **set**, not a winner
- **Every candidate is persisted**, so the [Plan Inspector](../architecture/frontend.md#routes) can show why the winner won instead of asserting it
- **Coverage is ranked before price** ([ADR 0004](../adr/0004-coverage-before-price.md)): a cheap plan that only partly answers the intent does not beat one that answers it
- More: [planner architecture](../architecture/planner.md)

### 3. Four cache layers, with a deterministic guard

```
EXACT      Redis, backed by a durable PostgreSQL index   request hash
SEMANTIC   pgvector, with a deterministic guard          near-duplicate queries
ARCHIVE    the SerpApi Searches Archive                  re-reads cost no credit
LIVE       SerpApi                                       the only layer that spends
```

- Detail per layer: [the Redis boundary](../architecture/caching.md#the-redis-boundary) for exact hits, [the Searches Archive](../architecture/caching.md#the-searches-archive) for re-reads
- **The semantic layer is the interesting one, and the dangerous one**
  - "Nvidia Q3 2024 revenue" and "Nvidia Q4 2024 revenue" embed close together
  - a cosine threshold alone serves one for the other, confidently: a correctness failure dressed as a saving
- **[The entity, numeral and version guard](../architecture/caching.md#the-entity-and-numeral-guard)** runs **independently of the similarity score**, on exact set equality ([ADR 0002](../adr/0002-deterministic-semantic-guard.md))
  - both queries mention a quarter, the sets differ, so it is rejected whatever the cosine says
- **[Availability is not acceptability](../architecture/marginal-replanning.md#available-is-not-acceptable):** an entry only counts as warm if it meets the step's [inferred freshness bound](../architecture/planner.md#freshness-inference)

```
realtime   < 15m      fresh   < 24h      recent   < 7d      stable
```

- More: [caching architecture](../architecture/caching.md)

### 4. Governance that is computed, not estimated

- **Budgets at four scopes:** organization, project, [API key](../security/api-keys.md), [service session](../security/api-keys.md#service-principal-sessions). The tightest applicable one wins, checked [before every live call](../architecture/executor.md#budget-enforcement)
- **Savings broken down by mechanism:** `routing`, `exact`, `semantic`, `archive` ([spend and savings](../operations/observability.md#spend-and-savings)). "We saved credits" is not a claim until you can say which of the four did it
- **Cross-project benefit is a figure, not a guess:** the [`budget_ledger`](../database/schema.md#governance) carries `project_id` and `beneficiary_project_id` separately
- **Spend attribution** runs organization → project → principal → run → step → engine

## Who it is for

- **An engineering team using SerpApi directly**
  - [the drop-in compat client](../sdks/python.md#the-serpapi-drop-in) keeps existing call sites in shape: a params dict in, `get_dict()` out
  - change the base URL and key, and caching, budgets and provenance arrive without a rewrite
  - **it re-routes:** only `q` (or `query`) is sent, as the intent of a [`POST /v1/search`](../api/overview.md#plan-and-execute), and the planner picks the engines. `engine` and every other parameter are echoed back in `search_parameters` and `search_metadata`, not honoured ([`app/sdk/__init__.py`](../../backend/app/sdk/__init__.py))
  - **the SDKs are not released yet:** they will be published when the author decides to host SerpFlow; if you self-host, install them from a checkout and use them on your own infrastructure ([Python](../sdks/python.md#install), [TypeScript](../sdks/typescript.md#install), [why](../sdks/releasing.md#first-who-runs-the-server)). `from serpflow import ...` needs an editable install of `backend/`

```python
from serpflow import SerpApiCompat
search = SerpApiCompat({"engine": "google_maps", "q": "...", "api_key": "sf_..."})
results = search.get_dict()   # routed by the planner; "engine" is echoed, not enforced
```

- **An agent or LLM application**
  - [the MCP server](../sdks/mcp.md) exposes `plan`, `search`, `explain` and `catalog`
  - every call resolves a full principal; a service key, or one carrying a session cap, also opens a [service session](../security/api-keys.md#service-principal-sessions) with its own cap
  - **with [`SERPFLOW_MCP_SESSION`](../security/secrets.md#inventory) set**, every call resumes that named session, so an agent stuck in a loop hits `SESSION_CAP_EXCEEDED`, not the organization's monthly budget
  - **without it**, each tool call opens a fresh session, so the cap does not accumulate across calls; the key's own budget, created alongside a service key's cap, is the cumulative limit ([`open_service_session`](../../backend/app/services/auth/service.py), [`organizations.py`](../../backend/app/api/v1/organizations.py), [sessions and budgets](../sdks/mcp.md#sessions-and-budgets))
- **A platform team**
  - multi-tenant with [row-level security](../database/rls.md), enforced in the database and again in the application ([ADR 0006](../adr/0006-rls-plus-application-guards.md))
  - per-project [engine policy](../architecture/executor.md#engine-policy)
  - an [append-only, hash-chained audit log](../database/rls.md#the-audit-log)
  - shorter [retention](../architecture/executor.md#retention) for high-PII payloads

## What it does not do

Stated plainly, because an unstated boundary reads as an oversight.

- **It does not scrape.** SerpApi is the only outbound data path
- **It does not verify upstream results.** It caches and attributes what SerpApi returns
- **It does not replace SerpApi.** It is a control plane in front of it, and live execution needs your own SerpApi credential: [bring your own key](../security/byok.md), [upstream credentials](../security/credentials.md)
- **Routing accuracy is 38.3%, not 90%**
  - the honest measured number for the deterministic adapter on 120 hand-authored tasks
  - the main failure is still wrong-engine selection, on 58 of them
  - full error analysis in [benchmark](benchmark.md#failure-analysis), including the cases where the label, not the planner, is arguably wrong

## The surfaces

| Surface | For |
| --- | --- |
| [REST API](../api/overview.md) | anything |
| [SSE stream](../api/streaming.md) | watching a run happen, one frame per real stage transition |
| [Python SDK](../sdks/python.md) | sync and async, plus the SerpApi drop-in; not on PyPI yet |
| [TypeScript SDK](../sdks/typescript.md) | no runtime dependencies; Node, Deno, Bun, browser; not released until SerpFlow is hosted |
| [CLI](../sdks/cli.md) | `serpflow plan`, `search`, `runs`, `replay`, `catalog`, `cache`, `benchmark`, `health`, `version` |
| [MCP](../sdks/mcp.md) | agents, with their own budget identity |
| [Web console](../architecture/frontend.md) | dashboard, Run Inspector, Plan Inspector, Catalog Explorer, Cache Dashboard |

- **How the four programmatic surfaces relate**, and which to pick: [SDKs and tools](../sdks/overview.md)

## Proving it

```bash
make seed        # no API keys needed
make demo        # exits non-zero if the thesis fails
make benchmark   # reproduces the routing numbers
make test-e2e    # asserts the replan actually changed the selection
```

- Everything above runs inside the **SerpApi free tier**, and in fact spends **zero** credits: the default [execution mode](execution-modes.md) is `replay`, and a [`test` key](../security/api-keys.md#test-keys) always routes to the deterministic mock
- The 101-credit chain in the demo is a **[projection](../architecture/marginal-replanning.md#projections-are-never-executed)** from catalog fan-out hints, and is never executed live
- What each target does: [the reference demo](demo.md), [the routing benchmark](benchmark.md#running-it), [the same assertion in tests](demo.md#the-same-assertion-in-ci), [everyday targets](../deployment/local.md#everyday-targets)

## Related

- [The reference demo](demo.md): the thesis proven end to end, with an exit code
- [Execution modes](execution-modes.md): why the demo, the tests and `make seed` spend nothing
- [Routing benchmark](benchmark.md): the 38.3%, and the error analysis behind it
- [Glossary](glossary.md): every term on this page, defined and linked to its canonical page
- [Architecture overview](../architecture/overview.md): the system map behind the four pieces
- [Marginal-cost replanning](../architecture/marginal-replanning.md): the mechanism the thesis rests on
- [SDKs and tools](../sdks/overview.md): the SDK, CLI and MCP surfaces side by side
- [Decision records](../adr/README.md): why each piece is built the way it is

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Product index](../product/README.md) | [Docs index](../README.md) · [Product index](../product/README.md) | [The reference demo](../product/demo.md) |
