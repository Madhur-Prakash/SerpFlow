# Routing benchmark

<p>
  <a href="../README.md#product"><img alt="docs: Product" src="https://img.shields.io/badge/docs-Product-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="routing accuracy: 38.3%" src="https://img.shields.io/badge/routing%20accuracy-38.3%25-3fcf8e">
  <img alt="tasks: 120" src="https://img.shields.io/badge/tasks-120-2F6BFF">
  <img alt="Groq: BYOK" src="https://img.shields.io/badge/Groq-BYOK-F55036">
  <a href="../../backend/app/services/benchmark/service.py"><img alt="source: benchmark/service.py" src="https://img.shields.io/badge/source-benchmark%2Fservice.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 11 min" src="https://img.shields.io/badge/read-11%20min-555555">
</p>

[Docs](../README.md) › [Product](../README.md#product) › **Routing benchmark** · page 4 of 57

```bash
make benchmark
```

- **120 hand-authored labelled tasks**, three systems, results committed per [catalog version](../architecture/catalog.md#versioning)
- With [`LLM_PROVIDER`](../security/secrets.md#inventory) set to `groq` the suite makes **real LLM calls**, so it runs on demand and is deliberately **not** part of `make test`. The deterministic adapter makes none
- It measures **routing only**: [stages A to D of the planner](../architecture/planner.md), against the labels. Nothing is executed and the cache is not consulted, so the ranking is the cold one
- Harness: [`app/services/benchmark/service.py`](../../backend/app/services/benchmark/service.py)

## Results

Catalog `v1.0.0`, suite `v1`, deterministic adapter (`LLM_PROVIDER=mock`, model `deterministic-v1`).

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

Raw reports: [`backend/fixtures/benchmark/results/`](../../backend/fixtures/benchmark/results)

- **These reports predate one selector change.** Each file's `generated_at` is 2026-10-01. The regional-engine penalty in the deterministic adapter, described [below](#wrong_engine-58), landed after it, so the committed failure examples still show `naver` winning English intents that resolved to a US locale
- A re-run at HEAD with `--no-write` (not committed) scores **40.0%** for the SerpFlow planner, with `wrong_engine` at 55 and `locale_miss` at 4. **The headline stays 38.3%** until the reports are regenerated and committed, so every figure on this page matches a file you can open

## Read this before quoting the number

> **38.3% is not a good routing accuracy.** It is the honest measurement of the
> deterministic adapter, the one that runs with no API keys at all.

- It is reported as-is: an unqualified claim would be worth less than a qualified one
- **It is not a ceiling**
  - [stage B](../architecture/planner.md#stage-b-select) here is a keyword-and-affinity selector ([`app/integrations/llm/mock.py`](../../backend/app/integrations/llm/mock.py))
  - the Groq adapter replaces it with a model that reads the retrieved shortlist and its documented trade-offs
  - measure that with `LLM_PROVIDER=groq GROQ_API_KEY=... make benchmark`. It is a different system, and should be reported as one. The key is [yours to bring](../security/byok.md)
- **It is a fair comparison:** all three systems ran in the same conditions, on the same tasks, with the same scoring
- **The scoring is strict**
  - a chain must match exactly, or match a declared acceptable alternative
  - the locale parameters must match too
  - the right engine with the wrong `gl` scores **zero** on the task, not half

### Why the baselines score zero on exact match

They are not sabotaged. They are measured doing what they can actually do.

- **Unaided model:** gets the intent and nothing else. No engine list, no dependency edges, no substitutes
  - **unless the Groq adapter is configured, it is not a model at all:** it answers `engine=google` for every task, the dominant community behaviour, which is what the committed `deterministic-v1` report measures
  - its 10.8% engine-level accuracy is the 13 tasks whose answer really is `engine=google`, right by luck
  - that is the position most of the 111-of-185 community projects are in
  - without a catalog it cannot learn that reviewer identity is only reachable through `google_maps_reviews.reviews[].user.contributor_id`
- **Embedding retrieval:** returns the single nearest engine by cosine similarity ([stage A](../architecture/planner.md#stage-a-retrieve) alone)
  - no selector and no path-finding, so it **structurally cannot** produce a two-engine chain
  - every multi-hop task is lost before scoring starts
  - that is why it is included: it isolates how much of SerpFlow's accuracy comes from the **typed graph** ([ADR 0002](../adr/0002-typed-catalog-edges.md)) rather than from retrieval

## Failure analysis

From the committed SerpFlow report. Each failed task gets exactly one mode:

| Mode | Tasks | What it means |
| --- | ---: | --- |
| `wrong_engine` | 58 | Routed to an engine that does not answer the intent |
| `extra_hop` | 8 | Added a hop the intent did not require |
| `missing_hop` | 3 | Stopped short of the chain the answer needed |
| `locale_miss` | 3 | Right engine, wrong locale parameters |
| `no_plan` | 2 | Produced no valid plan at all |

### wrong_engine (58)

- **The dominant mode**, and the one a real model would move most
- The deterministic selector scores [capability vocabulary](../architecture/catalog.md#the-capability-vocabulary) against the intent
- When an intent uses words the vocabulary does not cover, it falls back to whatever retrieval ranked highest
- **Regional engines now stay in their markets.** Naver (`kr`), Baidu (`cn`), Yandex and Yandex Images (`ru`, `by`, `kz`) take a 4-point penalty unless the resolved locale is in-market, the intent names the engine, or the intent is written in the market's script (`REGIONAL_ENGINES` in [`mock.py`](../../backend/app/integrations/llm/mock.py)). The reason is recorded with the selection
  - **why:** Naver's catalog entry mentions "blogs and cafes", which used to win "cafes in Koramangala", a Bangalore neighbourhood, for a Korean search engine
  - **the committed reports predate it:** three of their five recorded `wrong_engine` examples (`bm_003`, `bm_015`, `bm_023`) are `naver`, each for an English intent that resolved to a US locale
  - [`get_llm()`](../../backend/app/integrations/llm/__init__.py) returns this adapter unless `LLM_PROVIDER=groq`

```
bm_015  "Who is Yann LeCun and which of his papers are the most cited?"
        expected google_scholar_profiles, got naver
        -> "who is" indicates both a web search and an author lookup; the
           vocabulary does not disambiguate on "his papers". naver, for a
           US-locale intent, is the regional defect above; at HEAD the
           penalty moves it to yahoo, which is still wrong

bm_029  "Show me the top listing for the Sony WH-1000XM6 and then ..."
        expected google_shopping -> google_product, got walmart
        -> four engines share product_search; nothing in the intent names a
           retailer, and the tie-break is not principled
```

- **A few are judgement calls, not errors:** `bm_022` ("Interior photos of the Ace Hotel in Shoreditch") expects `google_images`
  - the planner routes `google_maps -> google_maps_photos`, which arguably answers it better, and is scored wrong

### locale_miss (3)

The committed report names the three tasks but not what was inferred. Locale inference has not changed since, so re-running them shows it:

```
bm_012  "Cheapest nonstop from Austin to Mexico City next Friday?"
        expected gl=us, inferred gl=mx
bm_077  "Find the patent behind the Dyson bladeless fan and show me the full claim set."
        expected gl=uk, inferred gl=us
bm_117  "Hours and stall listings for Mangwon Market street food."
        expected gl=kr, inferred gl=us
```

- **`bm_012` is a label disagreement:** the planner infers the locale of the **subject**, the destination; the task labels the locale of the **searcher**, in Austin. Both are defensible. Noting it is more useful than special-casing it
- **`bm_077` is arguable:** no place is named, so the planner falls back to `us`; the label reads the locale off the company
- **`bm_117` is a real miss:** Mangwon Market is in Seoul, and the place gazetteer does not know it
- **A locale miss can also be filed as `wrong_engine`.** Failure classification compares against the primary chain only ([`_classify_failure`](../../backend/app/services/benchmark/service.py)), so a task that takes an acceptable alternative with the wrong locale is not a `locale_miss`
  - `bm_003` in the committed report: "Korean buyers" on the Galaxy Z Fold, routed to `naver`, an acceptable alternative, but resolved to `gl=us` against a `kr` label

### no_plan (2)

Both fail at [path-finding](../architecture/planner.md#stage-d-path-find-and-generate-candidates) with "no valid dependency path": a required parameter has no value, from the intent or from an upstream engine.

```
bm_061  "Sydney to Auckland flight options for the long weekend."
        google_flights: departure_id=SYD and arrival_id=AKL bind; outbound_date does not
bm_008  "Walking directions from Shibuya Station to the Nintendo store in Parco, please."
        google_maps_directions: start_addr and end_addr are never bound
```

- **`bm_061`:** `google_flights` requires `departure_id`, `arrival_id` and `outbound_date`, and "the long weekend" does not resolve to a date
  - **the planner refuses rather than fabricating a window:** correct behaviour, scored as a failure
  - the right fix is a date resolver that understands holidays and seasons, not a planner that guesses
- **`bm_008`:** the synthesizer does not split "from X to Y" into an origin and a destination, so the directions engine has neither address
- Through the API, the same refusal is [`NO_VIABLE_PLAN`](../operations/troubleshooting.md#no_viable_plan)

## What improved, and by how much

The benchmark was not run once at the end. It drove three changes:

| Change | Accuracy |
| --- | ---: |
| Baseline | 21.7% |
| Capability-aware retrieval plus a district and landmark gazetteer | 34.2% |
| Selector depth rules, harness mirroring the planner ranking, wider vocabulary | 38.3% |

- **The first was the largest single win**, and exposed a real defect:
  - embedding similarity alone retrieved `home_depot` for "What is Nvidia trading at right now?"
  - engine docs use vendor vocabulary, and nothing in `google_finance`'s description contains "trading"
  - capability-aware retrieval is now part of [stage A](../architecture/planner.md#stage-a-retrieve)
- **The selector changes since are not in this table:** the regional penalty above has no committed report yet

## The task set

- [`backend/fixtures/benchmark/tasks_v1.json`](../../backend/fixtures/benchmark/tasks_v1.json), authored by hand and committed (suite `v1`, 120 tasks). One of them:

```json
{
  "id": "bm_023",
  "intent": "What do Korean reviewers say about the food court at Starfield Hanam?",
  "expected_engines": ["google_maps", "google_maps_reviews"],
  "acceptable_alternatives": [["google_local", "google_maps_reviews"]],
  "expected_params": { "gl": "kr", "hl": "ko" },
  "expected_freshness": "recent",
  "category": "locale",
  "difficulty": "medium",
  "notes": "Locale is the discriminator: hl=ko decides whether review text comes back in the language it was written in."
}
```

- **Distribution:** 40 `single_engine`, 26 `multi_hop`, 20 `locale`, 16 `freshness`, 18 `substitute`
  - 12 tasks end in `google_maps_contributor_reviews`
  - 10 are Korean-locale (`gl=kr`), 7 of them with `naver` as an acceptable alternative to Google
  - 7 are review-source substitution cases: Google Maps reviews against Yelp
- **Every chain follows the real dependency edges**
  - every engine in every expected chain and alternative exists in catalog `v1.0.0`
  - a two-engine chain is an actual edge; a three-engine chain is two chained edges
  - there are no invented relationships in the labels
  - **nothing in the test suite enforces this.** It held when this page was last checked against the catalog; re-check it after a [catalog change](#if-you-change-the-catalog)
- `make seed` loads the tasks into [`benchmark_tasks`](../database/schema.md#benchmark), which is where the Benchmarks page reads the task set from

## Scoring

```
correct   = engines_correct AND params_correct
engines_correct   exact chain match, or an exact match against a declared
                  acceptable alternative
params_correct    every key in expected_params matches, case-insensitively
freshness_correct reported separately, not part of `correct`
```

- Freshness is scored, but **kept out of the headline** so the number stays comparable with a routing-only baseline
- **A match on an acceptable alternative counts as correct**, and is counted separately as `matched_alternative_count` (23 in the committed SerpFlow report)
- **The SerpFlow system is scored on the plan the planner would rank first on a cold cache:** coverage, then cold cost, then selector confidence, the same order the planner uses ([coverage before price](../architecture/marginal-replanning.md#coverage-before-price), [ADR 0008](../adr/0008-coverage-before-price.md))

## Running it

```bash
make benchmark                                                  # all three systems; rewrites the committed reports
serpflow benchmark run --system serpflow --no-write              # one system, nothing written
serpflow benchmark run --system serpflow --limit 20 --no-write   # a subset, while iterating
```

- **The CLI writes by default.** `serpflow benchmark run` saves its report over `backend/fixtures/benchmark/results/<catalog>_<suite>_<system>.json` unless you pass `--no-write`, and the file name does not record `--limit`: a 20-task run replaces the committed 120-task report. `make benchmark` runs `serpflow benchmark compare`, which always writes all three ([CLI: `serpflow benchmark`](../sdks/cli.md#serpflow-benchmark))
- **The CLI runs in-process** and stores nothing in the database
- **From the UI:** the Benchmarks page triggers a run through [`POST /v1/benchmarks/run`](../api/overview.md#governance) (needs `benchmark:run`) and shows accuracy by category, the failure breakdown and the full task set
  - **a UI run is stored, not written:** it lands in [`benchmark_runs` and `routing_evals`](../database/schema.md#benchmark), never in the committed files, and sets the [`serpflow_routing_accuracy`](../operations/observability.md#planner) gauge for that system and catalog version
  - the page lists runs from the database only, so it is empty until a run is triggered through the page or the API
  - **benchmark runs are instance-wide:** the benchmark tables hold no tenant data ([covered tables](../database/rls.md#covered-tables)), so every organization sees the latest 50
- **Storage:** `benchmark_tasks`, `benchmark_runs` and `routing_evals`, exposed at `GET /v1/benchmarks`, `GET /v1/benchmarks/tasks` and `GET /v1/benchmarks/{run_id}/evals`
- **Tracked per `catalog_version`**, so a routing regression is attributable to a specific catalog change

## If you change the catalog

- **Re-run the benchmark**
- A catalog edit that improves one route often degrades another
- Per-version tracking exists so that is visible, not discovered later: bump the [catalog version](../architecture/catalog.md#versioning) and the reports land under a new file name instead of overwriting the old ones
- **Re-check the labels too:** a renamed engine or a removed edge can turn a correct label into an impossible one, and nothing fails to tell you

## Related

- [Product overview](product-overview.md#what-it-does-not-do): where the 38.3% is stated as a boundary, not hidden
- [The planner](../architecture/planner.md): the four stages the harness runs, and the selector the failure analysis is about
- [The engine catalog](../architecture/catalog.md#versioning): why reports are tracked per catalog version
- [Bring your own key](../security/byok.md): the Groq key that swaps in a model-backed selector
- [CLI](../sdks/cli.md#serpflow-benchmark): every `serpflow benchmark` flag, including `--no-write`
- [Database schema](../database/schema.md#benchmark): `benchmark_tasks`, `benchmark_runs` and `routing_evals`
- [ADR 0008](../adr/0008-coverage-before-price.md): coverage before price, the order the harness ranks in
- [ADR 0002](../adr/0002-typed-catalog-edges.md): the typed graph the embedding-only baseline lacks

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Execution modes](../product/execution-modes.md) | [Docs index](../README.md) | [Glossary](../product/glossary.md) |
