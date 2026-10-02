# Product overview

SerpFlow is a search control plane for SerpApi. It takes a natural-language
intent, works out which engine or engine chain answers it, inspects what is
already cached, computes the **marginal** cost of every candidate plan, re-ranks
on that, and executes only the searches that still need a live call.

This page is the why. The architecture docs are the how.

## The problem

A team using SerpApi at any scale ends up building four things, badly, in the
application layer:

**Engine selection.** SerpApi exposes dozens of engines with different
parameters, different result shapes and different costs. Which one answers
"what is Nvidia trading at right now" is a judgement call, and it gets hardcoded
into whichever service happened to need it first.

**Chaining.** Some questions cannot be answered by one engine. Reviewer
identity is reachable only through `google_maps_reviews.reviews[].user.contributor_id`,
which means Maps, then reviews, then contributor reviews. That chain lives in a
script somebody wrote once, and nothing else in the company can discover it.

**Caching.** Results get cached by request hash, because that is the obvious
thing. Which means a paraphrase of yesterday's question is a full-price miss,
and a stale entry for a volatile query is served as if it were live.

**Cost control.** Spend is visible as one number on the SerpApi dashboard at the
end of the month. Which team, which feature, which query shape — unknown.

Each is solvable. Solved separately, in four services, they do not compose: the
cache does not know what the router is choosing between, so the router keeps
choosing the expensive-but-already-cached plan's cheaper-but-cold rival.

## The thesis

**Cache state should change which plan is selected, not just make the selected
plan faster.**

That is the one claim this system makes, and it is deliberately falsifiable.

Conventional caching ranks plans on cold cost, picks a winner, and then checks
the cache. If the winner happens to be cached, you save money. SerpFlow ranks
on **marginal** cost: the cost of the steps that still need a live call. A plan
that costs 101 credits cold but is entirely warm costs 0, and beats a plan that
costs 51 cold and is cold in fact.

```
cold ranking         google_local -> google_maps_reviews -> contributor_reviews   51 credits
marginal ranking     google_maps  -> google_maps_reviews -> contributor_reviews    0 credits

same intent, same catalog version, different selected plan
```

The metric is `serpflow_marginal_replan_changed_selection_total`, and
`make demo` exits non-zero if it is zero. A cache hit on the same plan is
explicitly **not** sufficient — that is the thing everyone already has.

Detail: [marginal replanning](../architecture/marginal-replanning.md).

## What makes it work

Four pieces, none of which is optional.

### A typed catalog

54 engines described with their required parameters, produced fields, cost,
volatility prior and capability tags. Two edge sets on top:

- **Dependency edges** (`satisfied_by` / `feeds`) — how engines chain. Without
  them, multi-hop chains are not computable and `/paths` has nothing to answer.
- **Substitute edges** (`capability_tags` / `substitutes`) — how engines
  compete. Without them, there is only ever one candidate plan, and a ranking
  with one entry cannot change.

Both are mandatory. The thesis needs alternatives to choose between.

[Catalog architecture](../architecture/catalog.md).

### A four-stage planner

```
A  retrieve      candidate engines, by tag affinity and embedding similarity
B  select        which capability actually answers this
C  synthesize    dates, locale, entities, parameter binding
D  generate      multiple competing plans, via substitutes and path-finding
```

Stage D is the one that matters for the thesis. It produces a candidate **set**,
not a winner, and every candidate is persisted — so the Plan Inspector can show
why the winner won rather than asserting that it did.

[Planner architecture](../architecture/planner.md).

### Four cache layers

```
hot        Redis, exact match
exact      PostgreSQL, request hash
semantic   pgvector, with a deterministic guard
archive    the SerpApi Searches Archive
```

The semantic layer is the interesting one, and the dangerous one. "Nvidia Q3
2024 revenue" and "Nvidia Q4 2024 revenue" embed close together. A cosine
threshold alone will serve one for the other, confidently, and that is a
correctness failure dressed as a saving.

So the entity, numeral and version guard runs **independently of the similarity
score**, on exact set equality. Both queries mention a quarter; the sets differ;
rejected, whatever the cosine says.

And availability is not acceptability: an entry only counts as warm if it
satisfies the step's inferred freshness bound.

```
realtime   < 15m      fresh   < 24h      recent   < 7d      stable
```

[Caching architecture](../architecture/caching.md).

### Governance that is computed, not estimated

Budgets at four scopes — organization, project, API key, service session — with
the tightest applicable one winning. Savings decomposed by the mechanism that
produced them (`routing`, `exact`, `semantic`, `archive`), because "we saved
credits" is not a claim until you can say which of four things did it.

The ledger carries `project_id` and `beneficiary_project_id` separately, so
cross-project benefit from a shared cache is a figure rather than a guess.

Spend attribution runs organization to project to principal to run to step to
engine.

## Who it is for

**An engineering team using SerpApi directly.** The drop-in compat client keeps
existing code working; the base URL and key change, and caching, budgets and
provenance arrive without a rewrite.

```python
from serpflow import SerpApiCompat
search = SerpApiCompat({"engine": "google_maps", "q": "...", "api_key": "sf_..."})
```

**An agent or an LLM application.** The MCP server exposes `plan`, `search`,
`explain` and `catalog`. Every call resolves a full principal including a
service session with its own cap, so an agent in a loop hits
`SESSION_CAP_EXCEEDED` rather than the organization's monthly budget.

**A platform team.** Multi-tenant with row-level security, per-project engine
policy, an append-only hash-chained audit log, and retention that is shorter
for high-PII payloads.

## What it does not do

Stated plainly, because an unstated boundary reads as an oversight.

- **It does not scrape.** SerpApi is the only outbound data path.
- **It does not verify upstream results.** It caches and attributes what
  SerpApi returns.
- **It does not replace SerpApi.** It is a control plane in front of it, and
  needs your own SerpApi credential.
- **Routing accuracy is 38.3%, not 90%.** That is the honest measured number
  for the deterministic adapter on 120 hand-authored tasks, with the dominant
  failure mode still wrong-engine selection on 58 of them. The full error
  analysis is in [benchmark](benchmark.md), including the two cases where the
  label is arguably wrong rather than the planner.

## The surfaces

| Surface | For |
| --- | --- |
| REST API | anything |
| SSE stream | watching a run happen, frame per real stage transition |
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

Everything above runs inside the SerpApi free tier. The 101-credit chain in the
demo is a **projection**, computed from catalog fan-out hints, and is never
executed live.

## Related

- [Demo walkthrough](demo.md)
- [Benchmark](benchmark.md)
- [Architecture overview](../architecture/overview.md)
- [Marginal replanning](../architecture/marginal-replanning.md)
- [Decision records](../adr/README.md)
