# 0002. A deterministic guard independent of the cosine score

<p>
  <a href="../adr/README.md"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/tests/unit/test_cache_guard.py"><img alt="source: unit/test_cache_guard.py" src="https://img.shields.io/badge/source-unit%2Ftest__cache__guard.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../adr/README.md) › **0002. A deterministic guard independent of the cosine score** · page 53 of 57

**Status** Accepted

## Context

- **The [semantic cache layer](../architecture/caching.md) finds entries whose query embedding is close to the incoming query.** That is what makes a paraphrase of yesterday's question free instead of full price
- **It is also the most dangerous component in the system:**

```
"Nvidia Q3 2024 revenue"
"Nvidia Q4 2024 revenue"
```

- These **embed very close together**: every content word matches
- The only difference is one character, and it **changes the answer completely**
- **A threshold cannot separate them:** raise it until these are far enough apart, and genuine paraphrases fall below the line too. The system stops being a semantic cache at all

## Decision

**Run a deterministic guard that does not look at the similarity score.**

```python
# app/services/cache/guard.py
def check(incoming_query: str, candidate_query: str) -> GuardVerdict:
    ...
```

- **The signature takes two strings and nothing else**
  - there is no `similarity` parameter, deliberately
  - a test asserts the signature ([`tests/unit/test_cache_guard.py`](../../backend/tests/unit/test_cache_guard.py)), so it cannot acquire one by convenience later
- **Three token families are extracted from both queries** ([`guard_tokens`](../../backend/app/core/text.py)), and must match as **exact sets**:

```
numerals     20, 2024, 101, 3
versions     v2, 3.11, Q3
entities     Nvidia, Koramangala, Ichiran
```

- **Checked in that order**, and the first family that differs names the reason: `numeral_mismatch`, `version_mismatch` or `entity_mismatch`
- **Both queries mention a quarter. The sets differ. Rejected**, whatever the cosine says (`Q3` against `Q4`: `version_mismatch`)
- **Rejections are recorded** in [`semantic_guard_rejections`](../database/schema.md#semantic_guard_rejections) (both queries, both token sets, the reason) and counted as [`serpflow_semantic_guard_rejections_total{engine, reason}`](../operations/observability.md#cache)

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **A higher similarity threshold** | Trades false positives for false negatives on one axis that does not separate the cases. The failure is categorical, not a matter of degree |
| **Feed the token mismatch in as a score penalty** | Then a high enough cosine still wins, which is exactly the failure. The guard has to be a **veto**, not a term |
| **Ask a model to judge equivalence** | Non-deterministic, adds latency to every semantic lookup, and makes a correctness guarantee depend on a model's mood |

## Cost

- **False negatives**
  - "Revenue for Nvidia in 2024" and "Nvidia 2024 revenue" pass
  - "Nvidia revenue last year" against "Nvidia 2024 revenue" does not: one has a numeral the other lacks
  - those are paid as live calls
- **That trade is correct for this product**
  - a missed saving costs one credit
  - a false hit returns wrong data to a caller who believes it is right, and the system's whole claim is that its savings are **safe**
- **Counter-signal to watch:** `serpflow_semantic_guard_rejections_total` going to **zero** is a warning, not a success. A corpus with real numerals in it should be rejecting some
- **Update (2026-10-11): how the guard runs at HEAD, and one example that no longer holds**
  - **Tokens are extracted once, at write time,** and stored on the cache entry (`numerals`, `entities`, `versions`); lookups compare against them through `check_against_stored`, which re-extracts from the cached query for rows written before those columns existed ([`guard.py`](../../backend/app/services/cache/guard.py))
  - **Identifier-only requests never reach the guard:** a request addressed by an opaque id such as `data_id` skips the semantic layer ([`is_identifier_lookup`](../../backend/app/services/cache/keys.py), [caching](../architecture/caching.md#identifier-lookups-skip-the-layer-entirely))
  - **The counter counts guard evaluations, not distinct rejections:** it increments on every semantic inspection, the planner's `inspect` for each candidate as well as the executor's `lookup`, while a `semantic_guard_rejections` row is written only on the `lookup` path ([`cache/service.py`](../../backend/app/services/cache/service.py))
  - **The first false-negative example above does not pass as written:** a capitalised, sentence-initial word counts as an entity, so "Revenue for Nvidia in 2024" carries `revenue` and fails `entity_mismatch` against "Nvidia 2024 revenue"; the lowercase "revenue for Nvidia in 2024" passes. Same direction as the trade above: a missed saving, never a false hit

## Related

- [Caching: the entity and numeral guard](../architecture/caching.md#the-entity-and-numeral-guard): the mechanism, its examples, and why it is not a model call
- [Caching: rejections are evidence](../architecture/caching.md#rejections-are-evidence): where rejected near-matches are stored and rendered, for tuning the threshold
- [`test_cache_guard.py`](../../backend/tests/unit/test_cache_guard.py): the signature test, the near-miss table and the stored-token fallback
- [Threat model: stale or wrong cached data](../security/threat-model.md#stale-or-wrong-cached-data-served-as-live): the threat this guard answers
- [Troubleshooting: a semantic hit returned the wrong thing](../operations/troubleshooting.md#a-semantic-hit-returned-the-wrong-thing): reporting a false hit and reading the evidence
- [Observability: cache metrics](../operations/observability.md#cache): the rejection counter, and why zero is a warning

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0001: Rank candidate plans on marginal cost, n…](../adr/0001-marginal-cost-replanning.md) | [Docs index](../README.md) · [Decisions index](../adr/README.md) | [ADR 0003: Envelope encryption for upstream credent…](../adr/0003-envelope-encryption.md) |
