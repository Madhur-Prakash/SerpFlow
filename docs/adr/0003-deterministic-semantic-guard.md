# 0003. A deterministic guard independent of the cosine score

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0003. A deterministic guard independent of the cosine score** · page 39 of 50

**Status** Accepted

## Context

- **The semantic cache layer finds entries whose query embedding is close to the incoming query.** That is what makes a paraphrase of yesterday's question free instead of full price
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
def check(incoming: str, candidate: str) -> GuardResult:
    ...
```

- **The signature takes two strings and nothing else**
  - there is no `similarity` parameter, deliberately
  - a test asserts the signature (`tests/unit/test_cache_guard.py`), so it cannot acquire one by convenience later
- **Three token families are extracted from both queries**, and must match as **exact sets**:

```
numerals     20, 2024, 101, 3
versions     v2, 3.11, Q3
entities     Nvidia, Koramangala, Ichiran
```

- **Both queries mention a quarter. The sets differ. Rejected**, whatever the cosine says
- **Rejections are recorded** in `semantic_guard_rejections` (both queries, both token sets, the reason) and counted as `serpflow_semantic_guard_rejections_total{engine, reason}`

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

## See also

- [Caching architecture](../architecture/caching.md)
- [ADR 0009: freshness gates warmth](0009-freshness-gates-warmth.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0002: Two separate edge sets: dependency and s…](../adr/0002-typed-catalog-edges.md) | [Docs index](../README.md) | [ADR 0004: HMAC-SHA256 for API keys, Argon2id for p…](../adr/0004-hmac-for-api-keys.md) |
