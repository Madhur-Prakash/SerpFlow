# 0014. Persist every candidate plan, not just the winner

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/db/models/planning.py"><img alt="source: models/planning.py" src="https://img.shields.io/badge/source-models%2Fplanning.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0014. Persist every candidate plan, not just the winner** · page 57 of 57

**Status** Accepted

## Context

- **The planner generates [several candidate plans](../architecture/planner.md#stage-d-path-find-and-generate-candidates), [ranks them twice](0001-marginal-cost-replanning.md), and selects one.** The natural thing to store is the selected plan: it is what executes, and what the caller asked for
- **But the product's claim is about the comparison**
  - ["cache-aware replanning changed the selected plan"](../architecture/marginal-replanning.md#what-changed_selection-means) is a statement about a candidate that **lost**
  - a system that stores only the winner cannot **substantiate** that. It can only assert it
- **The same goes for the everyday operator question** when a result looks wrong: why this engine, and not the obvious one?

## Decision

**Every candidate is persisted**, in a [`plan_candidates`](../database/schema.md#plan_candidates) row of its own (`PlanCandidate` in [`app/db/models/planning.py`](../../backend/app/db/models/planning.py)):

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
- **The [plan row](../database/schema.md#plans) records** `selected_candidate_id` and `cold_winner_candidate_id`, alongside `marginal_replan_changed_selection` and a human-readable `replan_explanation`
- **Every loser carries a `rejection_reason`**, written at the moment it lost (`_rejection_reason` in [`cost.py`](../../backend/app/services/planner/cost.py)):

```json
{ "plan": "google_local>google_maps_reviews>google_maps_contributor_reviews",
  "naive_cost": 51, "marginal_cost": 1, "coverage": "full",
  "reason": "Marginal cost 1 against 0 for the selected plan (2 warm step(s) against 3)." }
```

- **`marginal_replan_changed_selection` is indexed**, so "show me every run where replanning changed the answer" is a cheap query, and a [filter on the runs list](../api/overview.md#runs) (`changed_selection=true`)

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Store the winner only** | Cannot substantiate the central claim, and the [Plan Inspector](../architecture/frontend.md#routes) has nothing to show |
| **Log the candidates** | Logs expire, are not queryable by plan id, and are not available to the UI. The comparison is **product data**, not diagnostic output |
| **Recompute the comparison on demand** | Impossible: the comparison depended on the cache state at planning time, which has moved on. The ranking only means something as of the instant it was made |

## Cost

- **More rows:** on the order of 6 to 10 per plan, and more write work on a path already doing cache inspection
  - at HEAD the set is capped at `planner_max_candidates` + 3, nine by default, with answering plans kept first ([`candidates.py`](../../backend/app/services/planner/candidates.py))
- **Three [`MissingGreenlet`](../operations/troubleshooting.md#missinggreenlet-greenlet_spawn-has-not-been-called) failures during development**
  - writing the candidates and then reading `plan.candidates` triggers a lazy load after the session has moved on
  - the fix: build the list locally and commit it explicitly ([lazy relationship loading](../architecture/backend.md#lazy-relationship-loading))

```python
set_committed_value(plan_row, "candidates", candidate_rows)
```

- **Worth it:** `plan_candidates` is what makes the Plan Inspector show **why**, not just **what**
  - it is the difference between a demo that claims a behaviour, and one that can be **audited** for it afterwards

## See also

- [The planner: what the Plan stores](../architecture/planner.md#what-the-plan-stores): the plan and candidate fields, and the counterfactual they make possible
- [Marginal-cost replanning: what `changed_selection` means](../architecture/marginal-replanning.md#what-changed_selection-means): the stored disagreement, and what it does not claim
- [Database schema: `plan_candidates`](../database/schema.md#plan_candidates): the table and its `(plan_id, marginal_rank)` index
- [Frontend: routes](../architecture/frontend.md#routes): the Plan Inspector, which reads these rows instead of recomputing
- [`test_marginal_replanning.py`](../../backend/tests/e2e/test_marginal_replanning.py): asserts the cold winner is recorded, at least two candidates exist and every rejected alternative has a reason
- [API overview: runs](../api/overview.md#runs): the `changed_selection` filter the index makes cheap
- [Troubleshooting: `MissingGreenlet`](../operations/troubleshooting.md#missinggreenlet-greenlet_spawn-has-not-been-called): the lazy-load failure this write path ran into
- [ADR 0001: marginal cost replanning](0001-marginal-cost-replanning.md): the comparison these rows substantiate

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0013: Run uvicorn through an explicit loop fac…](../adr/0013-explicit-event-loop-factory.md) | [Docs index](../README.md) | [Back to the start](../README.md) |
