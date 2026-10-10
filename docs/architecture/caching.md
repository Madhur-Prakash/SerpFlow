# Caching

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="layers: 4" src="https://img.shields.io/badge/layers-4-2F6BFF">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <a href="../../backend/app/services/cache"><img alt="source: services/cache" src="https://img.shields.io/badge/source-services%2Fcache-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **Caching** · page 14 of 50

**Four layers, in order. Only the last one spends.**

```
EXACT      Redis                  hot, TTL-based, fast, NOT the source of truth
SEMANTIC   PostgreSQL + pgvector  partition-filtered, guard-protected
ARCHIVE    SerpApi Searches       re-reads consume no credit
LIVE       SerpApi                the only layer that costs money
```

- The exact layer is backed by a **durable index in PostgreSQL**: a Redis miss falls through to it, not straight to a live call
- Code: [`app/services/cache/`](../../backend/app/services/cache)

## Two entry points

```python
cache.inspect(engine, params, freshness=...)   # planner: would this be free?
cache.lookup(engine, params, freshness=...)    # executor: give me the payload
```

| Method | Called by | Side effects |
| --- | --- | --- |
| `inspect` | the planner, for **every step of every candidate** during ranking | none: read-only |
| `lookup` | the executor, about to run a step | records guard rejections, increments hit counters, repopulates Redis |

- `inspect` is what makes marginal cost **a real number**, not something observed after the fact

## Normalisation

Before anything is hashed:

```
whitespace collapsed       "  Cafes  IN   Koramangala " -> "cafes in koramangala"
casing folded
accents stripped
parameters stably ordered
non-semantic parameters removed:  api_key, output, no_cache, async, zero_trace
```

- **Stripping non-semantic parameters is what makes the exact layer hit at all:** they never change the result, so they must never change the key
- `tests/unit/test_cache_guard.py` asserts each rule

## Partitioning

```
project-level (default)    partition_key = "project:<id>"
organization-level         partition_key = "org:<id>"
```

- **The partition columns are first-class:** `partition_key`, `engine`, `gl`, `hl`, `location`, with a composite index
- **The semantic query filters on them before any vector distance is computed:**

```sql
SELECT id, 1 - (embedding <=> :vec) AS similarity
FROM cache_entries
WHERE partition_key = :partition
  AND engine = :engine AND gl = :gl AND hl = :hl AND location = :location
  AND invalidated_at IS NULL AND expires_at > now()
  AND embedding IS NOT NULL
ORDER BY embedding <=> :vec
LIMIT 5
```

- A full vector scan **then** filtering would be slower, **and** cross the project isolation boundary while doing it
- The **HNSW index** (`m=16, ef_construction=64`, cosine ops) orders within the already-narrowed rows

### Organization-level sharing

- **Opt-in, per project**
- **It crosses a billing and a data boundary:** results fetched for one project become readable by another
  - so the UI says exactly that at the point of enabling it
- **The ledger keeps the two sides apart:**

```
SPEND     attributed to the project that fetched
SAVINGS   attributed to the project that benefited
```

- `/v1/analytics/cross-project` reports the flows between them

## The entity and numeral guard

**This is the part that stops the semantic layer being a liability.**

```
1. Extract from BOTH the incoming query and the candidate cached query:
     - all numerals and numeric tokens      16, 17, 2024, 4K
     - all named entities                   products, brands, places, people
     - all model and version identifiers    v3, M2, 14.5, s24
2. Require EXACT SET EQUALITY of all three.
3. Any difference rejects the hit, regardless of cosine score.
```

So:

```
iphone 16                     never matches   iphone 17
restaurants in Koramangala    never matches   restaurants in Indiranagar
galaxy s24 ultra              never matches   galaxy s25 ultra
python 3.12 release notes     never matches   python 3.13 release notes
```

- **The guard takes two query strings and nothing else**
- There is no code path by which a high similarity score could override it
- **A test asserts its signature contains no `similarity` parameter**

### Why it is not a model call

- A model judging equivalence is right **most of the time**
- "Most of the time" means serving Indiranagar restaurants to someone who asked about Koramangala, once every few dozen queries
  - a silent correctness failure that a high hit rate makes look like a win, and nobody reports as a bug
- **Deterministic extraction is** auditable, reproducible, free, and has no failure mode that depends on prompt phrasing
- More: [ADR 0003](../adr/0003-deterministic-semantic-guard.md)

### Rejections are evidence

- **Every rejected near-match is written to `semantic_guard_rejections`**, with both queries, both token sets, the similarity score and the reason
- The Cache dashboard renders them
- That is how the threshold gets tuned **with evidence**, not intuition
- `serpflow_semantic_guard_rejections_total` counts them by reason

### Identifier lookups skip the layer entirely

- `google_maps_reviews?data_id=0x...` has no meaningful semantic neighbourhood: a "similar" `data_id` is **a different place**
- A semantic hit there would be a correctness bug, not a saving
- So requests addressed purely by an opaque identifier **never consult the layer**

### Threshold, and what the local embedder means for it

- **Default similarity threshold: `0.95`**, configurable per project
- **The default embedder is local and deterministic** (feature hashing): no network, no key, identical across processes and CI
- **It is deliberately conservative:**
  - true paraphrases ("cafes in Koramangala" / "Koramangala cafes") score **1.0**
  - an entity swap in a long query lands in the high 0.8s to low 0.9s, not the 0.98 a dense sentence model would report
- So in the default setup **the threshold filters most near-misses on its own**
- **The guard keeps that true** when the embedder is swapped for a denser one, because it never consults the score

## The Redis boundary

```
Redis                      hot cache, TTL-based, fast lookup, NOT the truth
PostgreSQL cache_entries   durable index, vector storage, semantic lookup
Object storage             large response payloads, content addressed
```

On a Redis restart:

```
Redis hot cache     rebuilt lazily as requests arrive
Postgres durable    survives
Object payloads     survive
```

- **No durable state is destroyed and no credits are lost**, which is why the hot layer can evict aggressively (`allkeys-lru`, 512 MiB)
- **A Redis miss is not a cache miss:** the lookup falls through to the durable index, and repopulates Redis on the way back

## Object storage

- **Large SERP payloads do not belong in PostgreSQL.** They go to S3-compatible storage; PostgreSQL holds only `payload_ref`
  - MinIO locally, or the **filesystem by default**, so `make dev` needs nothing extra
- **Keys are the SHA-256 of the gzipped body**, so two identical responses (common once engines are cached and replayed) deduplicate to one object

## The Searches Archive

- **Re-reading an archived SerpApi search consumes no credit**, so the executor checks `archive_refs` before paying for a live call
- `search_id`, `engine` and `created_at` are recorded whenever a live call succeeds
- **`get_archived` and `search` are separate client methods**, so no code path can accidentally bill for a re-read

## Adaptive TTL

Starts from the engine's `volatility_prior`, then moves on each refresh:

```
top-10 unchanged      TTL x 1.5
significant churn     TTL x 0.5      (3 or more of the top 10 moved)
minor churn           TTL held
```

- **Clamped between 5 minutes and 90 days**
- **Learned per query class, not only per engine**
  - `google` has a 24-hour prior, but `google?q=current gold price` behaves nothing like `google?q=history of the roman empire`
  - a per-engine-only controller averages them, and is wrong for both
- **A TTL may never outlive the step's freshness requirement**
  - a 30-day entry serving a `realtime` step would stay available long after it stopped being acceptable
  - `cap_for_freshness` shortens it at write time, and records `ttl_source: freshness_capped`
- **Every adjustment is written to `ttl_observations`** with the churn ratio and measured interval: the volatility view in Analytics renders it

## Invalidation

| Trigger | How |
| --- | --- |
| **Manual** | from the Cache dashboard, or `POST /v1/cache/invalidate`, by engine or by entry |
| **False-hit report** | an operator reports a bad semantic hit from the Run Inspector; also increments `serpflow_semantic_false_hit_reports_total` |
| **Retention** | 30 days standard, 7 days for high-PII-risk runs |

- Invalidation sets `invalidated_at` on the durable row, and **deletes the matching Redis keys by pattern**

## Metrics

```
serpflow_cache_hits_total{layer, project_id}
serpflow_cache_lookup_seconds{layer}
serpflow_credits_saved_total{source}
serpflow_semantic_guard_rejections_total{engine, reason}
serpflow_semantic_false_hit_reports_total{project_id, engine}
serpflow_adaptive_ttl_seconds{engine, direction}
```

## Related

- [Marginal replanning](marginal-replanning.md): how `inspect()` feeds the cost model
- [Executor](executor.md): how `lookup()` is used at run time
- [Redis operations](../operations/redis.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Marginal-cost replanning](../architecture/marginal-replanning.md) | [Docs index](../README.md) | [The executor](../architecture/executor.md) |
