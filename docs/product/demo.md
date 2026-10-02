# The reference demo

```bash
make seed ARGS=--reset
make demo ARGS=--reset-cache
```

Exits 0 if cache-aware marginal-cost replanning changed the selected plan, and
non-zero if it did not. It consumes **zero SerpApi credits**: every phase runs
against the deterministic mock through a test API key.

## What it is proving

> Cache-aware marginal-cost replanning changed which plan was selected.

Not "a cache hit happened". Not "the second run was faster". The same intent,
against the same catalog version, produced a **different execution plan**,
because the cache state between the two runs was different.

## The question

```
find coordinated review rings among Koramangala cafes
```

Answering it properly needs reviewer identity, and reviewer identity is only
reachable through a chain:

```
google_maps                        find the cafes
  local_results[].data_id
        |
        v
google_maps_reviews                read each cafe reviews
  reviews[].user.contributor_id
        |
        v
google_maps_contributor_reviews    read each reviewer full history
```

`google_maps_contributor_reviews` has effectively zero usage in the SerpApi
ecosystem. The planner reaches it by walking typed dependency edges, not
because a model recalled that the chain exists. That is the discovery proof.

## The three phases

### Phase 1: cold cache, dry run

The reference intent is **planned but not executed**. Planning calls a language
model rather than SerpApi, so it costs nothing - and, importantly for an honest
comparison, it warms nothing.

```
candidates generated  9

  google_local -> google_maps_reviews -> google_maps_contributor_reviews    51 cr   full
  google_maps  -> google_maps_reviews -> google_maps_contributor_reviews   101 cr   full
  yelp -> yelp_reviews                                                      11 cr   narrow
  (plus six truncations, retained as budget fallbacks)

cold ranking      google_local chain: same coverage as the Maps chain, cheaper
marginal ranking  identical, because nothing is warm
changed           no
```

Note what did **not** happen: the 11-credit Yelp route did not win. It is a
narrow-coverage substitute - Yelp exposes reviewer display names but no stable
contributor identity, so cross-venue linkage degrades to name matching - and
coverage is ranked before price.

### Phase 2: a different project warms the Maps chain

A second project, Market Watch, runs the same investigation. Its policy pins
the Google Maps corpus: Yelp and the Google local pack are both on its engine
denylist, because neither is comparable across runs. So this run routes through
`google_maps` specifically.

It runs at full scale, the 101-credit shape, against the deterministic mock.
Zero real credits. The organization has a shared cache enabled, so the entries
are visible to the first project:

```
google_maps                       1 entry
google_maps_reviews              20 entries
google_maps_contributor_reviews  80 entries
```

This is the realistic part of the demo: the work that makes a later plan cheap
is usually work somebody else already did.

### Phase 3: the same intent, warm

```
google_maps chain    naive 101    marginal 0    3 of 3 steps warm
google_local chain   naive  51    marginal 1    entry point still cold
yelp chain           naive  11    marginal 11   narrow coverage, never competitive

cold ranking      google_local -> google_maps_reviews -> google_maps_contributor_reviews
marginal ranking  google_maps  -> google_maps_reviews -> google_maps_contributor_reviews

REPLAN CHANGED SELECTION: YES
```

The cold ranking still prefers the cheaper local-pack entry point, because on
cold cost it genuinely is cheaper: 51 against 101. The marginal ranking prefers
the Maps chain, because every one of its steps is already satisfiable and still
within its freshness bound, so it costs **nothing** to run.

```
naive 101 credits    marginal 0 credits    actually spent 0
```

Same intent. Same catalog. Different plan.

## Why contributor histories stay warm

Contributor histories are append-only and change slowly, so
`google_maps_contributor_reviews` carries `volatility_prior: 30d`. The step
freshness requirement for this intent resolves to `recent` (7 days), which a
freshly written entry satisfies comfortably.

That is why the expensive tail of the chain is the part that stays free, and it
is why the economics of this particular chain invert once it has been run once.

## The full-scale figure

101 credits is a **projection**. It is displayed, labelled as a projection, and
never executed live:

```
google_maps                           20 cafes       1 credit
google_maps_reviews x 20            ~400 reviews    20 credits
google_maps_contributor_reviews x 80 ~80 histories  80 credits
                                                    ───────────
                                                   101 credits
```

One live run would consume 40% of a month on the SerpApi free tier. The demo
executes against the mock; a live demonstration would use `SERPFLOW_MODE=record`
once and then replay, with the REPLAY badge visible throughout.

The number itself is computed, not written down: `fan_out_hint` propagates
along the chain, and
[`test_planner_core.py`](../../backend/tests/unit/test_planner_core.py)
asserts it so it cannot drift.

## Seeing it in the UI

```bash
make dev        # API on :8000, frontend on :5173
```

Sign in with the owner account `make seed` printed, then:

1. **Search** - run the reference intent and watch the eleven-stage pipeline.
   Every stage advances on a real SSE frame.
2. **Plan Inspector** - the warm run opens with a green panel stating that
   marginal cost changed the selection, the cold winner and the marginal winner
   side by side with their costs, then every candidate with its rejection
   reason.
3. **Run Inspector** - per step: which cache layer served it, the matched query
   and similarity for semantic hits, the age of the entry, the TTL source, the
   credits, the latency.
4. **Overview** - `serpflow_marginal_replan_changed_selection_total` rendered
   as a count, with a link to the runs where it fired.

## Reproducing from a clean state

```bash
make down && make up          # fresh postgres, redis, kafka
make upgrade
make seed ARGS=--reset        # new demo org, fresh API keys
make demo ARGS=--reset-cache  # invalidate the cache first
```

`--reset-cache` matters: without it, phase 1 may find entries from an earlier
run, and the comparison is no longer between a cold and a warm cache.

## The same assertion in CI

`tests/e2e/test_marginal_replanning.py` performs the same three phases against
a throwaway organization and asserts:

```python
assert warm_plan.marginal_replan_changed_selection is True
assert warm_engines != cold_engines
assert warm_plan.marginal_cost < warm_plan.naive_cost
assert warm_plan.warm_steps
assert _replan_counter_total() > before
```

If marginal replanning stops working, that test fails. It runs in `make test`.
