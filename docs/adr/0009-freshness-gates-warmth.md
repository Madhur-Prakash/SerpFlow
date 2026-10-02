# 0009. Available is not acceptable: freshness gates warmth

**Status** Accepted

## Context

Marginal cost is computed from which steps are already warm. The obvious
definition of warm is "an entry exists in the cache".

That definition is wrong, and it is wrong in the direction that loses the
product its credibility.

```
"What is Nvidia trading at right now"      -> a 6-hour-old entry exists
"Best cafes in Koramangala"                -> a 6-hour-old entry exists
```

The same entry age is correct for one and useless for the other. Counting both
as warm means the planner reports a saving it did not earn and returns a stale
price as if it were current.

## Decision

A cached entry counts as warm **only if** it satisfies the step's inferred
freshness bound.

```
realtime   < 15 minutes
fresh      < 24 hours
recent     < 7 days
stable     no bound
```

Freshness is inferred per step from two signals: temporal language in the
intent ("right now", "recent", "latest", a named month) and the engine's
`volatility_prior` from the catalog. The stricter of the two wins.

An entry that exists but is too old is a **miss** for marginal costing, and the
step is costed at full price. The cache inspection records it as such, so the
Plan Inspector shows "entry exists, 6h old, requires <15m" rather than silently
not counting it.

Freshness also caps TTL: an entry written for a `realtime` step cannot be given
a 7-day TTL by the adaptive controller, whatever the churn observations say.

## Alternatives rejected

**Count any entry as warm.** Inflates the savings number and serves stale data.
Both are fatal for a system whose claim is that its savings are safe.

**One global TTL.** A TTL short enough for stock prices makes the cache useless
for stable reference data; a TTL long enough for reference data serves
yesterday's price. The variance across engines and query classes is several
orders of magnitude.

**Let the caller specify freshness.** Available as an override, but it cannot
be the mechanism. A caller asking "what is Nvidia trading at right now" has
already said what they need, and requiring them to say it twice in a parameter
is a design failure.

## Cost

More live calls, and a savings number that is lower than it could be made to
look.

Also complexity in the planner: freshness has to be inferred before cache
inspection, which is why `inferring_freshness` is its own stage in the pipeline
rather than a detail inside the cache lookup. And the inference is heuristic —
temporal language detection and a per-engine prior — so it will sometimes be
stricter than necessary.

Being stricter than necessary costs a credit. Being looser than necessary costs
a wrong answer.

## See also

- [Caching architecture](../architecture/caching.md)
- [ADR 0003 — deterministic semantic guard](0003-deterministic-semantic-guard.md)
- [ADR 0001 — marginal cost replanning](0001-marginal-cost-replanning.md)
