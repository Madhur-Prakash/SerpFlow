# The planner

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="stages: 4" src="https://img.shields.io/badge/stages-4-2F6BFF">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="Groq: BYOK" src="https://img.shields.io/badge/Groq-BYOK-F55036">
  <a href="../../backend/app/services/planner/service.py"><img alt="source: planner/service.py" src="https://img.shields.io/badge/source-planner%2Fservice.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **The planner** · page 12 of 50

**Four stages, then costing, then budget.**

- The whole sequence lives in [`app/services/planner/service.py`](../../backend/app/services/planner/service.py)
- It emits a **progress event at every transition**, and that is what the UI pipeline animates

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

Code: [`retrieval.py`](../../backend/app/services/planner/retrieval.py)

- **Returns the top candidates out of 54 engines**
- It deliberately does **not** pass every engine schema to the selector: that would be slow, expensive, and bury the real candidates
- **Scoring:** `0.72 x capability affinity + 0.28 x embedding similarity`
  - affinity dominates because engine docs use the vendor's vocabulary, not the user's. See [the catalog's note](catalog.md#the-capability-vocabulary)
- **Two expansions then run, and both matter:**
  - **substitutes of strong matches** are pulled in even when they score poorly alone. If competitors never enter the set, stage D cannot emit alternative plans, and marginal replanning has nothing to re-rank
  - **upstream producers** of strong matches are pulled in, so a chain's entry point is never missing

## Stage B: select

Code: [`mock.py`](../../backend/app/integrations/llm/mock.py) · [`groq.py`](../../backend/app/integrations/llm/groq.py)

- **Chooses up to three engines**, and records for every engine it did **not** choose a concrete reason about coverage or a trade-off
- Those reasons surface in the Plan Inspector
- **The selector may not design chains.** It picks a target capability; stage D decides what is reachable
  - with the Groq adapter this is **enforced, not requested**: any engine the model names that was not retrieved is dropped and recorded as `hallucinated: true`
- **Generic imperatives are not evidence**
  - "find" and "search" appear in nearly every intent
  - scoring them as web-search signals routes everything to `engine=google`, the exact failure SerpFlow exists to fix
  - so they are excluded from the vocabulary
- **Drill-down engines need an invitation**
  - an engine reachable only through another engine's identifier is penalised, but only when drilling down buys nothing
  - `google_patents_details` declares the same `patent_search` capability as `google_patents`, so "find the patent covering X" wants the search
  - `apple_reviews` declares `app_reviews`, which `apple_app_store` does not, so "what users say about the app" genuinely needs the second hop

## Stage C: synthesize

Code: [`text.py`](../../backend/app/core/text.py) · [`routes.py`](../../backend/app/core/routes.py)

**Deliberately rule-based:** these are reproducible decisions that must be explainable in the Run Inspector.

| Concern | Behaviour |
| --- | --- |
| Locale inference | `Seoul -> gl=kr, hl=ko`. Districts are checked before cities, so "omakase in Ginza" resolves to Japan instead of falling back to `us` |
| Date normalisation | ISO dates, "tomorrow", "in 3 weeks", "next Friday", "late November" with an approximate-day marker |
| Entity resolution | City names become IATA codes, so `google_flights` is actually routable. Both endpoints must resolve, or nothing is bound |
| Parameter binding | The free-text query maps onto whatever each engine calls it: `q`, `query`, `text`, `term`, `find_desc` |
| Freshness inference | See below |

- **With the Groq adapter, locale and dates stay deterministic**
  - a model that disagrees about `gl` silently changes the result set: not worth gambling on
- **The model may tighten a freshness level, never relax one**

### Freshness inference

```
realtime  < 15m    live prices, fares, breaking news
fresh     < 24h    today, latest, current, hotel and job listings
recent    < 7d     recent reviews, local listings
stable    any TTL  patents, papers, reference lookups
```

- **Three signal families:** temporal language in the intent, the engine's `volatility_prior`, and the query class
- **Each step gets its own level:** one intent can touch a 15-minute-prior engine and a 30-day-prior one, and needs the right bar for each
- **This is not decoration.** The cost model uses it to decide whether a warm entry is **acceptable**, not merely **available**
  - without it, marginal cost is computed against an undefined bar, and stale data gets served for time-sensitive intents

## Stage D: path-find and generate candidates

Code: [`graph.py`](../../backend/app/services/catalog/graph.py) · [`candidates.py`](../../backend/app/services/planner/candidates.py)

- **`find_paths` walks typed edges backwards** from a target, until every required parameter is either caller-supplied or produced upstream
- **A parameter that cannot be sourced invalidates the path**, and it is discarded: the planner never guesses a value it cannot produce
- **Watch for parameter-name collisions** (this caused a real bug):
  - `google.q` is the user's query, which the caller always has
  - `google_scholar_cite.q` is a Scholar `result_id` that only an upstream hop can produce
  - both are called `q`. The catalog settles it with `caller_suppliable`, and the graph honours that instead of trusting the name
- **Fan-out propagates along the chain**, which is where the 101-credit projection comes from

### Candidate plurality is a hard requirement

Three generation strategies:

| Strategy | Source | Role |
| --- | --- | --- |
| `primary` | The chosen engines' own valid chains, differing in entry point or hop count | answer |
| `substitute` | A competing engine serving the same capability | answer |
| `shallow` | Truncations of a longer chain | fallback |

Two rules decide what competes:

- **Role assignment**
  - stage B ranks its choices; the top choice defines the capability the intent asks for
  - a plan ending anywhere else answers a different question, and becomes a **fallback**
  - without this, a one-credit place lookup outranks a review-ring investigation on price, and the planner optimises a question nobody asked
- **Truncation demotion**
  - a plan whose engine list is a strict prefix of another's is a truncation, not a peer: it is cheaper **because it does less**
  - fallbacks stay in the set, persisted and visible in the Plan Inspector, but only win when nothing else fits a budget

**If exactly one answering plan exists**, the Plan records `single_candidate_reason`, naming one of:

- the engine's `single_source_note`
- that no catalog engine shares its capability tag
- that its substitutes exist but are unreachable from this intent's parameters

## What the Plan stores

Everything the Plan Inspector needs, so **nothing is recomputed in the browser**:

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

- `plan_candidates` persists **every** candidate, not just the winner. See [ADR 0014](../adr/0014-persist-every-candidate.md)

## Observability

- **Spans:** `serpflow.plan` wrapping `catalog.retrieve`, `plan.select`, `plan.synthesize`, `plan.pathfind`, `plan.candidates`, `plan.marginal_cost`
- **Metrics:** `serpflow_plan_latency_seconds` by stage, `serpflow_plan_candidates_count`, `serpflow_plan_confidence`, and `serpflow_marginal_replan_changed_selection_total`

## Next

- [Marginal replanning](marginal-replanning.md): the cost model and ranking
- [Caching](caching.md): what `inspect()` is actually looking at
- [Benchmark](../product/benchmark.md): how well this routes, honestly

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The engine catalog](../architecture/catalog.md) | [Docs index](../README.md) | [Marginal-cost replanning](../architecture/marginal-replanning.md) |
