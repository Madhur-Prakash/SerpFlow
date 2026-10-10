# 0008. Rank on coverage before price

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0008. Rank on coverage before price** · page 44 of 50

**Status** Accepted

## Context

- **Once candidate plans are costed, the obvious sort key is cost:** cheapest wins
- **That produces a planner that confidently answers the wrong question:**

```
yelp -> yelp_reviews                                              11 credits
google_maps -> google_maps_reviews -> contributor_reviews        101 credits
```

- For "find coordinated review rings among Koramangala cafes", **the Yelp chain is a ninth of the price**
- **It also cannot answer the question:**
  - Yelp exposes reviewer **display names**, but no stable contributor identity
  - so it cannot establish that the same person reviewed five venues
  - it is cheap **precisely because it answers a smaller question**
- **A pure cost ranking picks it every time**, returns a plausible-looking result, and the caller has no way to know the question changed

## Decision

**Coverage is the primary sort key. Cost only breaks ties within a coverage band.**

```python
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
- **Narrow plans are not discarded.** They are kept as **budget fallbacks**, with their trade-off note attached
  - when no full-coverage plan fits the budget, the caller is offered the cheap one, with an explicit statement of what it cannot do:

```json
{ "plan": "yelp>yelp_reviews", "naive_cost": 11, "coverage": "narrow",
  "trade_off_note": "Yelp exposes reviewer display names but no stable contributor identity ..." }
```

- **Related: plans are assigned a role**, `ROLE_ANSWER` or `ROLE_FALLBACK`
  - only plans ending at the target capability compete for selection
  - truncations and different-capability plans are fallbacks by construction

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Cheapest wins** | Optimises a question nobody asked |
| **A weighted score combining coverage and cost** | A large enough price gap then overrides coverage: the same failure, further down the price curve. Coverage is **categorical**, not a quantity to trade off |
| **Discard narrow plans entirely** | Removes the budget fallback. When nothing full-coverage fits, a partial answer with its limits stated beats `BUDGET_INFEASIBLE` |

## Cost

- **The planner is more expensive by default:** the demo shows a 101-credit plan where an 11-credit plan existed
  - worse in a headline number, correct in substance
- **The demo got harder to construct**
  - once coverage became the primary key, the tuned phase-2 denylist no longer produced disjoint warm sets
  - `google_local` had to be added to it, so the two full-coverage contributor chains would actually disagree

## See also

- [Planner architecture](../architecture/planner.md)
- [Marginal replanning](../architecture/marginal-replanning.md)
- [ADR 0001: marginal cost replanning](0001-marginal-cost-replanning.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0007: Interactive search does not go through K…](../adr/0007-interactive-search-bypasses-kafka.md) | [Docs index](../README.md) | [ADR 0009: Available is not acceptable: freshness g…](../adr/0009-freshness-gates-warmth.md) |
