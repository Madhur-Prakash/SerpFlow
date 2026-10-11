# 0001. Rank candidate plans on marginal cost, not cold cost

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/services/planner/cost.py"><img alt="source: planner/cost.py" src="https://img.shields.io/badge/source-planner%2Fcost.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0001. Rank candidate plans on marginal cost, not cold cost** · page 44 of 57

**Status** Accepted

## Context

- **A [planner](../architecture/planner.md#stage-d-path-find-and-generate-candidates) that produces several candidate chains has to rank them.** The obvious key is cost: how many SerpApi credits does this plan consume?
- **That number is wrong the moment a [cache](../architecture/caching.md) exists:**
  - a plan costing 101 credits cold, whose every step is already warm, costs **nothing** to run
  - a plan costing 51 credits cold, and actually cold, costs **51**
- **Conventional systems rank cold, pick a winner, then consult the cache**
  - the cache makes the chosen plan cheaper if it happens to be warm
  - it **never** changes which plan is chosen

## Decision

**Rank on [marginal cost](../architecture/marginal-replanning.md#the-distinction):** the cost of the steps that still need a live call.

- The planner computes **[two rankings](../architecture/marginal-replanning.md#ranking)** for every candidate set, cold and marginal, and records both on the [`plans` row](../database/schema.md#plans), plus whether they disagree:

```
plans.naive_cost
plans.marginal_cost
plans.cold_winner_candidate_id
plans.selected_candidate_id
plans.marginal_replan_changed_selection
plans.replan_explanation
```

- **Both rankings live in [`app/services/planner/cost.py`](../../backend/app/services/planner/cost.py)** (`cold_rank_key`, `marginal_rank_key`), and coverage is the first key of each: see [ADR 0008](0008-coverage-before-price.md)
- **Disagreement is the product:**
  - [`serpflow_marginal_replan_changed_selection_total`](../operations/observability.md#the-thesis-metric) counts it
  - the [e2e suite](../../backend/tests/e2e/test_marginal_replanning.py) asserts that it increments and that the selected chain differs from the cold one
  - [`make demo`](../product/demo.md#what-it-is-proving) exits non-zero if it stops being true
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
  - roughly **120 ms** of planning latency on the reference demo, visible as the [`inspecting_cache` stage](../api/streaming.md#the-stage-sequence) in the stream
  - a real cost, paid on every request, to change the outcome on some of them
  - justified: the thing being bought is credits, which cost money, against latency on a request that was going to make network calls anyway
- **The flip only happens when candidates have disjoint warm engines**
  - two plans sharing their warm steps rank the same either way
  - the [demo](../product/demo.md#the-three-phases) has to be constructed to produce the disagreement: honest, but the headline behaviour is not continuous
  - it fires when cache state is **asymmetric**, not on every request
- **Update (2026-10-11): recorded spend now agrees with marginal cost on empty results**
  - a SerpApi "no results" answer is a billed, successful search ([`SerpApiResponse.is_empty_result`](../../backend/app/integrations/serpapi/client.py)), not an error
  - the [executor](../architecture/executor.md#an-empty-answer-is-still-a-billed-answer) records its credit and caches the response, so a step costed at full price is recorded at full price, and the identical step is warm next time, within its freshness bound ([ADR 0009](0009-freshness-gates-warmth.md))
  - before, the step failed with `UPSTREAM_ERROR`, the ledger recorded 0 credits for a search SerpApi had charged, and nothing was cached
  - enforced by [`test_live_responses.py`](../../backend/tests/unit/test_live_responses.py)

## See also

- [Marginal-cost replanning](../architecture/marginal-replanning.md#ranking): how each step is costed and the two rankings compared
- [The reference demo](../product/demo.md#what-it-is-proving): the scenario built to make the rankings disagree, and the PROVEN check
- [`test_marginal_replanning.py`](../../backend/tests/e2e/test_marginal_replanning.py): the end-to-end assertion that warm cache state changes the selected plan
- [Troubleshooting: `make demo` exits non-zero](../operations/troubleshooting.md#make-demo-exits-non-zero): what to check when the disagreement stops happening
- [ADR 0002: typed catalog edges](0002-typed-catalog-edges.md): without them there is only one candidate and nothing can flip
- [ADR 0008: coverage before price](0008-coverage-before-price.md): the key that sorts ahead of marginal cost in both rankings
- [ADR 0009: freshness gates warmth](0009-freshness-gates-warmth.md): which warm entries are allowed to lower the marginal cost
- [ADR 0014: persist every candidate](0014-persist-every-candidate.md): how the losing plan is kept, so the disagreement can be audited

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Architecture decision records](../adr/README.md) | [Docs index](../README.md) | [ADR 0002: Two separate edge sets: dependency and s…](../adr/0002-typed-catalog-edges.md) |
