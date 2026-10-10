# 0009. Available is not acceptable: freshness gates warmth

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0009. Available is not acceptable: freshness gates warmth** · page 45 of 50

**Status** Accepted

## Context

- **Marginal cost is computed from which steps are already warm.** The obvious definition of warm is "an entry exists in the cache"
- **That definition is wrong**, and wrong in the direction that costs the product its credibility:

```
"What is Nvidia trading at right now"      -> a 6-hour-old entry exists
"Best cafes in Koramangala"                -> a 6-hour-old entry exists
```

- **The same entry age is correct for one and useless for the other**
- Counting both as warm means the planner reports a saving it **did not earn**, and returns a stale price as if it were current

## Decision

**A cached entry counts as warm only if it satisfies the step's inferred freshness bound.**

```
realtime   < 15 minutes
fresh      < 24 hours
recent     < 7 days
stable     no bound
```

- **Freshness is inferred per step from two signals; the stricter wins:**
  - temporal language in the intent: "right now", "recent", "latest", a named month
  - the engine's `volatility_prior` from the catalog
- **An entry that exists but is too old is a miss** for marginal costing, and the step is costed at full price
  - cache inspection records it as such, so the Plan Inspector shows "entry exists, 6h old, requires <15m" instead of silently not counting it
- **Freshness also caps TTL:** an entry written for a `realtime` step cannot get a 7-day TTL from the adaptive controller, whatever the churn observations say

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Count any entry as warm** | Inflates the savings number **and** serves stale data. Both fatal for a system whose claim is that its savings are safe |
| **One global TTL** | Short enough for stock prices makes the cache useless for stable reference data; long enough for reference data serves yesterday's price. The variance across engines and query classes spans orders of magnitude |
| **Let the caller specify freshness** | Available as an override, but cannot be **the** mechanism. A caller asking "what is Nvidia trading at right now" has already said what they need; making them say it twice is a design failure |

## Cost

- **More live calls**, and a savings number lower than it could be made to look
- **Planner complexity:** freshness must be inferred **before** cache inspection
  - that is why `inferring_freshness` is its own pipeline stage, not a detail inside the cache lookup
- **The inference is heuristic** (temporal language plus a per-engine prior), so it is sometimes stricter than necessary
- **The asymmetry decides it:**
  - stricter than necessary costs **a credit**
  - looser than necessary costs **a wrong answer**

## See also

- [Caching architecture](../architecture/caching.md)
- [ADR 0003: deterministic semantic guard](0003-deterministic-semantic-guard.md)
- [ADR 0001: marginal cost replanning](0001-marginal-cost-replanning.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0008: Rank on coverage before price](../adr/0008-coverage-before-price.md) | [Docs index](../README.md) | [ADR 0010: A test key overrides the execution mode,…](../adr/0010-test-key-mode-precedence.md) |
