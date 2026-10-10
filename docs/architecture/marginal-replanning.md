# Marginal-cost replanning

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="thesis: marginal cost" src="https://img.shields.io/badge/thesis-marginal%20cost-3fcf8e">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <a href="../../backend/app/services/planner/cost.py"><img alt="source: planner/cost.py" src="https://img.shields.io/badge/source-planner%2Fcost.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **Marginal-cost replanning** · page 13 of 50

**This is the thesis.** Everything else in SerpFlow exists to make it possible.

> SerpFlow does not merely cache search results. It re-plans execution based on
> what is already warm, optimizing **marginal** cost rather than cold cost.

Code: [`app/services/planner/cost.py`](../../backend/app/services/planner/cost.py) · [`budget.py`](../../backend/app/services/planner/budget.py)

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
 -> inspect cache state for every step of every candidate
 -> marginal_cost = sum(cost of steps that actually require live calls)
 -> re-rank on marginal cost
 -> select
 -> execute
```

The spec's own example:

```
Plan A    cold cost 4    marginal cost 4
Plan B    cold cost 8    marginal cost 1     <- selected
```

- A planner comparing cold costs picks A, and **pays four credits to avoid paying one**
- An executor-level cache hit would not have helped: it would have been hitting **A's** steps, not B's

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

- Without freshness inference, marginal cost is computed against an undefined bar, and the planner confidently serves stale data for time-sensitive intents

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
  - 12 calls needed, 12 warm: costs **0**
  - 80 needed, 12 warm: costs **68**
- Narrowing the step consumes the saving rather than scaling it: the honest arithmetic

## Ranking

Candidates are ranked **twice**:

```python
cold_rank_key     = (coverage_rank, naive_cost + penalty, -confidence, signature)
marginal_rank_key = (coverage_rank, marginal_cost + penalty, -confidence,
                     naive_cost, signature)
```

### Coverage before price

```
full = 0    partial = 1    narrow = 2
```

- **Coverage is the primary key**, not a discount against price
- A narrow substitute is cheaper **precisely because it answers a smaller question**
  - `yelp_reviews` costs a ninth of the Google Maps contributor chain, and cannot establish reviewer identity at all
- Letting price outrank coverage makes the planner optimise a question nobody asked
- **Cost only breaks ties within a coverage band.** See [ADR 0008](../adr/0008-coverage-before-price.md)

### What `changed_selection` means

When the two rankings disagree, **the marginal ranking's plan executes**, and the fact is recorded:

```python
plan.cold_winner_candidate_id            = what cold ranking would have chosen
plan.marginal_replan_changed_selection   = True
plan.replan_explanation                  = a sentence naming both and their costs
metrics.marginal_replan_changed_selection_total.inc()
```

- **That boolean is the product, persisted**
  - the Plan Inspector renders it
  - the overview counts it
  - the e2e suite asserts it
- **A cache hit on the same plan does not count.** That is the distinction the whole design turns on

## Budget-aware reduction happens before ranking

Section 16 orders the steps:

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
- **If nothing fits even after reduction**, the planner raises `BUDGET_INFEASIBLE`, listing what the cheapest option would cost

## Projections are never executed

- `projected_full_scale_cost` is the **uncapped** shape: 101 credits for the reference chain
- It is displayed, clearly labelled as a projection, and **never run live**
- One execution would use 40% of the SerpApi free tier

## Worked example: the reference demo

```
Phase 1  cold cache, dry run (planning costs nothing, and warms nothing)

  candidates          google_local -> google_maps_reviews -> google_maps_contributor_reviews   51 cr
                      google_maps  -> google_maps_reviews -> google_maps_contributor_reviews  101 cr
                      yelp -> yelp_reviews  (narrow coverage, fallback)                        11 cr

  cold ranking        google_local chain wins: same coverage, cheaper
  marginal ranking    identical, nothing is warm
  changed_selection   false

Phase 2  a second project, whose policy pins the Google Maps corpus, runs the
         same investigation at full scale against the deterministic mock.
         0 credits spent. The shared organization cache now holds
         google_maps, 20 google_maps_reviews entries and 80
         google_maps_contributor_reviews entries.

Phase 3  same intent, same catalog version, warm cache

  google_maps chain   naive 101    marginal 0    all three steps warm
  google_local chain  naive  51    marginal 1    entry point still cold

  cold ranking        google_local chain  (51 < 101)
  marginal ranking    google_maps chain   (0 < 1)
  changed_selection   TRUE
```

- Same intent. Same catalog. **A different plan, because of cache state**
- Reproduce with `make demo`, which exits non-zero if this stops being true
- Walkthrough: [the demo guide](../product/demo.md)

## Instrumentation

| Metric | What it tells you |
| --- | --- |
| `serpflow_marginal_replan_changed_selection_total` | How often the thesis actually fired |
| `serpflow_marginal_credits_avoided_total` | `naive_cost - marginal_cost` on selected plans |
| `serpflow_plan_candidates_count` | Candidate plurality. Trending to 1 means nothing to re-rank |
| `serpflow_credits_saved_total{source}` | Savings by mechanism: routing, exact, semantic, archive |

- The overview dashboard and `/v1/analytics/savings` turn those into a **waterfall** from naive execution down to actual spend

## Related

- [ADR 0001: rank on marginal cost](../adr/0001-marginal-cost-replanning.md)
- [ADR 0009: freshness gates warmth](../adr/0009-freshness-gates-warmth.md)
- [Caching](caching.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The planner](../architecture/planner.md) | [Docs index](../README.md) | [Caching](../architecture/caching.md) |
