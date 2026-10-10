# 0014. Persist every candidate plan, not just the winner

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0014. Persist every candidate plan, not just the winner** · page 50 of 50

**Status** Accepted

## Context

- **The planner generates several candidate plans, ranks them twice, and selects one.** The natural thing to store is the selected plan: it is what executes, and what the caller asked for
- **But the product's claim is about the comparison**
  - "cache-aware replanning changed the selected plan" is a statement about a candidate that **lost**
  - a system that stores only the winner cannot **substantiate** that. It can only assert it
- **The same goes for the everyday operator question** when a result looks wrong: why this engine, and not the obvious one?

## Decision

**Every candidate is persisted**, in a `plan_candidates` row of its own:

```
engines, steps, hops
naive_cost, marginal_cost
warm_step_indices, cache_state
coverage, confidence
naive_rank, marginal_rank
selected
feasible_within_budget
rejection_reason
trade_off_note
```

- **Both ranks are stored**, so the disagreement that is the thesis is a **stored fact**, not a derived claim
- **The plan row records** `selected_candidate_id` and `cold_winner_candidate_id`, alongside `marginal_replan_changed_selection` and a human-readable `replan_explanation`
- **Every loser carries a `rejection_reason`**, written at the moment it lost:

```json
{ "plan": "google_local>google_maps_reviews>google_maps_contributor_reviews",
  "naive_cost": 51, "marginal_cost": 1, "coverage": "full",
  "reason": "Marginal cost 1 against 0 for the selected plan (2 warm steps against 3)." }
```

- **`marginal_replan_changed_selection` is indexed**, so "show me every run where replanning changed the answer" is a cheap query, and a filter on the runs list

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Store the winner only** | Cannot substantiate the central claim, and the Plan Inspector has nothing to show |
| **Log the candidates** | Logs expire, are not queryable by plan id, and are not available to the UI. The comparison is **product data**, not diagnostic output |
| **Recompute the comparison on demand** | Impossible: the comparison depended on the cache state at planning time, which has moved on. The ranking only means something as of the instant it was made |

## Cost

- **More rows:** on the order of 6 to 10 per plan, and more write work on a path already doing cache inspection
- **Three `MissingGreenlet` failures during development**
  - writing the candidates and then reading `plan.candidates` triggers a lazy load after the session has moved on
  - the fix: build the list locally and commit it explicitly

```python
set_committed_value(plan_row, "candidates", candidate_rows)
```

- **Worth it:** `plan_candidates` is what makes the Plan Inspector show **why**, not just **what**
  - it is the difference between a demo that claims a behaviour, and one that can be **audited** for it afterwards

## See also

- [Planner architecture](../architecture/planner.md)
- [Marginal replanning](../architecture/marginal-replanning.md)
- [Database schema](../database/schema.md)
- [ADR 0001: marginal cost replanning](0001-marginal-cost-replanning.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0013: Run uvicorn through an explicit loop fac…](../adr/0013-explicit-event-loop-factory.md) | [Docs index](../README.md) | [Back to the start](../README.md) |
