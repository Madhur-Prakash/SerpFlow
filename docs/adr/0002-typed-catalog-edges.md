# 0002. Two separate edge sets: dependency and substitute

**Status** Accepted

## Context

An engine catalog that is only a list of engines with their parameters can
answer "which engine does this". It cannot answer either of the two questions
the planner actually needs:

1. How do I reach a capability that no single engine provides?
2. What else could answer this instead?

The first is a path-finding question over a directed graph. The second is a
similarity question over a set. They are different relations, and conflating
them produces a graph where "A can replace B" and "A feeds B" are the same
edge — which is nonsense in both directions.

## Decision

Two edge sets, authored separately, stored separately, served separately.

**Dependency edges** describe how engines chain. A `produces` field on one
engine satisfies a `requires` parameter on another:

```yaml
google_maps_reviews:
  produces:
    - path: reviews[].user.contributor_id
      feeds: google_maps_contributor_reviews.contributor_id
      fan_out_hint: 4
```

**Substitute edges** describe how engines compete, through shared capability
tags:

```yaml
yelp:
  capability_tags: [place_search, place_reviews]
  substitutes:
    - engine: google_maps
      coverage: narrow
      note: "Yelp exposes reviewer display names but no stable contributor identity."
```

`GET /v1/catalog/graph` returns them as two arrays, `dependency_edges` and
`substitute_edges`, rather than one. The Catalog Explorer renders them
differently because they mean different things.

Both are mandatory. 30 dependency edges and 69 substitute edges across 54
engines.

## Alternatives rejected

**One generic edge type with a `kind` field.** Every consumer immediately
branches on `kind`, so the unification is cosmetic, and the two relations have
genuinely different attributes: dependency edges carry `produces_field`,
`satisfies_param` and `fan_out_hint`; substitute edges carry `coverage` and a
trade-off note.

**Infer chaining from field-name matching.** `google.q` and
`google_scholar_cite.q` are both named `q`, and they are not the same thing:
one is a user query, the other is a Scholar result id. Name matching would
produce a chain that cannot work. The catalog carries an explicit
`caller_suppliable` flag for exactly this collision.

**Infer substitutes from embedding similarity.** Similarity in a description
space is not substitutability. `home_depot` scored well against "What is Nvidia
trading at right now" during development, which is how the tag-affinity
weighting came to exist in the first place.

## Cost

The catalog has to be authored, and authored carefully. 54 engines with
parameters, produced fields, costs, volatility priors, capability tags and both
edge sets is a substantial hand-written artefact, and it is the single thing
most likely to go stale as SerpApi changes.

Mitigations, not solutions: `make catalog-build` regenerates drafts from the
SerpApi documentation with a `--diff` mode, `make catalog-validate` lints the
committed file, and the benchmark is labelled by `catalog_version` so a routing
regression is attributable to a specific catalog change.

The YAML remains the source of truth; the database holds a queryable
projection.

## See also

- [Catalog architecture](../architecture/catalog.md)
- [ADR 0001 — marginal cost replanning](0001-marginal-cost-replanning.md)
