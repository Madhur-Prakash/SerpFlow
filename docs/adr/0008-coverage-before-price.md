# 0008. Rank on coverage before price

**Status** Accepted

## Context

Once candidate plans are costed, the obvious sort key is cost: cheapest wins.

That produces a planner that confidently answers the wrong question.

```
yelp -> yelp_reviews                                              11 credits
google_maps -> google_maps_reviews -> contributor_reviews        101 credits
```

For "find coordinated review rings among Koramangala cafes", the Yelp chain is
a ninth of the price. It is also incapable of answering: Yelp exposes reviewer
**display names** but no stable contributor identity, so it cannot establish
that the same person reviewed five venues. It is cheap precisely because it
answers a smaller question.

A pure cost ranking picks it every time, returns a plausible-looking result,
and the caller has no way to know the question changed.

## Decision

Coverage is the **primary** sort key. Cost only breaks ties within a coverage
band.

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

A `full`-coverage plan at 101 credits beats a `narrow` plan at 11. Within a
band, a weaker route still has to be meaningfully cheaper to win, which is what
`COVERAGE_MARGIN_PENALTY` (`full` 0.0, `partial` 0.25, `narrow` 0.5)
expresses.

Narrow plans are not discarded. They are retained as **budget fallbacks** with
their trade-off note attached, so when no full-coverage plan fits the budget
the caller is offered the cheap one with an explicit statement of what it
cannot do:

```json
{ "plan": "yelp>yelp_reviews", "naive_cost": 11, "coverage": "narrow",
  "trade_off_note": "Yelp exposes reviewer display names but no stable contributor identity ..." }
```

Related: plans are assigned a role, `ROLE_ANSWER` or `ROLE_FALLBACK`. Only
plans terminating at the target capability compete for selection; truncations
and different-capability plans are fallbacks by construction.

## Alternatives rejected

**Cheapest wins.** Optimises a question nobody asked.

**A weighted score combining coverage and cost.** Then a sufficiently large
price gap overrides coverage, which is the failure mode again, just further
down the price curve. Coverage is categorical, not a quantity to trade off.

**Discard narrow plans entirely.** Removes the budget fallback. When nothing
full-coverage fits, a partial answer with its limitations stated is more useful
than `BUDGET_INFEASIBLE`.

## Cost

The planner is more expensive by default, and the demo shows a 101-credit plan
where an 11-credit plan existed. That looks worse in a headline number and is
correct in substance.

It also made the demo harder to construct: when coverage became the primary
key, the previously-tuned phase-2 denylist no longer produced disjoint warm
sets, and `google_local` had to be added to it so the two full-coverage
contributor chains would actually disagree.

## See also

- [Planner architecture](../architecture/planner.md)
- [Marginal replanning](../architecture/marginal-replanning.md)
- [ADR 0001 — marginal cost replanning](0001-marginal-cost-replanning.md)
