# The engine catalog

<p>
  <a href="../architecture/README.md"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="engines: 54" src="https://img.shields.io/badge/engines-54-2F6BFF">
  <img alt="dependency edges: 30" src="https://img.shields.io/badge/dependency%20edges-30-2F6BFF">
  <img alt="substitutes: 69" src="https://img.shields.io/badge/substitutes-69-2F6BFF">
  <img alt="capability tags: 28" src="https://img.shields.io/badge/capability%20tags-28-2F6BFF">
  <img alt="YAML: catalog v1.0.0" src="https://img.shields.io/badge/YAML-catalog%20v1.0.0-CB171E?logo=yaml&logoColor=white">
  <a href="../../backend/app/services/catalog/data/v1"><img alt="source: data/v1" src="https://img.shields.io/badge/source-data%2Fv1-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../architecture/README.md) › **The engine catalog** · page 15 of 50

**The catalog is the largest body of domain knowledge in SerpFlow, and everything else depends on it.**

- It lives as versioned YAML under [`backend/app/services/catalog/data/v1/`](../../backend/app/services/catalog/data/v1)
- It is the **source of truth**, not a runtime scrape
- Every stage of the [planner](planner.md) reads it: retrieval scores against it, the selector chooses from it, path-finding walks it

```
app/services/catalog/
├── schema.py           Pydantic models: EngineSpec, Substitute, RequiredParam, the two edge types
├── loader.py           reads the YAML once per process, derives both edge sets, lints
├── graph.py            find_paths: typed path-finding and fan-out propagation
├── vocabulary.py       capability tag -> the words people actually use
└── data/v1/
    ├── _meta.yaml                      version, capability tag glossary, coverage and volatility vocabularies
    ├── google_maps.yaml     6 engines  the reference demo chain, plus photos, directions, the local pack
    ├── web_search.yaml     11 engines  the densest substitute group, including the regional engines
    ├── commerce.yaml       10 engines  retail verticals
    └── verticals.yaml      27 engines  local reviews, news, images, video, scholar, patents, jobs,
                                        flights, hotels, events, trends, finance, apps
```

| `v1.0.0` contains | Count |
| --- | ---: |
| Engines | **54** |
| Dependency edges | **30** |
| Substitute edges | **69** |
| Capability tags | **28** |

- **The loader logs these four numbers** on every start (`catalog.loaded`); [`GET /v1/catalog`](../api/overview.md#catalog) returns the engine, edge and substitute counts with the tag glossary
- **69 counts declared substitutes only.** Engines that merely share a tag are added as competitors at lookup time (see [how it is loaded](#how-it-is-loaded)), and are not in the count

## What an engine entry declares

```yaml
- engine: google_maps_reviews
  purpose: Reviews for a specific place.

  # How engines COMPETE
  capability_tags: [place_reviews]
  substitutes:
    - engine: yelp_reviews
      coverage: partial
      note: >
        Sparse coverage outside US metros, and the reviewer identity shape
        differs, so contributor-history chaining is not available downstream.

  # How engines CHAIN
  requires:
    data_id:
      type: string
      satisfied_by:
        - google_maps.local_results[].data_id
        - google_maps.place_results.data_id
    place_id:
      type: string
      alternative_to: data_id          # either one satisfies the obligation
      satisfied_by:
        - google_maps.local_results[].place_id
  optional: [hl, gl, sort_by, next_page_token]
  produces:
    "reviews[].user.contributor_id":
      feeds: [google_maps_contributor_reviews.contributor_id]
      fan_out_hint: 4

  cost: 1
  latency_class: medium
  volatility_prior: 7d
  locale_sensitive: [hl, gl]
  pii_risk: high
  docs_url: https://serpapi.com/google-maps-reviews-api
```

### Both relationship kinds are mandatory

This is the part that is easy to get wrong, and why the two are kept as separate edge sets.

| Relationship | Declared by | Describes | Without it |
| --- | --- | --- | --- |
| **Dependency edges** | `satisfied_by`, `feeds` | how engines **chain** | multi-hop routing collapses to guessing |
| **Capability tags and substitutes** | `capability_tags`, `substitutes` | how engines **compete** | [stage D](planner.md#stage-d-path-find-and-generate-candidates) emits one plan per intent, and [marginal replanning](marginal-replanning.md) has nothing to re-rank |

- **Dependency edges make rare engines routable:** `google_maps_contributor_reviews` has effectively zero ecosystem usage, and no model has seen it chained. It becomes routable because the graph can compute the path
- **Remove substitutes and the product thesis is unimplementable**

### A parameter's name is not its shape

- **The same name can mean different things on different engines**
  - `google.q` is the user's query; `google_scholar_cite.q` is a Scholar `result_id` only an upstream hop can produce
  - `caller_suppliable` on the requirement settles it, and [path-finding](planner.md#stage-d-path-find-and-generate-candidates) honours that instead of trusting the name
- **`google_finance` requires `q`, but its `q` is a security identifier:** the entry describes it as "Ticker with exchange, for example "GOOGL:NASDAQ""
  - the catalog does not reshape anything; the planner adapts the free-text intent to a ticker at binding time ([query adapters](planner.md#query-adapters))
  - before that, a sentence went upstream and SerpApi answered with a [billed, empty search](caching.md#billed-empty-results)

### Coverage and notes

`coverage` is one of:

| Level | Meaning |
| --- | --- |
| `full` | Returns an equivalent result set for the same capability |
| `partial` | Overlapping but materially different coverage or field shape |
| `narrow` | Usable only inside a restricted geography, vertical or corpus |

- **The `note` is user-facing copy:** it appears verbatim in [Plan Inspector](frontend.md#routes) rejection reasons
  - so "different coverage" is not a note
  - the `Substitute` model in [`schema.py`](../../backend/app/services/catalog/schema.py) **rejects a note shorter than fifteen characters** for exactly this reason, so the catalog fails to load
- **Every engine must declare substitutes, or a `single_source_note`** saying why nothing competes with it
  - so the planner can explain the absence instead of staying silent: the note becomes the plan's `single_candidate_reason` ([candidate plurality](planner.md#candidate-plurality-is-a-hard-requirement))
  - `make catalog-validate` enforces this: it runs [`serpflow catalog validate`](../sdks/cli.md#serpflow-catalog), which exits `1` on any lint problem

### Volatility and PII

- **`volatility_prior`** seeds the [adaptive TTL](caching.md#adaptive-ttl) controller, which then learns from observed churn, and feeds [freshness inference](planner.md#freshness-inference)
- **`pii_risk`** drives retention ([executor retention](executor.md#retention))
  - a run inherits the highest risk level any of its steps carries
  - `high` gets a **7-day** window instead of 30
- `google_maps_contributor_reviews` is `pii_risk: high`: one response is **one named person's complete review history** across venues. That is not anonymous infrastructure data

## The reference demo chain

```
google_maps                       1 call     1 credit
  local_results[].data_id
        |
        v
google_maps_reviews              20 calls   20 credits
  reviews[].user.contributor_id
        |
        v
google_maps_contributor_reviews  80 calls   80 credits
                                            ───────────
                                            101 credits
```

- **The 101-credit figure is not hand-written.** It falls out of `fan_out_hint` propagating along the chain:
  - `google_maps -> google_maps_reviews` hints **20**
  - `google_maps_reviews -> google_maps_contributor_reviews` hints **4**
  - `1 + 20 + (20 x 4) = 101`
- [`test_planner_core.py`](../../backend/tests/unit/test_planner_core.py) asserts the number, so it cannot drift
- It is a **projection, never executed live**. The chain, and how cache state turns 101 credits into 0, is [the reference demo](../product/demo.md#the-question)

## How the catalog is authored

Six steps, **two of which cannot be automated**:

```
1. Scrape SerpApi engine documentation
2. Generate draft YAML per engine (schema, params, cost, locale sensitivity)
3. Derive dependency edges: which output fields satisfy which required inputs
4. Derive capability_tags and substitutes by grouping engines by purpose
5. Human review pass - steps 3 and 4 cannot be fully automated
6. Commit as versioned files under app/services/catalog/data/
```

- **`make catalog-build`** does steps 1 and 2 ([`backend/scripts/catalog_build.py`](../../backend/scripts/catalog_build.py)), writing to `data/_drafts/`. It never touches a committed file
- **Why steps 3 and 4 need a person**:
  - a scraper can see that `google_maps_reviews` takes a `data_id`
  - only a person decides that `google_maps.local_results[].data_id` is the field that satisfies it
  - that the fan-out is roughly twenty
  - that Yelp is a real substitute for place reviews, but not for contributor history
  - that Yelp's coverage collapses outside US metros
- **Every draft field that needs that judgement is marked `REVIEW_ME`**

```bash
make catalog-build               # refresh drafts
make catalog-build ARGS=--diff   # drafted engines the catalog lacks, and catalog engines with no draft
make catalog-validate            # lint the committed catalog; exits 1 on any problem
```

- `make help` lists every target; the everyday ones are in [local development](../deployment/local.md#everyday-targets)

## How it is loaded

[`loader.py`](../../backend/app/services/catalog/loader.py) reads the YAML **once per process** (`load_catalog` is memoised), validates it against the Pydantic schema in [`schema.py`](../../backend/app/services/catalog/schema.py), and derives both edge sets. A malformed engine fails the load and names its file and engine:

- **Dependency edges come from both directions of the declaration**
  - `produces[...].feeds` and `requires[...].satisfied_by` are two views of the same relationship
  - the union is deduplicated; where one relationship is declared twice, **the wider `fan_out_hint` wins**
  - that matters: `google_maps` yields `data_id` from both `local_results[]` and `place_results`, and only the list-valued one carries the fan-out that drives cost projection
- **Substitute edges come from the declarations, plus an implicit pass at lookup**
  - `substitutes_for()` treats any two engines sharing a capability tag as substitutes, even where nobody declared it
  - coverage is assumed `partial`, with a note saying so
  - that guarantees a competitor set exists, for [retrieval's expansion](planner.md#stage-a-retrieve) and for stage D's substitute strategy
- **Everything at request time reads the in-memory index:** retrieval, the selector, path-finding and the [catalog API](../api/overview.md#catalog) behind the Catalog Explorer. Nothing re-parses YAML per request
- **The index is also projected into tables** ([`catalog_versions`, `catalog_engines`, `catalog_edges`, `catalog_substitutes`](../database/schema.md#catalog-projection)) by `make seed` ([`app/db/seed.py`](../../backend/app/db/seed.py)), or on startup when [`SEED_ON_STARTUP`](../operations/bootstrap.md#what-happens) is set
  - a queryable, SQL-side copy; no request path reads it at HEAD

## Versioning

- **Every Plan stores the `catalog_version` it was planned against** (a column on [`plans`](../database/schema.md#planning-and-execution)), and so does every run's provenance. Benchmark runs record it too
- So routing accuracy is tracked **per version**, and a regression is attributable to a specific catalog change, not to "the planner". See [if you change the catalog](../product/benchmark.md#if-you-change-the-catalog)
- **To add a version:** create `data/v2/` with its own `_meta.yaml`
  - `load_catalog()` picks the last version directory in name order by default; directories starting with `_` (such as `_drafts`) are skipped
  - [`GET /v1/catalog/versions`](../api/overview.md#catalog) lists them all

## The capability vocabulary

- [`vocabulary.py`](../../backend/app/services/catalog/vocabulary.py) maps capability tags to the words people actually use
- Both [stage A retrieval](planner.md#stage-a-retrieve) and the deterministic selector read it
- **Why it exists: embedding similarity alone retrieves badly here**
  - engine docs are short and use the vendor's vocabulary, not the user's
  - nothing in `google_finance`'s description contains "trading"; nothing in `google_shopping`'s contains "65-inch"
  - before capability affinity, "What is Nvidia trading at right now?" retrieved `home_depot`
- **Measured effect:** benchmark routing accuracy went from **21.7% to 34.2%**, together with a district and landmark gazetteer; it is **38.3%** today. See [what improved, and by how much](../product/benchmark.md#what-improved-and-by-how-much)

## Catalog Explorer

- The UI renders all of this at `/app/catalog` ([routes](frontend.md#routes)), in three tabs: **Explore**, **Dependency graph** and **Substitute groups**
- **Dependency edges are solid arrows; substitute edges are dashed lines, with no arrow.** They mean different things and should never look the same
- The data comes from the [catalog endpoints](../api/overview.md#catalog); a worked request is in [explore the catalog](../api/examples.md#explore-the-catalog)

## Related

- [The planner](planner.md): how stages A to D use the catalog, and how a free-text query becomes a ticker
- [Marginal replanning](marginal-replanning.md) and [ADR 0004](../adr/0004-coverage-before-price.md): why substitutes give the cost model something to re-rank, and why their `coverage` outranks their price
- [Caching](caching.md#adaptive-ttl): how `volatility_prior` seeds each entry's TTL
- [Database schema](../database/schema.md#catalog-projection): the tables `make seed` projects the catalog into
- [Benchmark](../product/benchmark.md#if-you-change-the-catalog): routing accuracy per catalog version, and what to run after an edit
- [The reference demo](../product/demo.md): the contributor chain the dependency edges make routable
- [CLI](../sdks/cli.md#serpflow-catalog): `serpflow catalog validate` and the other catalog commands

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Architecture overview](../architecture/overview.md) | [Docs index](../README.md) · [Architecture index](../architecture/README.md) | [The planner](../architecture/planner.md) |
