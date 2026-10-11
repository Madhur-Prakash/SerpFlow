# The reference demo

<p>
  <a href="../README.md#product"><img alt="docs: Product" src="https://img.shields.io/badge/docs-Product-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="make demo: PROVEN" src="https://img.shields.io/badge/make%20demo-PROVEN-3fcf8e">
  <img alt="naive: 101 to 0 credits" src="https://img.shields.io/badge/naive-101%20to%200%20credits-3fcf8e">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <a href="../../backend/scripts/demo.py"><img alt="source: scripts/demo.py" src="https://img.shields.io/badge/source-scripts%2Fdemo.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 9 min" src="https://img.shields.io/badge/read-9%20min-555555">
</p>

[Docs](../README.md) › [Product](../README.md#product) › **The reference demo** · page 2 of 57

```bash
make seed ARGS=--reset
make demo ARGS=--reset-cache
```

- **Exits 0** if cache-aware [marginal-cost replanning](../architecture/marginal-replanning.md) changed the selected plan, **non-zero** if it did not
- Consumes **zero SerpApi credits**: every phase runs against the [deterministic mock](execution-modes.md#the-four-modes) through a [test API key](../security/api-keys.md#test-keys)
- Script: [`backend/scripts/demo.py`](../../backend/scripts/demo.py). Both targets are listed under [everyday targets](../deployment/local.md#everyday-targets)

## What it is proving

> Cache-aware marginal-cost replanning changed which plan was selected.

- **Not** "a cache hit happened"
- **Not** "the second run was faster"
- The same intent, against the same catalog version, produced a **different execution plan**, because the cache state between the two runs differed
- That is the claim [ADR 0001](../adr/0001-marginal-cost-replanning.md) makes, and the one the [product overview](product-overview.md#the-thesis) calls falsifiable
- **The pass condition is the warm run's own counterfactual:** its cold-cost ranking and its marginal-cost ranking disagreed, and the marginal one executed. The script checks the persisted `marginal_replan_changed_selection` flag on that plan, not a cache hit

## The question

```
find coordinated review rings among Koramangala cafes
```

Answering it properly needs **reviewer identity**, and that is only reachable through a chain:

```
google_maps                        find the cafes
  local_results[].data_id
        |
        v
google_maps_reviews                read each cafe's reviews
  reviews[].user.contributor_id
        |
        v
google_maps_contributor_reviews    read each reviewer's full history
```

- `google_maps_contributor_reviews` has effectively **zero usage** in the SerpApi ecosystem
- The planner reaches it by **walking typed dependency edges** ([the reference demo chain](../architecture/catalog.md#the-reference-demo-chain), [ADR 0002](../adr/0002-typed-catalog-edges.md)), not because a model recalled the chain: [stage D](../architecture/planner.md#stage-d-path-find-and-generate-candidates)
- That is the discovery proof

## The three phases

### Phase 1: cold cache, dry run

- The reference intent is **planned but not executed**, in the **Review Intelligence** project, under a **20-credit budget**
- Planning calls a language model, not SerpApi ([the planner](../architecture/planner.md)), so it costs nothing and, just as important for an honest comparison, **warms nothing**

```
candidates generated  8

  google_local -> google_maps_reviews -> google_maps_contributor_reviews   19 cr   full     (projection 51)
  google_maps  -> google_maps_reviews -> google_maps_contributor_reviews   19 cr   full     (projection 101)
  yelp -> yelp_reviews                                                     11 cr   narrow
  (plus five partial plans, retained as fallbacks)

budget reductions  google_maps_reviews 10 -> 3, google_maps_contributor_reviews 40 -> 15
cold ranking       google_local chain
marginal ranking   identical, because nothing is warm
changed            no
```

- **Both full chains are cut to fit the budget before they are ranked:** fan-out is scaled down proportionally, and each cut carries an impact note ([budget-aware reduction](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking))
- **At 19 credits each, the local-pack chain wins the tie** on selector confidence. Uncapped, it is also the cheaper shape: 51 credits against 101
- **The 11-credit Yelp route does not win.** It is a narrow-coverage substitute:
  - Yelp exposes reviewer display names, but no stable contributor identity
  - cross-venue linkage degrades to name matching
  - coverage is ranked **before** price ([coverage before price](../architecture/marginal-replanning.md#coverage-before-price), [ADR 0008](../adr/0008-coverage-before-price.md))

### Phase 2: a different project warms the Maps chain

- A second project, **Market Watch**, runs the same investigation
- Its policy **pins the Google Maps corpus**: Yelp and the Google local pack are on its [engine denylist](../architecture/executor.md#engine-policy), because neither is comparable across runs
- So this run routes through `google_maps` specifically
- It runs at **full scale**, the 101-credit shape, with no request budget, against the deterministic mock: zero real credits
- The organization has a **[shared cache](../architecture/caching.md#organization-level-sharing)**, which the script turns on for both projects, so the entries are visible to the first project:

```
google_maps                       1 entry
google_maps_reviews              20 entries
google_maps_contributor_reviews  80 entries
```

- This is the realistic part: **the work that makes a later plan cheap is usually work somebody else already did**

### Phase 3: the same intent, warm

```
google_maps chain    naive 101    marginal 0    3 of 3 steps warm
google_local chain   naive  51    marginal 1    entry point still cold
yelp chain           naive  11    marginal 11   narrow coverage, never competitive

cold ranking      google_local -> google_maps_reviews -> google_maps_contributor_reviews
marginal ranking  google_maps  -> google_maps_reviews -> google_maps_contributor_reviews

REPLAN CHANGED SELECTION: YES
```

- **Cold ranking** still prefers the cheaper local-pack entry point: on cold cost it really is cheaper, 51 against 101
- **Marginal ranking** prefers the Maps chain: every step is already satisfiable and within its freshness bound, so it costs **nothing**
- **Nothing is reduced this time:** the same 20-credit budget applies, but both full chains fit it on the margin (0 and 1), so the figures are the uncapped shapes

```
naive 101 credits    marginal 0 credits    actually spent 0    saved 101, all from the exact layer
```

- Same intent. Same catalog. **Different plan**
- The two counters the demo leaves behind: [`serpflow_marginal_replan_changed_selection_total`](../operations/observability.md#the-thesis-metric) went up by one, and the [ledger](../architecture/executor.md#writing-back) recorded 101 credits of `exact` savings for Review Intelligence

## Why contributor histories stay warm

- Contributor histories are append-only and change slowly, so `google_maps_contributor_reviews` carries `volatility_prior: 30d` in the [catalog](../../backend/app/services/catalog/data/v1/google_maps.yaml)
- **The intent has no temporal language**, so each step's requirement follows its engine's prior ([freshness inference](../architecture/planner.md#freshness-inference)):

```
google_maps                       volatility 7d     requirement recent   (7 days)
google_maps_reviews               volatility 7d     requirement recent   (7 days)
google_maps_contributor_reviews   volatility 30d    requirement stable
```

- An entry from earlier the same week meets all three, and the contributor step accepts any of its 80 entries that is still cached
- So the **expensive tail of the chain is the part that stays free**
- That is why this chain's economics invert after it has been run once
- Warm is not enough on its own: an entry that misses its step's bound is available but not acceptable, and costs a live call ([ADR 0009](../adr/0009-freshness-gates-warmth.md), [adaptive TTL](../architecture/caching.md#adaptive-ttl))

## The full-scale figure

**101 credits is a [projection](../architecture/marginal-replanning.md#projections-are-never-executed).** It is displayed, labelled as a projection, and never executed live:

```
google_maps                           20 cafes       1 credit
google_maps_reviews x 20            ~400 reviews    20 credits
google_maps_contributor_reviews x 80 ~80 histories  80 credits
                                                    ───────────
                                                   101 credits
```

- One live run would use **40% of a month** on the SerpApi free tier
- The demo executes against the mock. A live demonstration would set [`SERPFLOW_MODE`](../security/secrets.md#inventory) to `record` once, then `replay`, with the REPLAY badge visible throughout
  - that needs a `live` API key and a [SerpApi credential](../security/byok.md): a `test` key routes to the mock whatever the mode ([who chooses, and precedence](execution-modes.md#who-chooses-and-precedence))
- **The number is computed, not written down:** `fan_out_hint` propagates along the [dependency edges](../architecture/catalog.md#what-an-engine-entry-declares) (20 places, then 4 reviewers per place), and [`test_planner_core.py`](../../backend/tests/unit/test_planner_core.py) asserts it so it cannot drift

## Seeing it in the UI

```bash
make dev        # API on :8000, frontend on :5173
```

Sign in with the owner account `make seed` printed, then:

1. **Search:** run the reference intent and watch the [eleven-stage pipeline](../api/streaming.md#the-stage-sequence)
   - **stages are revealed one at a time, in order:** each is held as running for at least 320 ms (600 ms for `executing`), because planning stages often finish within milliseconds of each other
   - **no simulated progression:** a stage is never shown complete before its real SSE frame arrives, the reveal never runs ahead of the backend, and the timings shown are the real ones ([the pipeline animation](../architecture/frontend.md#the-pipeline-animation), `usePacedRun` in [`useRunStream.ts`](../../frontend/src/hooks/useRunStream.ts))
   - **run `make demo` first:** a signed-in search has no test key, so it runs on [the project's mode](execution-modes.md#who-chooses-and-precedence), `replay` by default. It is served from the cache the demo warmed; on a cold cache it fails with [`REPLAY_CASSETTE_MISS`](../operations/troubleshooting.md#replay_cassette_miss)
2. **Plan Inspector:** the warm run opens with a green panel stating that marginal cost changed the selection
   - the cold winner and the marginal winner side by side, with their costs
   - then every candidate with its rejection reason
3. **Run Inspector:** per step, which cache layer served it, the matched query and similarity for semantic hits, entry age, TTL source, credits and latency ([per-step record](../architecture/executor.md#per-step-record))
4. **Overview:** how many plans in the window had their selection changed by replanning, out of how many, with a link to those runs
   - counted from the persisted `marginal_replan_changed_selection` flag on each Plan ([`app/services/analytics/service.py`](../../backend/app/services/analytics/service.py)), the same fact [`serpflow_marginal_replan_changed_selection_total`](../operations/observability.md#the-thesis-metric) counts per process

## Reproducing from a clean state

```bash
docker compose down -v && make up   # drop the volumes: fresh postgres, redis, kafka
make upgrade
make seed ARGS=--reset              # new demo org, fresh API keys
make demo ARGS=--reset-cache        # invalidate the cache first
```

- **`make down` alone is not a clean state:** it stops the containers but keeps the named volumes, and the data in them ([resetting](../deployment/local.md#resetting))
- **`--reset-cache` matters:** without it, phase 1 may find entries from an earlier run
- Then the comparison is no longer between a cold and a warm cache, and phase 1 reports the chain as already warm ([troubleshooting](../operations/troubleshooting.md#phase-1-says-3-of-3-steps-warm))
  - the script still passes on the warm run's counterfactual, and says the two runs selected the same plan because the cache was already warm

## The same assertion in CI

[`tests/e2e/test_marginal_replanning.py`](../../backend/tests/e2e/test_marginal_replanning.py) runs the same three phases against a throwaway organization, rolled back at the end, and asserts:

```python
assert warm_plan.marginal_replan_changed_selection is True
assert warm_engines != cold_engines
assert warm_plan.marginal_cost < warm_plan.naive_cost
assert warm_plan.warm_steps
assert _replan_counter_total() > before
```

- **Two differences from the script:** run one is executed rather than a dry run, and the warm-up project is created by the test. Run one must also report `MOCK`, spend 0 credits and keep `changed_selection` false
- If marginal replanning stops working, **that test fails**
- It runs in `make test` and `make test-e2e`. **Without a reachable PostgreSQL it is skipped, not failed**: run `make up` first ([integration tests all report skipped](../operations/troubleshooting.md#integration-tests-all-report-skipped))
- The repository ships no hosted CI workflow, so "CI" here means wherever `make test` runs

## Related

- [Marginal-cost replanning](../architecture/marginal-replanning.md#worked-example-the-reference-demo): the mechanism, with these three phases as its worked example
- [The engine catalog](../architecture/catalog.md#the-reference-demo-chain): the dependency edges the chain walks
- [Execution modes](execution-modes.md): why a test key means zero credits, and why `replay` still serves a warm intent
- [Product overview](product-overview.md#the-thesis): the claim being proven
- [ADR 0001](../adr/0001-marginal-cost-replanning.md): the decision the demo exists to prove
- [ADR 0009](../adr/0009-freshness-gates-warmth.md): why a warm entry must also be fresh enough to count
- [Observability](../operations/observability.md#the-thesis-metric): the counter the demo increments
- [Troubleshooting](../operations/troubleshooting.md#the-demo): when `make demo` exits non-zero
- [Architecture overview](../architecture/overview.md): the components the demo exercises

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Product overview](../product/product-overview.md) | [Docs index](../README.md) | [Execution modes](../product/execution-modes.md) |
