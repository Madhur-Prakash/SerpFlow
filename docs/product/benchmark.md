# Routing benchmark

```bash
make benchmark
```

120 hand-authored labelled tasks, three systems, results committed per catalog
version. The suite makes real LLM calls, so it runs on demand and is
deliberately **not** part of CI.

## Results

Catalog `v1.0.0`, suite `v1`, deterministic adapter (`LLM_PROVIDER=mock`).

| System | Accuracy | Engine chain | Locale params | Freshness |
| --- | ---: | ---: | ---: | ---: |
| Unaided model, no catalog | 0.0% | 10.8% | 4.2% | 0.0% |
| Embedding retrieval only | 0.0% | 11.7% | 4.2% | 0.0% |
| **SerpFlow planner** | **38.3%** | **46.7%** | **79.2%** | **55.0%** |

By category:

| Category | Tasks | Correct | Accuracy |
| --- | ---: | ---: | ---: |
| freshness | 16 | 8 | 50.0% |
| substitute | 18 | 8 | 44.4% |
| multi_hop | 26 | 10 | 38.5% |
| locale | 20 | 7 | 35.0% |
| single_engine | 40 | 13 | 32.5% |

Raw reports: [`backend/fixtures/benchmark/results/`](../../backend/fixtures/benchmark/results).

## Read this before quoting the number

**38.3% is not a good routing accuracy.** It is the honest measurement of the
deterministic adapter, the one that runs with no API keys at all, and it is
reported as-is because an unqualified claim would be worth less than a
qualified one.

Three things it does and does not mean:

- It is **not** a ceiling. Stage B is a keyword-and-affinity selector here. The
  Groq adapter replaces it with a model that reads the retrieved shortlist and
  its documented trade-offs. Run `LLM_PROVIDER=groq GROQ_API_KEY=... make benchmark`
  to measure that configuration; it is a different system and should be
  reported as one.
- It **is** a fair comparison, because all three systems were measured in the
  same conditions on the same tasks with the same scoring.
- The scoring is **strict**. A chain must match exactly, or match a declared
  acceptable alternative, and the locale parameters must match too. A plan that
  routes to the right engine with the wrong `gl` scores zero on the task, not
  half.

### Why the baselines score zero on exact match

They are not sabotaged. They are measured doing what they can actually do.

**Unaided model** receives the intent and nothing else: no engine list, no
dependency edges, no substitutes. Its engine-level accuracy of 10.8% is almost
entirely `engine=google` being right by luck, which is also the condition most
of the 111-of-185 community projects are effectively in. Without a catalog it
has no way to learn that reviewer identity is reachable only through
`google_maps_reviews.reviews[].user.contributor_id`.

**Embedding retrieval** returns the single nearest engine by cosine similarity.
It has no selector and no path-finding, so it structurally cannot produce a
two-engine chain; every multi-hop task is lost before scoring begins. That is
the point of including it: it isolates how much of SerpFlow's accuracy comes
from the typed graph rather than from retrieval.

## Failure analysis

| Mode | Tasks | What it means |
| --- | ---: | --- |
| `wrong_engine` | 58 | Routed to an engine that does not answer the intent |
| `extra_hop` | 8 | Added a hop the intent did not require |
| `missing_hop` | 3 | Stopped short of the chain the answer needed |
| `locale_miss` | 3 | Right engine, wrong locale parameters |
| `no_plan` | 2 | Produced no valid plan at all |

### wrong_engine (58)

The dominant mode and the one that would move most with a real model. The
deterministic selector scores capability vocabulary against the intent, and
when an intent uses words the vocabulary does not cover, it falls back to
whatever retrieval ranked highest. Representative examples:

```
bm_015  "Who is Yann LeCun and which of his papers are the most cited?"
        expected google_scholar_profiles, got naver
        -> "who is" indicates both a web search and an author lookup; the
           vocabulary does not disambiguate on "his papers"

bm_029  "Show me the top listing for the Sony WH-1000XM6 and then ..."
        expected google_shopping -> google_product, got walmart
        -> four engines share product_search; nothing in the intent names a
           retailer, and the tie-break is not principled
```

A handful are genuine judgement calls rather than errors. `bm_022`
("Interior photos of the Ace Hotel in Shoreditch") expects `google_images`; the
planner routes `google_maps -> google_maps_photos`, which arguably answers it
better, and is scored wrong.

### locale_miss (3)

All three are label disagreements rather than inference failures:

```
bm_039  "Breaking coverage of the Taiwan earthquake"
        expected gl=us, inferred gl=tw
```

The planner infers the locale of the **subject**. The task labels the locale of
the **searcher**. Both are defensible; the suite picked one and the planner
picked the other. Noting it is more useful than special-casing it.

### no_plan (2)

```
bm_048  "Hotel availability in Kyoto for cherry blossom season."
```

`google_hotels` requires `check_in_date` and `check_out_date`, and "cherry
blossom season" does not resolve to dates. The planner refuses rather than
fabricating a window. That is correct behaviour scored as a failure, and the
right fix is a date resolver that understands seasons, not a planner that
guesses.

## What improved and by how much

The benchmark was not run once at the end. It drove three changes:

| Change | Accuracy |
| --- | ---: |
| Baseline | 21.7% |
| Capability-aware retrieval plus a district and landmark gazetteer | 34.2% |
| Selector depth rules, harness mirroring the planner ranking, wider vocabulary | 38.3% |

The first was the largest single win and exposed a real defect: embedding
similarity alone retrieved `home_depot` for "What is Nvidia trading at right
now?", because engine documentation uses the vendor vocabulary and nothing in
`google_finance`'s description contains the word "trading".

## The task set

[`backend/fixtures/benchmark/tasks_v1.json`](../../backend/fixtures/benchmark/tasks_v1.json),
authored by hand and committed.

```json
{
  "id": "bm_041",
  "intent": "recent reviews for a ramen shop in Seoul called Ichiran",
  "expected_engines": ["google_maps", "google_maps_reviews"],
  "acceptable_alternatives": [["naver"]],
  "expected_params": { "gl": "kr", "hl": "ko" },
  "expected_freshness": "recent",
  "category": "locale",
  "difficulty": "medium",
  "notes": "locale inference is the discriminator here"
}
```

Distribution: 40 `single_engine`, 26 `multi_hop`, 20 `locale`, 16 `freshness`,
18 `substitute`. Twelve tasks end in `google_maps_contributor_reviews`, ten are
Korean-locale (Naver against Google), and seven are review-source substitution
cases.

Every chain in the file is validated against the real dependency edges: a
two-engine chain must be an actual edge, a three-engine chain must be two
chained edges. There are no invented relationships in the labels.

## Scoring

```
correct   = engines_correct AND params_correct
engines_correct   exact chain match, or an exact match against a declared
                  acceptable alternative
params_correct    every key in expected_params matches, case-insensitively
freshness_correct reported separately, not part of `correct`
```

Freshness is scored but excluded from the headline so the number stays
comparable with a routing-only baseline.

## Running it

```bash
make benchmark                                  # all three systems
serpflow benchmark run --system serpflow        # one system
serpflow benchmark run --system serpflow --limit 20   # a subset, while iterating
```

From the UI, the Benchmarks page triggers a run with the `benchmark:run`
permission and renders accuracy by category, the failure breakdown and the full
task set.

Results are stored in `benchmark_runs` and `routing_evals` and exposed at
`GET /v1/benchmarks`, tracked per `catalog_version` so a routing regression is
attributable to a specific catalog change.

## If you change the catalog

Re-run the benchmark. A catalog edit that improves one route often degrades
another, and the per-version tracking exists so that is visible rather than
discovered later.
