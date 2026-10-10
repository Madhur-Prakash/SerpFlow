# 0002. Two separate edge sets: dependency and substitute

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0002. Two separate edge sets: dependency and substitute** · page 38 of 50

**Status** Accepted

## Context

- **A catalog that is only a list of engines and their parameters** can answer "which engine does this?"
- **It cannot answer either question the planner actually needs:**
  1. How do I reach a capability that no single engine provides?
  2. What else could answer this instead?
- **They are different relations:**
  - the first is **path-finding** over a directed graph
  - the second is **similarity** over a set
- **Conflating them** produces a graph where "A can replace B" and "A feeds B" are the same edge: nonsense in both directions

## Decision

**Two edge sets: authored separately, stored separately, served separately.**

- **Dependency edges** describe how engines **chain**: a `produces` field on one engine satisfies a `requires` parameter on another

```yaml
google_maps_reviews:
  produces:
    - path: reviews[].user.contributor_id
      feeds: google_maps_contributor_reviews.contributor_id
      fan_out_hint: 4
```

- **Substitute edges** describe how engines **compete**, through shared capability tags

```yaml
yelp:
  capability_tags: [place_search, place_reviews]
  substitutes:
    - engine: google_maps
      coverage: narrow
      note: "Yelp exposes reviewer display names but no stable contributor identity."
```

- **`GET /v1/catalog/graph`** returns them as two arrays, `dependency_edges` and `substitute_edges`, not one
- **The Catalog Explorer renders them differently**, because they mean different things
- **Both are mandatory:** 30 dependency edges and 69 substitute edges across 54 engines

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **One generic edge type with a `kind` field** | Every consumer immediately branches on `kind`, so the unification is cosmetic. And the relations carry different attributes: dependency edges have `produces_field`, `satisfies_param`, `fan_out_hint`; substitute edges have `coverage` and a trade-off note |
| **Infer chaining from field-name matching** | `google.q` and `google_scholar_cite.q` are both named `q` and are not the same thing: one is a user query, the other a Scholar result id. Name matching would build a chain that cannot work. The catalog carries an explicit `caller_suppliable` flag for this collision |
| **Infer substitutes from embedding similarity** | Similarity in description space is not substitutability. `home_depot` scored well against "What is Nvidia trading at right now" during development, which is how tag-affinity weighting came to exist |

## Cost

- **The catalog has to be authored, carefully**
  - 54 engines with parameters, produced fields, costs, volatility priors, capability tags and both edge sets is a substantial hand-written artefact
  - it is the single thing **most likely to go stale** as SerpApi changes
- **Mitigations, not solutions:**
  - `make catalog-build` regenerates drafts from the SerpApi documentation, with a `--diff` mode
  - `make catalog-validate` lints the committed file
  - the benchmark is labelled by `catalog_version`, so a routing regression is attributable to a specific catalog change
- **The YAML remains the source of truth**; the database holds a queryable projection

## See also

- [Catalog architecture](../architecture/catalog.md)
- [ADR 0001: marginal cost replanning](0001-marginal-cost-replanning.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0001: Rank candidate plans on marginal cost, n…](../adr/0001-marginal-cost-replanning.md) | [Docs index](../README.md) | [ADR 0003: A deterministic guard independent of the…](../adr/0003-deterministic-semantic-guard.md) |
