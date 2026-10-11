# The planner

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="stages: 4" src="https://img.shields.io/badge/stages-4-2F6BFF">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="Groq: BYOK" src="https://img.shields.io/badge/Groq-BYOK-F55036">
  <a href="../../backend/app/services/planner/service.py"><img alt="source: planner/service.py" src="https://img.shields.io/badge/source-planner%2Fservice.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 13 min" src="https://img.shields.io/badge/read-13%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **The planner** · page 13 of 57

**Four stages, then costing, then budget.**

- The whole sequence lives in [`app/services/planner/service.py`](../../backend/app/services/planner/service.py), called from `create_plan` in [`app/services/runs.py`](../../backend/app/services/runs.py) for every surface. See [the shape of a request](overview.md#the-shape-of-a-request)
- It emits a **progress event at every transition**: those are the [SSE stages](../api/streaming.md#the-stage-sequence) the [UI pipeline](frontend.md#the-pipeline-animation) animates
- **Planning never calls SerpApi.** It reads cache state and spends nothing, which is why the `analyst` role may call [`POST /v1/plan`](../api/overview.md#plan-without-executing)

```
intent
  |
  A. RETRIEVE      top 8 candidates, expanded by substitution
  |
  B. SELECT        chosen engines, and why each rejected one lost
  |
  C. SYNTHESIZE    dates, locale, entities, parameters, freshness
  |
  D. PATH-FIND     valid chains over typed edges -> N candidate plans
  |
  cost model       cache state per step per candidate -> marginal cost
  |
  re-rank          cold ranking vs marginal ranking
  |
  budget           reduce to fit, record what that cost
  |
  selected plan
```

Each stage's output goes to the stream as it happens, and onto the persisted [`plans` and `plan_candidates` rows](../database/schema.md#planning-and-execution) at the end:

| Stage | SSE stages it emits | Persisted as |
| --- | --- | --- |
| A. retrieve | `analyzing_intent`, `finding_candidates` (running) | `stage_trace[]` |
| B. select | `finding_candidates` (complete: `chosen`, `rejected_count`, `provider`, `model`) | `rejected_engines[]` |
| C. synthesize | `synthesizing_parameters`, `inferring_freshness` | `parameter_bindings`, `freshness_requirements[]`, `steps[].parameters` |
| D. path-find | `finding_paths`, `generating_candidates` | one `plan_candidates` row per candidate |
| cost model | `inspecting_cache`, `calculating_marginal_cost` | `naive_cost`, `marginal_cost`, `warm_steps[]`; `cache_state` per candidate |
| re-rank | `reranking_plans` | `cold_winner_candidate_id`, `marginal_replan_changed_selection`, `replan_explanation` |
| budget | `checking_budget` | `budget_reduction` |

- **The `executing` frames that follow come from the [executor](executor.md)**, not the planner
- Frame payloads: [what `detail` carries](../api/streaming.md#what-detail-carries)

## Which adapter plans

Stages B and C go through an `LLMAdapter`. Which one is resolved **per organization**, by [`resolve_llm`](../../backend/app/services/credentials/llm.py):

```
1. a Groq credential on the project or organization   -> Groq adapter, with that key
2. otherwise get_llm(): LLM_PROVIDER=groq              -> Groq adapter, with GROQ_API_KEY
3. otherwise                                           -> deterministic mock adapter (the default)
```

- **The deterministic adapter is the default**, and it produced the published [benchmark](../product/benchmark.md#results) numbers
  - a real lexical and capability scoring pass over the shortlist, with no network call
  - the same plan for the same intent, every time ([`mock.py`](../../backend/app/integrations/llm/mock.py))
- **The Groq adapter falls back to it, and says so**, when no key is set or a model call fails: the plan records `provider: mock` and a model string such as `deterministic-v1 (groq unavailable)` ([`groq.py`](../../backend/app/integrations/llm/groq.py))
- **Which one answered is persisted:** the `finding_candidates` entry of `stage_trace[]` carries `provider` and `model`, and so does its SSE frame
- Keys, and the self-hosting fallback: [bring your own key](../security/byok.md#the-self-hosting-exception). `GROQ_API_KEY` is in the [secrets inventory](../security/secrets.md#inventory)

## Stage A: retrieve

Code: [`retrieval.py`](../../backend/app/services/planner/retrieval.py)

- **Returns the top 8 out of 54 [catalog](catalog.md) engines** (`PLANNER_RETRIEVAL_TOP_K`), after the project's [engine policy](executor.md#engine-policy) has filtered out denied engines
- It deliberately does **not** pass every engine schema to the selector: that would be slow, expensive, and bury the real candidates
- **Scoring:** `0.72 x capability affinity + 0.28 x embedding similarity`
  - affinity dominates because engine docs use the vendor's vocabulary, not the user's. See [the catalog's note](catalog.md#the-capability-vocabulary)
- **Two expansions then run over the four strongest matches** (`SUBSTITUTE_EXPANSION`), **and both matter:**
  - **substitutes of strong matches** are pulled in even when they score poorly alone. If competitors never enter the set, stage D cannot emit alternative plans, and marginal replanning has nothing to re-rank
  - **upstream producers** of strong matches are pulled in, so a chain's entry point is never missing

## Stage B: select

Code: [`mock.py`](../../backend/app/integrations/llm/mock.py) · [`groq.py`](../../backend/app/integrations/llm/groq.py)

- **Chooses up to three engines**, and records for every engine it did **not** choose a concrete reason about coverage or a trade-off
- Those reasons surface in the [Plan Inspector](frontend.md#routes)
- **The selector may not design chains.** It picks a target capability; stage D decides what is reachable
  - with the Groq adapter this is **enforced, not requested**: any engine the model names that was not retrieved is dropped and recorded as `hallucinated: true`
  - if that leaves no engine, the deterministic choice fills in
- **Generic imperatives are not evidence**
  - "find" and "search" appear in nearly every intent
  - scoring them as web-search signals routes everything to `engine=google`, the exact failure SerpFlow exists to fix
  - so they are excluded from the vocabulary
- **Drill-down engines need an invitation**
  - an engine reachable only through another engine's identifier is penalised, but only when drilling down buys nothing
  - `google_patents_details` declares the same `patent_search` capability as `google_patents`, so "find the patent covering X" wants the search
  - `apple_reviews` declares `app_reviews`, which `apple_app_store` does not, so "what users say about the app" genuinely needs the second hop
- **Regional engines stay in their markets** (deterministic adapter)
  - `REGIONAL_ENGINES` in [`mock.py`](../../backend/app/integrations/llm/mock.py) marks Naver (`kr`), Baidu (`cn`), and Yandex and Yandex Images (`ru`, `by`, `kz`)
  - each loses `REGIONAL_PENALTY = 4.0` unless the resolved locale is in its market, the intent names the engine, or the intent is written in the market's script (Hangul, CJK, Cyrillic)
  - Naver's catalog entry mentions "blogs and cafes", which used to win "cafes in Koramangala", a Bangalore neighbourhood, for a Korean search engine
  - the penalised score is what `rejected_engines[]` records; the penalty's own reason (`naver serves kr; this intent resolves to in`) joins the engine's reason trail, which is shown only if it is chosen anyway
  - the converse rule, `LOCALE_PREFERENCE`, adds 2.5 to Naver, Yandex or Baidu for web search inside its own locale
  - [`test_live_responses.py`](../../backend/tests/unit/test_live_responses.py) asserts both directions: no Naver for Koramangala, Naver for "best cafes in Seoul"
- **The Groq adapter has none of these scoring rules**
  - the model chooses from the shortlist (purpose, capability tags, required parameters, substitutes, cost, latency class) under a system prompt that forbids chains and off-list engines
  - the rules above apply only when it falls back to the deterministic selector

## Stage C: synthesize

Code: [`text.py`](../../backend/app/core/text.py) · [`routes.py`](../../backend/app/core/routes.py)

**Deliberately rule-based:** these are reproducible decisions that must be explainable in the [Run Inspector](frontend.md#routes).

| Concern | Behaviour |
| --- | --- |
| Locale inference | `Seoul -> gl=kr, hl=ko`. Districts are checked before cities, so "omakase in Ginza" resolves to Japan instead of falling back to `us` |
| Location | `extract_location_phrase` takes the place after `in`, `near`, `at` and similar as `location`. Temporal and quantity phrases are [not places](#temporal-phrases-are-not-places) |
| Date normalisation | ISO dates, "tomorrow", "in 3 weeks", "next Friday", "late November" with an approximate-day marker |
| Entity resolution | City names become IATA codes, so `google_flights` is actually routable. Both endpoints must resolve, or nothing is bound |
| Parameter binding | The free-text query maps onto whatever each engine calls it: `q`, `query`, `text`, `term`, `find_desc`. Engines whose query slot is an identifier get it reshaped: see [query adapters](#query-adapters) |
| Freshness inference | See below |

- **With the Groq adapter, locale and dates stay deterministic**
  - a model that disagrees about `gl` silently changes the result set: not worth gambling on
  - the model may propose `location` and other whitelisted keys; the rule-based `location` is used only when it does not
- **The model may tighten a freshness level, never relax one**

### Temporal phrases are not places

- **A preposition does not make a place.** "trading at right now", "at least three", "in the morning" all follow a preposition
  - before the fix these came back as `location=right` and `location=least`, and were sent upstream as if they were cities
- **Phrases led by a non-place word are skipped:** `_NON_PLACE_LEADS` in [`text.py`](../../backend/app/core/text.py) lists them ("right now", "the moment", "least", "a week", "real time"...)
- **The place is cut at the next clause:** `_PHRASE_BREAKS` end it. The list is fixed: prepositions (`at`, `in`, `on`, `for`, `with`, `from`, `to`, `by`, `during`, `before`, `after`, `until`, `since`) and time words (`right`, `now`, `today`, `tonight`, `tomorrow`, `yesterday`, `this`, `next`, `last`, `currently`)

```
what is nvidia trading at right now          ->  no location
at least three ramen shops in Kyoto          ->  Kyoto
hotels near Shibuya at the moment            ->  Shibuya
cafes in Koramangala                         ->  Koramangala
```

- [`test_live_responses.py`](../../backend/tests/unit/test_live_responses.py) asserts each case
- **Any other word continues the phrase**, up to four words after the preposition, so the fix is narrower than "places only":

```
a ramen shop in Seoul called Ichiran         ->  Seoul called Ichiran
cafes near Shibuya station tonight           ->  Shibuya station
flights to Tokyo next week                   ->  no location ("to" does not open a phrase)
```

- **`location` matters twice:** it is sent upstream to engines that accept it, and for those it is a [cache partition column](caching.md#partitioning), so a noisy value also splits the cache. Locale (`gl`, `hl`) is inferred separately and is unaffected

### Query adapters

**Google Finance gets a ticker, not a sentence.**

- **`google_finance` requires `q`, but its `q` is a security identifier** (`GOOGL:NASDAQ`), as its [catalog entry](catalog.md#what-an-engine-entry-declares) says
  - sending the intent made SerpApi answer "Google Finance hasn't returned any results for this query": a [billed, empty search](caching.md#billed-empty-results)
- **`adapt_query` looks the engine up in `QUERY_ADAPTERS`** ([`text.py`](../../backend/app/core/text.py)); `google_finance` maps to `finance_query`, and every other engine's value passes through untouched
- **Applied during parameter binding**, in `PlannerService._bind_step_parameters`, to root-bound string parameters only: chained placeholders are filled by the [executor](executor.md#fan-out-and-binding) later
- **`finance_query` resolves in order:**

```
1. an explicit symbol in the intent wins        "quote for NVDA:NASDAQ"     -> NVDA:NASDAQ
                                                "price of BTC-USD right now" -> BTC-USD
2. a known company, index or crypto name        "apple share price today"   -> AAPL:NASDAQ
   (FINANCE_SYMBOLS, longest name first)        "how is the s&p 500 doing"  -> .INX:INDEXSP
3. otherwise the intent minus filler words      "tata steel share price"    -> tata steel
```

- "what is nvidia trading at right now" is sent as `q=NVDA:NASDAQ`
- **The adapted value is what `steps[].parameters` carries**, so the plan records what will actually be sent; `parameter_bindings` keeps the synthesised free text
- [`test_live_responses.py`](../../backend/tests/unit/test_live_responses.py) asserts each resolution, and that other engines are left alone

### Freshness inference

```
realtime  < 15m    live prices, fares, breaking news
fresh     < 24h    today, latest, current, hotel and job listings
recent    < 7d     recent reviews, local listings
stable    any TTL  patents, papers, reference lookups
```

- **Three signal families:** temporal language in the intent, the engine's `volatility_prior`, and the query class
- **Each step gets its own level:** one intent can touch a 15-minute-prior engine and a 30-day-prior one, and needs the right bar for each
  - the intent-level requirement is a floor that an engine's prior may tighten, never relax: "latest reviews" stays `fresh` on a 30-day-prior engine
- **This is not decoration.** The cost model uses it to decide whether a warm entry is **acceptable**, not merely **available**. See [available is not acceptable](marginal-replanning.md#available-is-not-acceptable) and [ADR 0009](../adr/0009-freshness-gates-warmth.md)
  - without it, marginal cost is computed against an undefined bar, and stale data gets served for time-sensitive intents

## Stage D: path-find and generate candidates

Code: [`graph.py`](../../backend/app/services/catalog/graph.py) · [`candidates.py`](../../backend/app/services/planner/candidates.py)

- **`find_paths` walks typed [dependency edges](catalog.md#both-relationship-kinds-are-mandatory) backwards** from a target, until every required parameter is either caller-supplied or produced upstream, at most `PLANNER_MAX_HOPS` (4) deep
- **A parameter that cannot be sourced invalidates the path**, and it is discarded: the planner never guesses a value it cannot produce
  - if no path survives, planning fails with `NO_VIABLE_PLAN`, naming the parameters the intent did supply. See [errors](../api/overview.md#errors) and [the fix](../operations/troubleshooting.md#no_viable_plan)
- **Watch for parameter-name collisions** (this caused a real bug):
  - `google.q` is the user's query, which the caller always has
  - `google_scholar_cite.q` is a Scholar `result_id` that only an upstream hop can produce
  - both are called `q`. The catalog settles it with `caller_suppliable`, and the graph honours that instead of trusting the name
- **Fan-out propagates along the chain**, which is where the [101-credit projection](catalog.md#the-reference-demo-chain) comes from
- **Engine policy is enforced again here:** a substitute or upstream producer can pull a denied engine back into a chain, so the whole path is rejected

### Candidate plurality is a hard requirement

- **One candidate leaves [marginal replanning](marginal-replanning.md) nothing to re-rank**, so stage D always tries to emit competitors
- **The set is bounded:** up to `PLANNER_MAX_CANDIDATES` (6) answering plans are kept first, then the rest fill to at most nine in all. The [reference demo](../product/demo.md#phase-1-cold-cache-dry-run) emits eight: three answers and five truncations

Three generation strategies:

| Strategy | Source | Role |
| --- | --- | --- |
| `primary` | The chosen engines' own valid chains, differing in entry point or hop count | answer |
| `substitute` | A competing engine serving the same capability | answer |
| `shallow` | Truncations of a longer chain | fallback |

Two rules decide what competes:

- **Role assignment**
  - stage B ranks its choices; the top choice defines the capability the intent asks for
  - a plan ending anywhere else answers a different question, and becomes a **fallback**
  - without this, a one-credit place lookup outranks a review-ring investigation on price, and the planner optimises a question nobody asked. The same reasoning ranks [coverage before price](marginal-replanning.md#coverage-before-price) ([ADR 0008](../adr/0008-coverage-before-price.md))
- **Truncation demotion**
  - a plan whose engine list is a strict prefix of another's is a truncation, not a peer: it is cheaper **because it does less**
  - fallbacks stay in the set, persisted and visible in the Plan Inspector, but only win when nothing else fits a budget

**If exactly one answering plan exists**, the Plan records `single_candidate_reason`, naming one of:

- the engine's `single_source_note`
- that no catalog engine shares its capability tag
- that its substitutes exist but are unreachable from this intent's parameters

## What the Plan stores

Everything the [Plan Inspector](frontend.md#routes) needs, so **nothing is recomputed in the browser**. One [`plans`](../database/schema.md#planning-and-execution) row:

```
intent, steps, parameter_bindings
naive_cost, marginal_cost, projected_full_scale_cost
warm_steps[]                      which steps are free, and why
freshness_requirements[]          per step, with the signals that set it
budget_reduction                  what was cut and what that costs you
confidence, catalog_version
candidate_count, single_candidate_reason
rejected_alternatives[]           every loser, with its reason
rejected_engines[]                stage B's rejections
selected_candidate_id             the plan_candidates row that executes
cold_winner_candidate_id          what cold ranking would have chosen
marginal_replan_changed_selection the thesis, as a boolean
replan_explanation                the thesis, in a sentence
budget_limit, planner_latency_ms, mode
stage_trace[]                     every stage transition with timings
```

- `plan_candidates` persists **every** candidate, not just the winner, with its costs, ranks, per-step cache state and rejection reason. See [ADR 0014](../adr/0014-persist-every-candidate.md)
- **`steps[].parameters` are the concrete values each step will send**, after [query adaptation](#query-adapters); chained values stay as `$from_step` placeholders until the executor resolves them

## Observability

- **Spans:** `serpflow.plan` wrapping `serpflow.catalog.retrieve`, `serpflow.plan.select`, `serpflow.plan.synthesize`, `serpflow.plan.pathfind`, `serpflow.plan.candidates`, `serpflow.plan.marginal_cost`. See [tracing](../operations/observability.md#tracing)
- **Metrics** ([planner metrics](../operations/observability.md#planner)): `serpflow_plan_latency_seconds` by stage (`retrieve`, `select`, `synthesize`, `pathfind`, `marginal_cost`, `total`), `serpflow_plan_candidates_count`, `serpflow_plan_confidence`
- **And [the thesis metric](../operations/observability.md#the-thesis-metric)**, `serpflow_marginal_replan_changed_selection_total`, incremented by the cost model when the two rankings disagree

## Related

- [Marginal replanning](marginal-replanning.md): the cost model and ranking the candidates feed
- [The engine catalog](catalog.md) and [ADR 0002](../adr/0002-typed-catalog-edges.md): the typed edges stage D walks, the vocabulary stage A scores, and why chaining and competing are separate edge sets
- [Caching](caching.md#two-entry-points): what `inspect()` is actually looking at
- [Streaming](../api/streaming.md#the-stage-sequence): the frames each stage emits
- [Database schema](../database/schema.md#planning-and-execution): the `plans` and `plan_candidates` rows
- [Benchmark](../product/benchmark.md#failure-analysis): how well this routes, honestly, and where it misroutes
- [ADR 0008](../adr/0008-coverage-before-price.md) and [ADR 0014](../adr/0014-persist-every-candidate.md): coverage before price, and why every candidate is kept
- [Troubleshooting `NO_VIABLE_PLAN`](../operations/troubleshooting.md#no_viable_plan): when no path survives stage D

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The engine catalog](../architecture/catalog.md) | [Docs index](../README.md) | [Marginal-cost replanning](../architecture/marginal-replanning.md) |
