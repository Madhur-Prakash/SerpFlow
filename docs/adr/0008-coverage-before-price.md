# 0008. Rank on coverage before price

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/services/planner/candidates.py"><img alt="source: planner/candidates.py" src="https://img.shields.io/badge/source-planner%2Fcandidates.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0008. Rank on coverage before price** · page 51 of 57

**Status** Accepted

## Context

- **Once candidate plans are [costed](../architecture/marginal-replanning.md#costing-a-step), the obvious sort key is cost:** cheapest wins
- **That produces a planner that confidently answers the wrong question:**

```
yelp -> yelp_reviews                                              11 credits
google_maps -> google_maps_reviews -> contributor_reviews        101 credits
```

- For "find coordinated review rings among Koramangala cafes" (the [reference demo](../product/demo.md#the-question)), **the Yelp chain is a ninth of the price**
- **It also cannot answer the question:**
  - Yelp exposes reviewer **display names**, but no stable contributor identity
  - so it cannot establish that the same person reviewed five venues
  - it is cheap **precisely because it answers a smaller question**
- **A pure cost ranking picks it every time**, returns a plausible-looking result, and the caller has no way to know the question changed

## Decision

**[Coverage is the primary sort key](../architecture/marginal-replanning.md#coverage-before-price). Cost only breaks ties within a coverage band.**

```python
# app/services/planner/cost.py
COVERAGE_RANK = {"full": 0, "partial": 1, "narrow": 2}

def marginal_rank_key(self) -> tuple:
    return (
        self.coverage_rank,                             # first
        self.marginal_cost + self.coverage_penalty,
        -self.plan.confidence,
        self.naive_cost,
        self.plan.signature,
    )
```

- **A `full`-coverage plan at 101 credits beats a `narrow` plan at 11**
- **Within a band**, a weaker route still has to be meaningfully cheaper to win: `COVERAGE_MARGIN_PENALTY` (`full` 0.0, `partial` 0.25, `narrow` 0.5)
- **The cold ranking uses the same first key** (`cold_rank_key`), so cold and marginal rankings can disagree on price within a band, never on coverage ([ADR 0001](0001-marginal-cost-replanning.md))
- **A substitute plan's coverage comes from the catalog:** the `coverage` and [trade-off note](../architecture/catalog.md#coverage-and-notes) authored on its substitute edge ([ADR 0002](0002-typed-catalog-edges.md))
- **Narrow plans are not discarded.** They are kept as **[budget fallbacks](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking)**, with their trade-off note attached
  - when no full-coverage plan fits the budget, the caller is offered the cheap one, with an explicit statement of what it cannot do:

```json
{ "plan": "yelp>yelp_reviews", "naive_cost": 11, "coverage": "narrow",
  "trade_off_note": "Yelp exposes reviewer display names but no stable contributor identity ..." }
```

- **Related: plans are assigned a role**, `ROLE_ANSWER` or `ROLE_FALLBACK` ([`candidates.py`](../../backend/app/services/planner/candidates.py))
  - only plans ending at the target capability compete for selection
  - truncations and different-capability plans are fallbacks by construction

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Cheapest wins** | Optimises a question nobody asked |
| **A weighted score combining coverage and cost** | A large enough price gap then overrides coverage: the same failure, further down the price curve. Coverage is **categorical**, not a quantity to trade off |
| **Discard narrow plans entirely** | Removes the budget fallback. When nothing full-coverage fits, a partial answer with its limits stated beats [`BUDGET_INFEASIBLE`](../api/overview.md#errors) |

## Cost

- **The planner is more expensive by default:** the demo shows a 101-credit plan where an 11-credit plan existed
  - worse in a headline number, correct in substance
- **The demo got harder to construct**
  - once coverage became the primary key, the tuned [phase-2 denylist](../product/demo.md#phase-2-a-different-project-warms-the-maps-chain) no longer produced disjoint warm sets
  - `google_local` had to be added to it, so the two full-coverage contributor chains would actually disagree ([`backend/scripts/demo.py`](../../backend/scripts/demo.py))
- **Update (2026-10-11): `BUDGET_INFEASIBLE` is defined but not raised**
  - when no answering plan fits the cap after reduction, any plan that does fit is ranked instead, a truncation included; when none fits, every candidate is ranked and one is still selected, each over-budget one carrying a "cannot fit" `rejection_reason` ([`cost.py`](../../backend/app/services/planner/cost.py))
  - the request's `budget` caps planning only: execution stops at a configured budget, with `BUDGET_EXHAUSTED` ([errors](../api/overview.md#errors))

## See also

- [Marginal-cost replanning: coverage before price](../architecture/marginal-replanning.md#coverage-before-price): the rank keys and margin penalty as implemented
- [The planner, stage D](../architecture/planner.md#stage-d-path-find-and-generate-candidates): where substitute and truncated candidates are generated and given a role
- [The engine catalog: coverage and notes](../architecture/catalog.md#coverage-and-notes): where each substitute's coverage band and trade-off note are authored
- [The reference demo, phase 2](../product/demo.md#phase-2-a-different-project-warms-the-maps-chain): the denylist this decision forced to change
- [Routing benchmark](../product/benchmark.md): ranks each task's candidates coverage-first, cold, so it scores the planner that ships
- [Troubleshooting: `NO_VIABLE_PLAN`](../operations/troubleshooting.md#no_viable_plan): what happens when no candidate, of any coverage, reaches the target
- [ADR 0001: marginal cost replanning](0001-marginal-cost-replanning.md): the price key that coverage sorts ahead of
- [ADR 0002: typed catalog edges](0002-typed-catalog-edges.md): the substitute edges that carry each plan's coverage

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0007: Interactive search does not go through K…](../adr/0007-interactive-search-bypasses-kafka.md) | [Docs index](../README.md) | [ADR 0009: Available is not acceptable: freshness g…](../adr/0009-freshness-gates-warmth.md) |
