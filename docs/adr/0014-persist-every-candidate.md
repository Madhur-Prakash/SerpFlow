# 0014. Persist every candidate plan, not just the winner

**Status** Accepted

## Context

The planner generates several candidate plans, ranks them twice and selects
one. The natural thing to store is the selected plan: it is what executes, and
it is what the caller asked for.

But the product's claim is about the **comparison**. "Cache-aware replanning
changed the selected plan" is a statement about a candidate that lost, and a
system that stores only the winner cannot substantiate it. It can only assert
it.

The same applies to the everyday question an operator asks when a result looks
wrong: why this engine and not the obvious one?

## Decision

Every candidate is persisted, in a `plan_candidates` row of its own.

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

Both ranks are stored, so the disagreement that is the thesis is a stored fact
rather than a derived claim. The plan row records `selected_candidate_id` and
`cold_winner_candidate_id` alongside
`marginal_replan_changed_selection` and a human-readable
`replan_explanation`.

Every loser carries a `rejection_reason` written at the moment it lost:

```json
{ "plan": "google_local>google_maps_reviews>google_maps_contributor_reviews",
  "naive_cost": 51, "marginal_cost": 1, "coverage": "full",
  "reason": "Marginal cost 1 against 0 for the selected plan (2 warm steps against 3)." }
```

`marginal_replan_changed_selection` is indexed, so "show me every run where
replanning changed the answer" is a cheap query and a filter on the runs list.

## Alternatives rejected

**Store the winner only.** Cannot substantiate the central claim, and the Plan
Inspector has nothing to show.

**Log the candidates.** Logs expire, are not queryable by plan id, and are not
available to the UI. The comparison is product data, not diagnostic output.

**Recompute the comparison on demand.** Impossible: the comparison depended on
the cache state at planning time, which has moved on. The ranking is only
meaningful as of the instant it was made.

## Cost

More rows — on the order of 6 to 10 per plan — and more write work on a path
that is already doing cache inspection.

It also produced three `MissingGreenlet` failures during development, because
writing the candidates and then reading `plan.candidates` triggers a lazy load
after the session has moved on. The fix is to build the list locally and commit
it explicitly:

```python
set_committed_value(plan_row, "candidates", candidate_rows)
```

Worth it. `plan_candidates` is what makes the Plan Inspector show *why* rather
than *what*, and it is the difference between a demo that claims a behaviour
and one that can be audited for it afterwards.

## See also

- [Planner architecture](../architecture/planner.md)
- [Marginal replanning](../architecture/marginal-replanning.md)
- [Database schema](../database/schema.md)
- [ADR 0001 — marginal cost replanning](0001-marginal-cost-replanning.md)
