# The engine catalog

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="engines: 54" src="https://img.shields.io/badge/engines-54-2F6BFF">
  <img alt="dependency edges: 30" src="https://img.shields.io/badge/dependency%20edges-30-2F6BFF">
  <img alt="substitutes: 69" src="https://img.shields.io/badge/substitutes-69-2F6BFF">
  <img alt="capability tags: 28" src="https://img.shields.io/badge/capability%20tags-28-2F6BFF">
  <img alt="YAML: catalog v1.0.0" src="https://img.shields.io/badge/YAML-catalog%20v1.0.0-CB171E?logo=yaml&logoColor=white">
  <a href="../../backend/app/services/catalog/data/v1"><img alt="source: data/v1" src="https://img.shields.io/badge/source-data%2Fv1-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **The engine catalog** · page 11 of 50

**The catalog is the largest body of domain knowledge in SerpFlow, and everything else depends on it.**

- It lives as versioned YAML under [`backend/app/services/catalog/data/v1/`](../../backend/app/services/catalog/data/v1)
- It is the **source of truth**, not a runtime scrape

```
data/v1/
├── _meta.yaml          version, capability tag glossary, coverage vocabulary
├── google_maps.yaml    the reference demo chain
├── web_search.yaml     the densest substitute group
├── commerce.yaml       retail verticals
└── verticals.yaml      scholar, patents, flights, hotels, apps, local reviews
```

| `v1.0.0` contains | Count |
| --- | ---: |
| Engines | **54** |
| Dependency edges | **30** |
| Substitute edges | **69** |
| Capability tags | **28** |

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

This is the part that is easy to get wrong.

| Relationship | Declared by | Describes | Without it |
| --- | --- | --- | --- |
| **Dependency edges** | `satisfied_by`, `feeds` | how engines **chain** | multi-hop routing collapses to guessing |
| **Capability tags and substitutes** | `capability_tags`, `substitutes` | how engines **compete** | stage D emits one plan per intent, and marginal replanning has nothing to re-rank |

- **Dependency edges make rare engines routable:** `google_maps_contributor_reviews` has effectively zero ecosystem usage, and no model has seen it chained. It becomes routable because the graph can compute the path
- **Remove substitutes and the product thesis is unimplementable**

### Coverage and notes

`coverage` is one of:

| Level | Meaning |
| --- | --- |
| `full` | Returns an equivalent result set for the same capability |
| `partial` | Overlapping but materially different coverage or field shape |
| `narrow` | Usable only inside a restricted geography, vertical or corpus |

- **The `note` is user-facing copy:** it appears verbatim in Plan Inspector rejection reasons
  - so "different coverage" is not a note
  - `EngineSpec` validation **rejects a note shorter than fifteen characters** for exactly this reason
- **Every engine must declare substitutes, or a `single_source_note`** saying why nothing competes with it
  - so the planner can explain the absence instead of staying silent
  - `make catalog-validate` enforces this

### Volatility and PII

- **`volatility_prior`** seeds the adaptive TTL controller, which then learns from observed churn
- **`pii_risk`** drives retention
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

- **`make catalog-build`** does steps 1 and 2, writing to `data/_drafts/`. It never touches a committed file
- **Why steps 3 and 4 need a person:**
  - a scraper can see that `google_maps_reviews` takes a `data_id`
  - only a person decides that `google_maps.local_results[].data_id` is the field that satisfies it
  - that the fan-out is roughly twenty
  - that Yelp is a real substitute for place reviews, but not for contributor history
  - that Yelp's coverage collapses outside US metros
- **Every draft field that needs that judgement is marked `REVIEW_ME`**

```bash
make catalog-build               # refresh drafts
make catalog-build ARGS=--diff   # what the drafts cover that the catalog does not
make catalog-validate            # lint the committed catalog
```

## How it is loaded

[`loader.py`](../../backend/app/services/catalog/loader.py) reads the YAML **once per process**, validates it against the Pydantic schema, and derives both edge sets:

- **Dependency edges come from both directions of the declaration**
  - `produces[...].feeds` and `requires[...].satisfied_by` are two views of the same relationship
  - the union is deduplicated; where one relationship is declared twice, **the wider `fan_out_hint` wins**
  - that matters: `google_maps` yields `data_id` from both `local_results[]` and `place_results`, and only the list-valued one carries the fan-out that drives cost projection
- **Substitute edges come from the declarations, plus an implicit pass**
  - any two engines sharing a capability tag are substitutes, even where nobody declared it
  - coverage is assumed `partial`, with a note saying so
  - that guarantees a competitor set exists
- **The index is also projected into tables** (`catalog_engines`, `catalog_edges`, `catalog_substitutes`) by `make seed`
  - the Catalog Explorer and the retrieval stage query those, instead of re-parsing YAML per request

## Versioning

- **Every Plan stores the `catalog_version` it was planned against.** Benchmark runs record it too
- So routing accuracy is tracked **per version**, and a regression is attributable to a specific catalog change, not to "the planner"
- **To add a version:** create `data/v2/` with its own `_meta.yaml`
  - `load_catalog()` picks the newest directory by default
  - `GET /v1/catalog/versions` lists them all

## The capability vocabulary

- [`vocabulary.py`](../../backend/app/services/catalog/vocabulary.py) maps capability tags to the words people actually use
- Both stage A retrieval and the deterministic selector read it
- **Why it exists: embedding similarity alone retrieves badly here**
  - engine docs are short and use the vendor's vocabulary, not the user's
  - nothing in `google_finance`'s description contains "trading"; nothing in `google_shopping`'s contains "65-inch"
  - before capability affinity, "What is Nvidia trading at right now?" retrieved `home_depot`
- **Measured effect:** benchmark routing accuracy went from **21.7% to 34.2%**

## Catalog Explorer

- The UI renders all of this at `/app/catalog`
- **Dependency edges are solid arrows; substitute edges are dashed lines.** They mean different things and should never look the same

## Related

- [Planner](planner.md): how stages A-D use the catalog
- [ADR 0002: two separate edge sets](../adr/0002-typed-catalog-edges.md)
- [Benchmark](../product/benchmark.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Architecture overview](../architecture/overview.md) | [Docs index](../README.md) | [The planner](../architecture/planner.md) |
