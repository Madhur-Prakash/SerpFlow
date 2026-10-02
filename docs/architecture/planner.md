# The planner

Four stages, then costing, then budget. The whole sequence lives in
[`app/services/planner/service.py`](../../backend/app/services/planner/service.py)
and emits a progress event at every transition, which is what the UI pipeline
animates.

```
intent
  |
  A. RETRIEVE      top 8 candidates, expanded by substitution
  |
  B. SELECT        chosen engines, and why each rejected one lost
  |
  C. SYNTHESIZE    dates, locale, entities, parameters, freshness
  |
  D. PATH-FIND     valid chains over typed edges -> N candidate plans
  |
  cost model       cache state per step per candidate -> marginal cost
  |
  re-rank          cold ranking vs marginal ranking
  |
  budget           reduce to fit, record what that cost
  |
  selected plan
```

## Stage A: retrieve

[`retrieval.py`](../../backend/app/services/planner/retrieval.py)

Returns the top candidates out of 54 engines. It deliberately does **not** pass
every engine schema to the selector on each call: that would be slow, expensive
and would bury the real candidates.

Scoring is `0.72 x capability affinity + 0.28 x embedding similarity`.
Capability affinity dominates because engine documentation uses the vendor's
vocabulary rather than the user's - see
[the catalog's note on this](catalog.md#the-capability-vocabulary).

Two expansions then run, and both matter:

- **Substitutes of strong matches** are pulled in even when they score poorly
  on their own. If competing engines never enter the candidate set, stage D
  cannot emit alternative plans and marginal replanning has nothing to
  re-rank.
- **Upstream producers** of strong matches are pulled in, so a chain's entry
  point is never missing from the set.

## Stage B: select

[`mock.py`](../../backend/app/integrations/llm/mock.py) /
[`groq.py`](../../backend/app/integrations/llm/groq.py)

Chooses up to three engines and records, for every engine it did not choose, a
concrete reason referencing coverage or a trade-off. Those reasons surface in
the Plan Inspector.

The selector may **not** design chains. It picks a target capability; stage D
decides what is actually reachable. With the Groq adapter this is enforced
rather than requested: any engine the model names that is not in the retrieved
candidate set is dropped and recorded as `hallucinated: true` rather than
executed.

Two behaviours worth knowing:

**Generic imperatives are not evidence.** "find" and "search" appear in nearly
every intent. Scoring them as web-search signals routes everything to
`engine=google`, which is precisely the failure mode SerpFlow exists to fix, so
they are excluded from the vocabulary.

**Drill-down engines need an invitation.** An engine reachable only through
another engine's identifier is penalised - but only when drilling down buys
nothing. `google_patents_details` declares the same `patent_search` capability
as `google_patents`, so "find the patent covering X" wants the search.
`apple_reviews` declares `app_reviews`, which `apple_app_store` does not, so
"what users say about the app" genuinely needs the second hop.

## Stage C: synthesize

[`text.py`](../../backend/app/core/text.py),
[`routes.py`](../../backend/app/core/routes.py)

Deliberately rule-based, because these are reproducible decisions that have to
be explainable in the Run Inspector:

| Concern | Behaviour |
| --- | --- |
| Locale inference | `Seoul -> gl=kr, hl=ko`. Districts are consulted before cities, so "omakase in Ginza" resolves to Japan rather than falling back to `us`. |
| Date normalisation | ISO dates, "tomorrow", "in 3 weeks", "next Friday", "late November" with an approximate-day marker. |
| Entity resolution | City names become IATA codes, so `google_flights` is actually routable. Both endpoints must resolve or nothing is bound. |
| Parameter binding | The free-text query maps onto whatever each engine calls it: `q`, `query`, `text`, `term`, `find_desc`. |
| Freshness inference | See below. |

With the Groq adapter, locale and dates stay deterministic. A model that
disagrees about `gl` silently changes the result set, and that is a benchmark
discriminator worth not gambling on. The model may **tighten** a freshness
level but never relax one.

### Freshness inference

```
realtime  < 15m    live prices, fares, breaking news
fresh     < 24h    today, latest, current, hotel and job listings
recent    < 7d     recent reviews, local listings
stable    any TTL  patents, papers, reference lookups
```

Three signal families, as specified: temporal language in the intent, the
engine's `volatility_prior`, and the query class. Each step gets its own level,
because one intent can touch a 15-minute-prior engine and a 30-day-prior one
and needs the right bar for each.

This is not decoration. The cost model consumes it to decide whether a warm
entry is **acceptable**, not merely **available**. Without it, marginal cost is
computed against an undefined bar and stale data gets served for time-sensitive
intents.

## Stage D: path-find and generate candidates

[`graph.py`](../../backend/app/services/catalog/graph.py),
[`candidates.py`](../../backend/app/services/planner/candidates.py)

`find_paths` walks typed edges backwards from a target until every required
parameter is either caller-supplied or produced by an upstream engine. A
parameter that cannot be sourced makes the path invalid and it is discarded -
the planner never guesses a value it cannot produce.

One subtlety that caused a real bug: parameter names collide across engines.
`google.q` is the user's query and the caller always has one; `google_scholar_cite.q`
is a Scholar `result_id` that only an upstream hop can produce. Both are called
`q`. The catalog settles it with `caller_suppliable`, and the graph honours
that rather than taking the name at face value.

Fan-out propagates along the chain, which is where the 101-credit projection
comes from.

### Candidate plurality is a hard requirement

Three generation strategies:

| Strategy | Source | Role |
| --- | --- | --- |
| `primary` | The chosen engines' own valid chains, which differ in entry point or hop count | answer |
| `substitute` | A competing engine serving the same capability | answer |
| `shallow` | Truncations of a longer chain | fallback |

Two rules decide what competes:

- **Role assignment.** Stage B ranks its choices; the top choice defines the
  capability the intent is asking for. A plan terminating somewhere else
  answers a different question and becomes a fallback. Without this, a
  one-credit place lookup outranks a review-ring investigation on price and the
  planner optimises a question nobody asked.
- **Truncation demotion.** A plan whose engine list is a strict prefix of
  another plan's is a truncation, not a peer: it is cheaper precisely because
  it does less. Fallbacks stay in the set, persisted and visible in the Plan
  Inspector, but they only win when nothing else fits a budget.

If exactly one answering plan exists, the Plan records
`single_candidate_reason` explaining why - naming the engine's
`single_source_note`, or that no catalog engine shares its capability tag, or
that its substitutes exist but are unreachable from this intent's parameters.

## What the Plan stores

Everything the Plan Inspector needs, so nothing is recomputed in the browser:

```
intent, steps, parameter_bindings
naive_cost, marginal_cost, projected_full_scale_cost
warm_steps[]                      which steps are free, and why
freshness_requirements[]          per step, with the signals that set it
budget_reduction                  what was cut and what that costs you
confidence, catalog_version
candidate_count, single_candidate_reason
rejected_alternatives[]           every loser, with its reason
rejected_engines[]                stage B's rejections
cold_winner_candidate_id          what cold ranking would have chosen
marginal_replan_changed_selection the thesis, as a boolean
replan_explanation                the thesis, in a sentence
stage_trace[]                     every stage transition with timings
```

`plan_candidates` persists **every** candidate, not only the winner.

## Observability

Spans: `serpflow.plan` wrapping `catalog.retrieve`, `plan.select`,
`plan.synthesize`, `plan.pathfind`, `plan.candidates`, `plan.marginal_cost`.

Metrics: `serpflow_plan_latency_seconds` by stage,
`serpflow_plan_candidates_count`, `serpflow_plan_confidence`, and
`serpflow_marginal_replan_changed_selection_total`.

## Next

- [Marginal replanning](marginal-replanning.md) - the cost model and ranking
- [Caching](caching.md) - what `inspect()` is actually looking at
- [Benchmark](../product/benchmark.md) - how well this routes, honestly
