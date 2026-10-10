# Product overview

<p>
  <a href="../README.md#product"><img alt="docs: Product" src="https://img.shields.io/badge/docs-Product-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="thesis: marginal-cost replanning" src="https://img.shields.io/badge/thesis-marginal--cost%20replanning-2F6BFF">
  <img alt="SerpApi: 54 engines" src="https://img.shields.io/badge/SerpApi-54%20engines-2F6BFF">
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [Product](../README.md#product) › **Product overview** · page 1 of 50

**SerpFlow is a search control plane for SerpApi.** Given a natural-language intent, it:

- works out which engine, or engine chain, answers it
- inspects what is already cached
- computes the **marginal** cost of every candidate plan, and re-ranks on that
- executes only the searches that still need a live call

> This page is the **why**. The architecture docs are the **how**.

## The problem

A team using SerpApi at any scale ends up building four things, badly, in the application layer:

| Concern | What goes wrong |
| --- | --- |
| **Engine selection** | Dozens of engines with different parameters, result shapes and costs. Which one answers "what is Nvidia trading at right now" gets hardcoded into whichever service needed it first |
| **Chaining** | Some questions need several engines. Reviewer identity is only reachable through `google_maps_reviews.reviews[].user.contributor_id`: Maps, then reviews, then contributor reviews. That chain lives in one script nobody else can discover |
| **Caching** | Results get cached by request hash. A paraphrase of yesterday's question is a full-price miss, and a stale entry for a volatile query is served as if live |
| **Cost control** | Spend is one number on the SerpApi dashboard at month end. Which team, feature or query shape: unknown |

- Each is solvable on its own
- **Solved separately, they do not compose:**
  - the cache does not know what the router is choosing between
  - so the router keeps picking a cheaper-but-cold plan over an expensive-but-already-cached one

## The thesis

> **Cache state should change which plan is selected, not just make the selected plan faster.**

- That is the one claim this system makes, and it is **deliberately falsifiable**
- **Conventional caching:** rank plans on cold cost, pick a winner, then check the cache. Savings only happen if the winner is cached
- **SerpFlow:** rank on **marginal** cost, the cost of the steps that still need a live call
  - a plan costing 101 credits cold but fully warm costs **0**
  - it beats a plan costing 51 cold that is actually cold

```
cold ranking         google_local -> google_maps_reviews -> contributor_reviews   51 credits
marginal ranking     google_maps  -> google_maps_reviews -> contributor_reviews    0 credits

same intent, same catalog version, different selected plan
```

- The metric: `serpflow_marginal_replan_changed_selection_total`
- `make demo` **exits non-zero if it is zero**
- A cache hit on the same plan is explicitly **not** enough: everyone already has that
- Detail: [marginal replanning](../architecture/marginal-replanning.md)

## What makes it work

Four pieces, none of them optional.

### 1. A typed catalog

- **54 engines**, each described with required parameters, produced fields, cost, volatility prior and capability tags
- **Two edge sets** on top, both mandatory:
  - **Dependency edges** (`satisfied_by` / `feeds`): how engines **chain**. Without them, multi-hop chains are not computable and `/paths` has nothing to answer
  - **Substitute edges** (`capability_tags` / `substitutes`): how engines **compete**. Without them there is only ever one candidate plan, and a one-entry ranking cannot change
- The thesis needs alternatives to choose between
- More: [catalog architecture](../architecture/catalog.md)

### 2. A four-stage planner

```
A  retrieve      candidate engines, by tag affinity and embedding similarity
B  select        which capability actually answers this
C  synthesize    dates, locale, entities, parameter binding
D  generate      multiple competing plans, via substitutes and path-finding
```

- **Stage D matters most for the thesis:** it produces a candidate **set**, not a winner
- **Every candidate is persisted**, so the Plan Inspector can show why the winner won instead of asserting it
- More: [planner architecture](../architecture/planner.md)

### 3. Four cache layers, with a deterministic guard

```
EXACT      Redis, backed by a durable PostgreSQL index   request hash
SEMANTIC   pgvector, with a deterministic guard          near-duplicate queries
ARCHIVE    the SerpApi Searches Archive                  re-reads cost no credit
LIVE       SerpApi                                       the only layer that spends
```

- **The semantic layer is the interesting one, and the dangerous one**
  - "Nvidia Q3 2024 revenue" and "Nvidia Q4 2024 revenue" embed close together
  - a cosine threshold alone serves one for the other, confidently: a correctness failure dressed as a saving
- **The entity, numeral and version guard** runs **independently of the similarity score**, on exact set equality
  - both queries mention a quarter, the sets differ, so it is rejected whatever the cosine says
- **Availability is not acceptability:** an entry only counts as warm if it meets the step's inferred freshness bound

```
realtime   < 15m      fresh   < 24h      recent   < 7d      stable
```

- More: [caching architecture](../architecture/caching.md)

### 4. Governance that is computed, not estimated

- **Budgets at four scopes:** organization, project, API key, service session. The tightest applicable one wins
- **Savings broken down by mechanism:** `routing`, `exact`, `semantic`, `archive`. "We saved credits" is not a claim until you can say which of the four did it
- **Cross-project benefit is a figure, not a guess:** the ledger carries `project_id` and `beneficiary_project_id` separately
- **Spend attribution** runs organization → project → principal → run → step → engine

## Who it is for

- **An engineering team using SerpApi directly**
  - the drop-in compat client keeps existing code working
  - change the base URL and key, and caching, budgets and provenance arrive without a rewrite

```python
from serpflow import SerpApiCompat
search = SerpApiCompat({"engine": "google_maps", "q": "...", "api_key": "sf_..."})
```

- **An agent or LLM application**
  - the MCP server exposes `plan`, `search`, `explain` and `catalog`
  - every call resolves a full principal, including a service session with its own cap
  - an agent stuck in a loop hits `SESSION_CAP_EXCEEDED`, not the organization's monthly budget
- **A platform team**
  - multi-tenant with row-level security
  - per-project engine policy
  - an append-only, hash-chained audit log
  - shorter retention for high-PII payloads

## What it does not do

Stated plainly, because an unstated boundary reads as an oversight.

- **It does not scrape.** SerpApi is the only outbound data path
- **It does not verify upstream results.** It caches and attributes what SerpApi returns
- **It does not replace SerpApi.** It is a control plane in front of it, and needs your own SerpApi credential
- **Routing accuracy is 38.3%, not 90%**
  - the honest measured number for the deterministic adapter on 120 hand-authored tasks
  - the main failure is still wrong-engine selection, on 58 of them
  - full error analysis in [benchmark](benchmark.md), including two cases where the label, not the planner, is arguably wrong

## The surfaces

| Surface | For |
| --- | --- |
| REST API | anything |
| SSE stream | watching a run happen, one frame per real stage transition |
| Python SDK | sync and async, plus the SerpApi drop-in |
| TypeScript SDK | no runtime dependencies; Node, Deno, Bun, browser |
| CLI | `serpflow plan`, `search`, `runs`, `replay`, `catalog`, `cache` |
| MCP | agents, with their own budget identity |
| Web console | dashboard, Run Inspector, Plan Inspector, Catalog Explorer, Cache Dashboard |

## Proving it

```bash
make seed        # no API keys needed
make demo        # exits non-zero if the thesis fails
make benchmark   # reproduces the routing numbers
make test-e2e    # asserts the replan actually changed the selection
```

- Everything above runs inside the **SerpApi free tier**
- The 101-credit chain in the demo is a **projection** from catalog fan-out hints, and is never executed live

## Related

- [Demo walkthrough](demo.md)
- [Benchmark](benchmark.md)
- [Architecture overview](../architecture/overview.md)
- [Marginal replanning](../architecture/marginal-replanning.md)
- [Decision records](../adr/README.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Docs index](../README.md) | [Docs index](../README.md) | [The reference demo](../product/demo.md) |
