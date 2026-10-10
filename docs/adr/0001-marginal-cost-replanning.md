# 0001. Rank candidate plans on marginal cost, not cold cost

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0001. Rank candidate plans on marginal cost, not cold cost** · page 37 of 50

**Status** Accepted

## Context

- **A planner that produces several candidate chains has to rank them.** The obvious key is cost: how many SerpApi credits does this plan consume?
- **That number is wrong the moment a cache exists:**
  - a plan costing 101 credits cold, whose every step is already warm, costs **nothing** to run
  - a plan costing 51 credits cold, and actually cold, costs **51**
- **Conventional systems rank cold, pick a winner, then consult the cache**
  - the cache makes the chosen plan cheaper if it happens to be warm
  - it **never** changes which plan is chosen

## Decision

**Rank on marginal cost:** the cost of the steps that still need a live call.

- The planner computes **two rankings** for every candidate set, cold and marginal, and records both, plus whether they disagree:

```
plans.naive_cost
plans.marginal_cost
plans.cold_winner_candidate_id
plans.selected_candidate_id
plans.marginal_replan_changed_selection
plans.replan_explanation
```

- **Disagreement is the product:**
  - `serpflow_marginal_replan_changed_selection_total` counts it
  - the e2e suite asserts it is non-zero
  - `make demo` exits non-zero if it stops being true
- **A cache hit on the same plan is explicitly not sufficient evidence.** That is what every cache already does

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Rank cold, then check the cache** | The status quo. Saves money when lucky; never changes a decision. Cannot produce the behaviour this system exists to demonstrate |
| **Rank on a blended score** | Weighting cold cost and warmth together produces a number that is neither, with unjustifiable weights. Marginal cost is not a heuristic: it is the actual cost of running the plan now |
| **Decide per step at execution time** | Saves the same credits but cannot change the chain: the entry engine is already committed when the second step is considered. Replanning has to happen **before** execution to be replanning at all |

## Cost

- **Cache inspection moves into the planning path**
  - every step of every candidate is looked up before anything executes
  - roughly **120 ms** of planning latency on the reference demo, visible as the `inspecting_cache` stage in the stream
  - a real cost, paid on every request, to change the outcome on some of them
  - justified: the thing being bought is credits, which cost money, against latency on a request that was going to make network calls anyway
- **The flip only happens when candidates have disjoint warm engines**
  - two plans sharing their warm steps rank the same either way
  - the demo has to be constructed to produce the disagreement: honest, but the headline behaviour is not continuous
  - it fires when cache state is **asymmetric**, not on every request

## See also

- [Marginal replanning](../architecture/marginal-replanning.md)
- [ADR 0002: typed catalog edges](0002-typed-catalog-edges.md), without which there is only one candidate and nothing can flip
- [ADR 0014: persist every candidate](0014-persist-every-candidate.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Architecture decision records](../adr/README.md) | [Docs index](../README.md) | [ADR 0002: Two separate edge sets: dependency and s…](../adr/0002-typed-catalog-edges.md) |
