# 0001. Rank candidate plans on marginal cost, not cold cost

**Status** Accepted

## Context

A planner that produces several candidate chains has to rank them. The obvious
key is cost: how many SerpApi credits does this plan consume.

But that number is wrong the moment a cache exists. A plan costing 101 credits
cold, whose every step is already warm, costs nothing to run. A plan costing 51
credits cold, entirely cold in fact, costs 51.

Conventional systems rank cold, pick a winner, and then consult the cache. The
cache makes the chosen plan cheaper if it happens to be warm. It never changes
which plan is chosen.

## Decision

Rank on **marginal cost**: the cost of the steps that still need a live call.

The planner computes two rankings for every candidate set — one on cold cost,
one on marginal — and records both, along with whether they disagree:

```
plans.naive_cost
plans.marginal_cost
plans.cold_winner_candidate_id
plans.selected_candidate_id
plans.marginal_replan_changed_selection
plans.replan_explanation
```

Disagreement is the product. `serpflow_marginal_replan_changed_selection_total`
counts it, the e2e suite asserts it is non-zero, and `make demo` exits non-zero
if it stops being true.

A cache hit on the same plan is explicitly **not** sufficient evidence. That is
what every cache already does.

## Alternatives rejected

**Rank cold, then check the cache.** The status quo. Saves money when lucky;
never changes a decision. Cannot produce the behaviour this system exists to
demonstrate.

**Rank on a blended score.** Weighting cold cost and warmth together produces a
number that is neither, and the weights are unjustifiable. Marginal cost is not
a heuristic — it is the actual cost of running the plan now.

**Decide per step at execution time.** Checking the cache as each step runs
saves the same credits but cannot change the chain, because the entry engine is
already committed by the time the second step is considered. Replanning has to
happen before execution to be replanning at all.

## Cost

Cache inspection moves into the planning path. Every step of every candidate is
looked up before anything executes, which adds latency to planning — roughly
120 ms on the reference demo, visible as the `inspecting_cache` stage in the
stream.

That is a real cost, paid on every request, to change the outcome on some of
them. It is justified because the thing being bought is credits, which cost
money, against latency on a request that was going to make network calls
anyway.

A second cost: the flip only happens when candidates have **disjoint** warm
engines. Two plans sharing their warm steps rank the same either way. The
demo has to be constructed to produce the disagreement, which is honest but
means the headline behaviour is not continuous — it fires when the cache state
is asymmetric, not on every request.

## See also

- [Marginal replanning](../architecture/marginal-replanning.md)
- [ADR 0002 — typed catalog edges](0002-typed-catalog-edges.md), without which
  there is only one candidate and nothing can flip
- [ADR 0014 — persist every candidate](0014-persist-every-candidate.md)
