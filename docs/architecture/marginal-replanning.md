# Marginal-cost replanning

<p>
  <a href="../architecture/README.md"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="thesis: marginal cost" src="https://img.shields.io/badge/thesis-marginal%20cost-3fcf8e">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <a href="../../backend/app/services/planner/cost.py"><img alt="source: planner/cost.py" src="https://img.shields.io/badge/source-planner%2Fcost.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../architecture/README.md) › **Marginal-cost replanning** · page 17 of 57

**This is the thesis.** Everything else in SerpFlow exists to make it possible.

> SerpFlow does not merely cache search results. It re-plans execution based on
> what is already warm, optimizing **marginal** cost rather than cold cost.

Code: [`app/services/planner/cost.py`](../../backend/app/services/planner/cost.py) · [`budget.py`](../../backend/app/services/planner/budget.py) · decision: [ADR 0001](../adr/0001-marginal-cost-replanning.md)

- `replan_on_marginal_cost` runs after [stage D](planner.md#stage-d-path-find-and-generate-candidates) of the planner, over every candidate it emitted
- It is the `inspecting_cache`, `calculating_marginal_cost`, `reranking_plans` and `checking_budget` part of the [stage sequence](../api/streaming.md#the-stage-sequence)

## The distinction

**A conventional system caches inside the executor:**

```
intent -> plan -> execute (checking the cache per step) -> cache
```

- That saves credits on the plan you **already picked**. Worth having, and SerpFlow does it too
- But the plan was chosen **before anyone looked at the cache**, so the saving is incidental

**SerpFlow inspects cache state at ranking time:**

```
intent
 -> N candidate plans
 -> inspect cache state for every step of every candidate      cache.inspect(), read-only
 -> marginal_cost = sum(cost of steps that actually require live calls)
 -> re-rank on marginal cost
 -> select
 -> execute
```

A worked example:

```
Plan A    cold cost 4    marginal cost 4
Plan B    cold cost 8    marginal cost 1     <- selected
```

- A planner comparing cold costs picks A, and **pays four credits to avoid paying one**
- An executor-level cache hit would not have helped: it would have been hitting **A's** steps, not B's
- The two cache doors, `inspect()` for the planner and `lookup()` for the executor: [two entry points](caching.md#two-entry-points)

## Available is not acceptable

The single most important rule in the cost model:

> A warm entry counts toward marginal savings **only if it also satisfies the
> step's freshness requirement**.

- A thirty-day-old cached price is **available**
- For a step whose requirement is `realtime`, it is **not acceptable**: it contributes nothing, and the step is costed as live
- `CacheState` carries **both flags separately**, and explains the gap in words:

```
exact hit in the Redis hot layer, but it is 9d old and the step requires
fresh (max 24h). Not counted as warm.
```

- Without [freshness inference](planner.md#freshness-inference), marginal cost is computed against an undefined bar, and the planner confidently serves stale data for time-sensitive intents

## Costing a step

```python
for each step in each candidate:
    freshness = per-engine requirement from stage C
    if the step's parameters are all caller-supplied:
        state = cache.inspect(engine, params, freshness)
        marginal = 0 if state.is_warm else unit_cost * fan_out
    else:
        # An identifier-bound step has no concrete value until the upstream
        # step runs, so the probe asks how many calls of this engine, in this
        # partition, under this locale, are already satisfiable.
        warm_calls = count of durable entries within the freshness bound
        marginal = max(0, fan_out - warm_calls) * unit_cost
```

- **The fan-out probe is an absolute count, not a fraction**
  - it counts unexpired, uninvalidated [`cache_entries`](../database/schema.md#cache) rows for the engine in this partition (and `gl` / `hl`), created within the freshness bound. Which identifiers they hold is not checked, because the real identifiers do not exist until the upstream step runs
  - 12 calls needed, 12 warm: costs **0**
  - 80 needed, 12 warm: costs **68**
- Narrowing the step consumes the saving rather than scaling it: the honest arithmetic
- **Every step's `CacheState` is kept**, with its reason, on the candidate's `plan_candidates` row and on each of the selected plan's `steps[]`, so the [Plan Inspector](frontend.md#routes) can show why a step was or was not free

## Ranking

Candidates are ranked **twice**:

```python
cold_rank_key     = (coverage_rank, naive_cost + penalty, -confidence, signature)
marginal_rank_key = (coverage_rank, marginal_cost + penalty, -confidence,
                     naive_cost, signature)
# penalty: full 0, partial 0.25, narrow 0.5 (COVERAGE_MARGIN_PENALTY)
```

- **Only answering plans that fit the budget are ranked.** Truncations stay in the set as fallbacks, and compete only when no answering plan fits ([role assignment](planner.md#candidate-plurality-is-a-hard-requirement))

### Coverage before price

```
full = 0    partial = 1    narrow = 2
```

- **Coverage is the primary key**, not a discount against price
- A narrow substitute is cheaper **precisely because it answers a smaller question**
  - `yelp_reviews` costs a ninth of the Google Maps contributor chain, and cannot establish reviewer identity at all
- Letting price outrank coverage makes the planner optimise a question nobody asked
- **Cost only breaks ties within a coverage band.** See [ADR 0004](../adr/0004-coverage-before-price.md)

### What `changed_selection` means

When the two rankings disagree, **the marginal ranking's plan executes**, and the fact is recorded:

```python
plan.cold_winner_candidate_id            = what cold ranking would have chosen
plan.marginal_replan_changed_selection   = True
plan.replan_explanation                  = a sentence naming both and their costs
metrics.marginal_replan_changed_selection_total.inc()
```

- **That boolean is the product, persisted** on the [`plans`](../database/schema.md#planning-and-execution) row, with the cold winner kept as a `plan_candidates` row
  - the Plan Inspector renders it
  - the overview counts it
  - the e2e suite, [`test_marginal_replanning.py`](../../backend/tests/e2e/test_marginal_replanning.py), asserts it
- **A cache hit on the same plan does not count.** That is the distinction the whole design turns on

## Budget-aware reduction happens before ranking

The planner runs the steps in this order:

```
1. generate candidate plans
2. calculate marginal costs
3. identify plans that fit
4. choose the appropriate valid plan
5. record what was reduced, if anything
```

- **Step 3 before step 4 matters more than it looks**
  - reducing **after** selection compares two plans at costs neither would actually run at
  - so every over-budget candidate is reduced **first**, then the reduced costs are ranked
- **The cap is the tighter of two numbers:** the request's own `budget`, and the remaining allowance of the tightest configured [budget](../database/schema.md#governance) that applies (organization, project, API key or service session)

### How reduction works

- **Fan-out is scaled proportionally across every widened step**, not squeezed into the last hop
- **The shape of a plan is what makes its answer meaningful**
  - a contributor chain sampled 3 places deep and 12 contributors wide is still a contributor chain
  - the same budget spent on 18 places and 1 contributor is not
- **Only if proportional scaling cannot fit** does the reducer drop terminal steps, recorded as an `omitted_step` instead of happening quietly

### Every reduction carries an impact note

```json
{
  "type": "fan_out_cap",
  "step": 2,
  "engine": "google_maps_contributor_reviews",
  "original": 80,
  "reduced": 12,
  "impact_note": "Contributor sampling reduced; ring-detection recall will be lower - a reviewer active only on venues outside the sample will not be linked. Reduced from 80 to 12 calls."
}
```

- **A planner that silently truncates is worse than one that refuses:** the caller acts on a result they believe is complete
- **Notes are written per capability** in [`budget.py`](../../backend/app/services/planner/budget.py), so they say **what** is lost, not just that something was
- The reductions travel on the `checking_budget` [SSE frame](../api/streaming.md#what-detail-carries) and persist as the plan's `budget_reduction`

### When nothing fits

**The planner does not refuse.**

- **Every candidate that cannot fit is excluded from ranking**, with a rejection reason naming its minimum viable cost: "Cannot fit the 20-credit budget even after fan-out reduction; the minimum viable shape still costs N credits."
- **A truncation that fits wins** if one exists: this is what fallbacks are for
- **If none fits, the best-ranked candidate (coverage first, then marginal cost) is selected unreduced**, and `budget_reduction.note` says how many candidates could not be reduced to fit
- **What then stops the spend is the executor**, which checks the configured budgets before every live call and raises `BUDGET_EXHAUSTED` ([budget enforcement](executor.md#budget-enforcement))
  - a per-request `budget` with no configured budget behind it is a planning cap only; the executor does not re-check it
- **`BUDGET_INFEASIBLE` is defined but never raised at HEAD:** `BudgetInfeasibleError` exists in [`exceptions.py`](../../backend/app/core/exceptions.py) and in the [error table](../api/overview.md#errors), but no code path raises it

## Projections are never executed

- `projected_full_scale_cost` is the **uncapped** shape: 101 credits for the [reference chain](catalog.md#the-reference-demo-chain)
- It is displayed, clearly labelled as a projection, and **never run live**
- One execution would use 40% of the SerpApi free tier

## Worked example: the reference demo

```
Phase 1  cold cache, dry run, 20-credit budget
         (planning costs nothing, and warms nothing)

  candidates          google_local -> google_maps_reviews -> google_maps_contributor_reviews   19 cr  (uncapped 51)
                      google_maps  -> google_maps_reviews -> google_maps_contributor_reviews   19 cr  (uncapped 101)
                      yelp -> yelp_reviews  (narrow coverage)                                  11 cr
                      plus five truncations, retained as fallbacks

  reduction           both full chains are scaled down to fit the budget before ranking
  cold ranking        google_local chain wins: same coverage, same reduced cost,
                      higher selector confidence
  marginal ranking    identical, nothing is warm
  changed_selection   false

Phase 2  a second project, whose policy pins the Google Maps corpus, runs the
         same investigation at full scale against the deterministic mock.
         0 credits spent. The shared organization cache now holds
         google_maps, 20 google_maps_reviews entries and 80
         google_maps_contributor_reviews entries.

Phase 3  same intent, same catalog version, same 20-credit budget, warm cache

  google_maps chain   naive 101    marginal 0    all three steps warm
  google_local chain  naive  51    marginal 1    entry point still cold

  reduction           none: both chains fit the budget on the margin
  cold ranking        google_local chain  (51 < 101)
  marginal ranking    google_maps chain   (0 < 1)
  changed_selection   TRUE
```

- Same intent. Same catalog. **A different plan, because of cache state**
- **Reduction depends on cache state too.** Cold, both full chains cost more than 20 credits on the margin and are cut to 19 before ranking, so 51 and 101 are only their uncapped projections. Warm, nothing needs cutting, and the figures are the uncapped shapes
- Phase 2 only reaches phase 3 because the organization shares its cache across projects: [organization-level sharing](caching.md#organization-level-sharing)
- Reproduce with `make demo` ([proving the thesis](../deployment/local.md#proving-the-thesis)), which exits non-zero if this stops being true. If it does: [troubleshooting](../operations/troubleshooting.md#make-demo-exits-non-zero)
- Walkthrough: [the demo guide](../product/demo.md#the-three-phases)

## Instrumentation

| Metric | What it tells you |
| --- | --- |
| [`serpflow_marginal_replan_changed_selection_total`](../operations/observability.md#the-thesis-metric) | How often the thesis actually fired |
| `serpflow_marginal_credits_avoided_total` | `naive_cost - marginal_cost` on selected plans |
| [`serpflow_plan_candidates_count`](../operations/observability.md#planner) | Candidate plurality. Trending to 1 means nothing to re-rank |
| [`serpflow_credits_saved_total{source}`](../operations/observability.md#spend-and-savings) | Cache-layer savings (`exact`, `semantic`) as they happen |

- **The waterfall comes from the ledger, not the metrics.** The overview dashboard and [`/v1/analytics/savings`](../api/overview.md#governance) sum [`budget_ledger`](../database/schema.md#governance) rows, from naive execution down to actual spend
  - savings rows by source: `routing` (the cold winner's cold cost minus the selected plan's, when positive, in [`runs.py`](../../backend/app/services/runs.py)), `exact`, `semantic` and `archive`
  - routing and archive savings are written only to the ledger, never to `serpflow_credits_saved_total`
- **Actual spend is every credited live call**, written as a `spend` row by the executor
  - that includes a search SerpApi bills but finds nothing for: it is a successful, empty result, and is recorded and cached like any other ([billed empty results](caching.md#billed-empty-results))
  - before that fix, such a search was treated as a failure, and the ledger recorded 0 credits for a search SerpApi had charged

## Related

- [ADR 0001](../adr/0001-marginal-cost-replanning.md): why candidates are ranked on marginal cost, not cold cost
- [The planner](planner.md#stage-d-path-find-and-generate-candidates): where the candidates and their freshness requirements come from
- [Caching](caching.md#two-entry-points): what `inspect()` reads, and the layers behind it
- [The executor](executor.md#budget-enforcement): the per-call budget check, and the spend and saving rows it writes
- [The reference demo](../product/demo.md) and [the thesis](../product/product-overview.md#the-thesis): the claim this page implements, reproduced end to end with `make demo`
- [Database schema](../database/schema.md#governance): `budgets` and `budget_ledger`, where caps and spend live
- [Observability](../operations/observability.md#the-thesis-metric): the one metric the system exists to move above zero

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The planner](../architecture/planner.md) | [Docs index](../README.md) · [Architecture index](../architecture/README.md) | [Caching](../architecture/caching.md) |
