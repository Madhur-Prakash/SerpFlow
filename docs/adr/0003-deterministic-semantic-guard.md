# 0003. A deterministic guard independent of the cosine score

**Status** Accepted

## Context

The semantic cache layer finds entries whose query embedding is close to the
incoming query. That is what makes a paraphrase of yesterday's question free
instead of full price.

It is also the most dangerous component in the system. Consider:

```
"Nvidia Q3 2024 revenue"
"Nvidia Q4 2024 revenue"
```

These embed very close together. Every content word matches. The only
difference is a single character, and it changes the answer completely.

A threshold cannot separate them. Raising it until these are far enough apart
pushes genuine paraphrases below the line too, and the system stops being a
semantic cache at all.

## Decision

Run a deterministic guard that does not look at the similarity score.

```python
def check(incoming: str, candidate: str) -> GuardResult:
    ...
```

The signature takes two strings and nothing else. There is no `similarity`
parameter, deliberately, and a test asserts the signature so it cannot acquire
one by convenience later.

The guard extracts three token families from both queries and requires **exact
set equality**:

```
numerals     20, 2024, 101, 3
versions     v2, 3.11, Q3
entities     Nvidia, Koramangala, Ichiran
```

Both queries mention a quarter. The sets differ. Rejected — whatever the cosine
says.

Rejections are recorded in `semantic_guard_rejections` with both queries, both
token sets and the reason, and counted as
`serpflow_semantic_guard_rejections_total{engine, reason}`.

## Alternatives rejected

**A higher similarity threshold.** Trades false positives for false negatives
on a single axis that does not separate the cases. The failure is categorical,
not a matter of degree.

**Feed the token mismatch in as a score penalty.** Then a sufficiently high
cosine still wins, which is exactly the failure mode. The guard has to be a
veto, not a term.

**Ask a model to judge equivalence.** Non-deterministic, adds latency to every
semantic lookup, and makes a correctness guarantee depend on a model's mood.

## Cost

False negatives. "Revenue for Nvidia in 2024" and "Nvidia 2024 revenue" pass;
"Nvidia revenue last year" against "Nvidia 2024 revenue" does not, because one
has a numeral the other lacks. Those are paid as live calls.

That trade is correct for this product. A missed saving costs one credit. A
false hit returns wrong data to a caller who believes it is right, and the
system's whole claim is that its savings are safe.

Counter-signal to watch: `serpflow_semantic_guard_rejections_total` going to
**zero** is a warning, not a success. A corpus with real numerals in it should
be rejecting some.

## See also

- [Caching architecture](../architecture/caching.md)
- [ADR 0009 — freshness gates warmth](0009-freshness-gates-warmth.md)
