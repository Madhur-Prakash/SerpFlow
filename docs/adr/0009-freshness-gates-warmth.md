# 0009. Available is not acceptable: freshness gates warmth

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/services/cache/service.py"><img alt="source: cache/service.py" src="https://img.shields.io/badge/source-cache%2Fservice.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0009. Available is not acceptable: freshness gates warmth** · page 52 of 57

**Status** Accepted

## Context

- **[Marginal cost](../architecture/marginal-replanning.md#available-is-not-acceptable) is computed from which steps are already warm.** The obvious definition of warm is "an entry exists in the [cache](../architecture/caching.md)"
- **That definition is wrong**, and wrong in the direction that costs the product its credibility:

```
"What is Nvidia trading at right now"      -> a 6-hour-old entry exists
"Best cafes in Koramangala"                -> a 6-hour-old entry exists
```

- **The same entry age is correct for one and useless for the other**
- Counting both as warm means the planner reports a saving it **did not earn**, and returns a stale price as if it were current

## Decision

**A cached entry counts as warm only if it satisfies the step's [inferred freshness bound](../architecture/planner.md#freshness-inference).**

```
# FRESHNESS_LEVELS, app/integrations/llm/base.py
realtime   < 15 minutes
fresh      < 24 hours
recent     < 7 days
stable     no bound
```

- **Freshness is inferred per step from two signals; the stricter wins:**
  - temporal language in the intent: "right now", "recent", "latest", a named month
  - the engine's [`volatility_prior`](../architecture/catalog.md#volatility-and-pii) from the catalog
- **An entry that exists but is too old is a miss** for marginal costing, and the step is costed at full price
  - [cache inspection](../architecture/caching.md#two-entry-points) records it as such, so the Plan Inspector shows "entry exists, 6h old, requires <15m" instead of silently not counting it
  - the check is `acceptable = age <= max_age` in `CacheService._finish` ([`cache/service.py`](../../backend/app/services/cache/service.py)), applied after a semantic hit has passed the [guard](0003-deterministic-semantic-guard.md)
- **Freshness also caps TTL:** an entry written for a `realtime` step cannot get a 7-day TTL from the [adaptive controller](../architecture/caching.md#adaptive-ttl), whatever the churn observations say (`cap_for_freshness` in [`cache/ttl.py`](../../backend/app/services/cache/ttl.py))

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Count any entry as warm** | Inflates the savings number **and** serves stale data. Both fatal for a system whose claim is that its savings are safe |
| **One global TTL** | Short enough for stock prices makes the cache useless for stable reference data; long enough for reference data serves yesterday's price. The variance across engines and query classes spans orders of magnitude |
| **Let the caller specify freshness** | Available as an override, but cannot be **the** mechanism. A caller asking "what is Nvidia trading at right now" has already said what they need; making them say it twice is a design failure |

## Cost

- **More live calls**, and a savings number lower than it could be made to look
- **Planner complexity:** freshness must be inferred **before** cache inspection
  - that is why [`inferring_freshness`](../api/streaming.md#the-stage-sequence) is its own pipeline stage, not a detail inside the cache lookup
- **The inference is heuristic** (temporal language plus a per-engine prior), so it is sometimes stricter than necessary
- **The asymmetry decides it:**
  - stricter than necessary costs **a credit**
  - looser than necessary costs **a wrong answer**
- **Update (2026-10-11): three signals, a per-engine floor, and empty results**
  - **Freshness is inferred from three signal families, not two:** the query class tightens it too (finance and flights to `realtime`; news, events, hotels, jobs, trends and shopping to `fresh`), alongside temporal language and the prior ([`infer_freshness`](../../backend/app/core/text.py))
  - **Each engine gets its own level**, and the intent-level requirement is a floor its prior may tighten but never relax ([`_infer_freshness_per_engine`](../../backend/app/services/planner/service.py))
  - **A billed empty result is now a cache entry like any other:** SerpApi's "no results" answer is cached and charged ([ADR 0001](0001-marginal-cost-replanning.md), update), so a repeat of that step is warm, and free, only while it is inside the same freshness bound

## See also

- [Marginal-cost replanning: available is not acceptable](../architecture/marginal-replanning.md#available-is-not-acceptable): how acceptability feeds the step cost
- [The planner: freshness inference](../architecture/planner.md#freshness-inference): the levels, the three signal families and the per-engine floor
- [Caching: adaptive TTL](../architecture/caching.md#adaptive-ttl): the controller whose TTLs freshness caps
- [`test_planner_core.py`](../../backend/tests/unit/test_planner_core.py): freshness inference, stricter-wins and prior tightening; `test_security.py` covers `test_ttl_never_outlives_the_freshness_requirement`
- [Threat model: stale or wrong cached data](../security/threat-model.md#stale-or-wrong-cached-data-served-as-live): the threat this decision answers
- [Troubleshooting: nothing is ever warm](../operations/troubleshooting.md#nothing-is-ever-warm): when a strict freshness bound is the reason
- [ADR 0001: marginal cost replanning](0001-marginal-cost-replanning.md): the ranking whose input this decision defines
- [ADR 0003: deterministic semantic guard](0003-deterministic-semantic-guard.md): the other half of a safe hit, checked before freshness

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0008: Rank on coverage before price](../adr/0008-coverage-before-price.md) | [Docs index](../README.md) | [ADR 0010: A test key overrides the execution mode,…](../adr/0010-test-key-mode-precedence.md) |
