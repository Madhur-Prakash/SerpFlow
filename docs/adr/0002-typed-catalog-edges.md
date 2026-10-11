# 0002. Two separate edge sets: dependency and substitute

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/services/catalog/loader.py"><img alt="source: catalog/loader.py" src="https://img.shields.io/badge/source-catalog%2Floader.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0002. Two separate edge sets: dependency and substitute** · page 45 of 57

**Status** Accepted

## Context

- **A [catalog](../architecture/catalog.md) that is only a list of engines and their parameters** can answer "which engine does this?"
- **It cannot answer either question the [planner](../architecture/planner.md) actually needs:**
  1. How do I reach a capability that no single engine provides?
  2. What else could answer this instead?
- **They are different relations:**
  - the first is **[path-finding](../architecture/planner.md#stage-d-path-find-and-generate-candidates)** over a directed graph
  - the second is **similarity** over a set
- **Conflating them** produces a graph where "A can replace B" and "A feeds B" are the same edge: nonsense in both directions

## Decision

**Two edge sets: authored separately, stored separately, served separately.**

- **Dependency edges** describe how engines **chain**: a `produces` field on one engine satisfies a `requires` parameter on another ([what an engine entry declares](../architecture/catalog.md#what-an-engine-entry-declares))

```yaml
# app/services/catalog/data/v1/google_maps.yaml (excerpt)
- engine: google_maps_reviews
  produces:
    "reviews[].user.contributor_id":
      type: string
      feeds:
        - google_maps_contributor_reviews.contributor_id
      fan_out_hint: 4
```

- **Both directions are read:** `produces[].feeds` and `requires[].satisfied_by` are two views of one relationship, and the loader takes their union, deduplicated ([`_derive_edges`](../../backend/app/services/catalog/loader.py))
- **Substitute edges** describe how engines **compete**, through shared [capability tags](../architecture/catalog.md#the-capability-vocabulary)

```yaml
# app/services/catalog/data/v1/google_maps.yaml (excerpt)
- engine: google_maps
  capability_tags: [place_search, local_business]
  substitutes:
    - engine: yelp
      coverage: narrow
      note: >
        Sparse coverage outside US metros. For an Indian neighbourhood like
        Koramangala the result set is a small, biased subset.
```

- **Substitutes are authored per engine, not inferred from tags:** the loader records the tags each pair shares as `shared_tags` ([`_derive_substitutes`](../../backend/app/services/catalog/loader.py)), and 13 of the 69 pairs share none (`google_maps_contributor_reviews` → `yelp_reviews` is one)
- **[`GET /v1/catalog/graph`](../api/overview.md#catalog)** returns them as two arrays, `dependency_edges` and `substitute_edges`, not one
- **The [Catalog Explorer](../architecture/catalog.md#catalog-explorer) renders them differently**, because they mean different things
- **[Both are mandatory](../architecture/catalog.md#both-relationship-kinds-are-mandatory):** 30 dependency edges and 69 substitute edges across 54 engines

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **One generic edge type with a `kind` field** | Every consumer immediately branches on `kind`, so the unification is cosmetic. And the relations carry different attributes: dependency edges have `produces_field`, `satisfies_param`, `fan_out_hint`; substitute edges have `coverage` and a trade-off note |
| **Infer chaining from field-name matching** | `google.q` and `google_scholar_cite.q` are both named `q` and are not the same thing: one is a user query, the other a Scholar result id. Name matching would build a chain that cannot work. The catalog carries an explicit [`caller_suppliable`](../../backend/app/services/catalog/schema.py) flag for this collision |
| **Infer substitutes from embedding similarity** | Similarity in description space is not substitutability. `home_depot` scored well against "What is Nvidia trading at right now" during development, which is how [tag-affinity weighting](../architecture/planner.md#stage-a-retrieve) came to exist |

## Cost

- **The catalog has to be authored, carefully**
  - 54 engines with parameters, produced fields, costs, volatility priors, capability tags and both edge sets is a substantial hand-written artefact
  - it is the single thing **most likely to go stale** as SerpApi changes
- **Mitigations, not solutions:**
  - [`make catalog-build`](../architecture/catalog.md#how-the-catalog-is-authored) regenerates drafts from the SerpApi documentation, with a `--diff` mode
  - `make catalog-validate` lints the committed file
  - the [benchmark](../product/benchmark.md#if-you-change-the-catalog) is labelled by `catalog_version`, so a routing regression is attributable to a specific catalog change
- **The YAML remains the source of truth**; the database holds a [queryable projection](../database/schema.md#catalog-projection)

## See also

- [The engine catalog](../architecture/catalog.md#both-relationship-kinds-are-mandatory): how both edge kinds are declared, loaded and versioned
- [The planner, stage D](../architecture/planner.md#stage-d-path-find-and-generate-candidates): the path-finder that walks dependency edges and emits several candidates
- [API overview: catalog](../api/overview.md#catalog): `GET /v1/catalog/graph` and the paths endpoint that serve the two edge sets
- [`test_planner_core.py`](../../backend/tests/unit/test_planner_core.py): asserts dependency edges are typed and resolvable and every engine has substitutes or says why
- [`test_api.py`](../../backend/tests/integration/test_api.py): `test_catalog_separates_dependency_and_substitute_edges` checks the API keeps them apart
- [Routing benchmark](../product/benchmark.md#if-you-change-the-catalog): what to rerun when the hand-authored catalog changes
- [ADR 0001: marginal cost replanning](0001-marginal-cost-replanning.md): the decision that needs several candidates to choose between
- [ADR 0008: coverage before price](0008-coverage-before-price.md): what a substitute edge's `coverage` value does at ranking time

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0001: Rank candidate plans on marginal cost, n…](../adr/0001-marginal-cost-replanning.md) | [Docs index](../README.md) | [ADR 0003: A deterministic guard independent of the…](../adr/0003-deterministic-semantic-guard.md) |
