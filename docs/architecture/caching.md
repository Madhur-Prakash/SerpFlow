# Caching

<p>
  <a href="../architecture/README.md"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="layers: 4" src="https://img.shields.io/badge/layers-4-2F6BFF">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <a href="../../backend/app/services/cache"><img alt="source: services/cache" src="https://img.shields.io/badge/source-services%2Fcache-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 12 min" src="https://img.shields.io/badge/read-12%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../architecture/README.md) › **Caching** · page 18 of 57

**Four layers, in order. Only the last one spends.**

```
EXACT      Redis                  hot, TTL-based, fast, NOT the source of truth
SEMANTIC   PostgreSQL + pgvector  partition-filtered, guard-protected
ARCHIVE    SerpApi Searches       re-reads consume no credit
LIVE       SerpApi                the only layer that costs money
```

- The exact layer is backed by a **durable index in PostgreSQL** ([`cache_entries`](../database/schema.md#cache)): a Redis miss falls through to it, not straight to a live call
- The [executor](executor.md) walks the layers per call; the [planner](planner.md) inspects them per candidate, before anything runs
- Code: [`app/services/cache/`](../../backend/app/services/cache)

## Two entry points

```python
cache.inspect(engine, params, freshness=...)   # planner: would this be free?
cache.lookup(engine, params, freshness=...)    # executor: give me the payload
```

| Method | Called by | Side effects |
| --- | --- | --- |
| `inspect` | the planner, for **every step of every candidate** during ranking | nothing durable: it only observes lookup latency and guard-rejection counts in metrics |
| `lookup` | the executor, about to run a step | records guard rejections, increments hit counters ([`serpflow_cache_hits_total`](../operations/observability.md#cache)), repopulates Redis |
| `store` | the executor, after a live call | writes object storage, the durable row and Redis |

- `inspect` is what makes marginal cost **a real number**, not something observed after the fact. See [costing a step](marginal-replanning.md#costing-a-step)
- **A warm entry must also be fresh enough to count:** `CacheState` carries `available` and `acceptable` separately, and only both together are warm

## Normalisation

Before anything is hashed:

```
whitespace collapsed       "  Cafes  IN   Koramangala " -> "cafes in koramangala"
casing folded
accents stripped
parameters stably ordered
empty and null values dropped
non-semantic parameters removed:  api_key, output, no_cache, async, zero_trace,
                                  json_restrictor, device_id, _limit
```

- **Stripping non-semantic parameters is what makes the exact layer hit at all:** they never change the result, so they must never change the key
- The key is the SHA-256 of the normalised request, in [`keys.py`](../../backend/app/services/cache/keys.py); [`tests/unit/test_cache_guard.py`](../../backend/tests/unit/test_cache_guard.py) asserts each rule
- **The key is built from the parameters actually sent**, so a step whose query was reshaped by a [query adapter](planner.md#query-adapters) is cached under the adapted value (`q=NVDA:NASDAQ`), not the sentence

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
- The **HNSW index** (`m=16, ef_construction=64`, cosine ops, created in [`0001_initial`](../database/migrations.md#0001_initial)) orders within the already-narrowed rows
- Organizations are walled off underneath that: every row also carries `org_id`, enforced by [row-level security](../database/rls.md#covered-tables)

### Execution mode is not part of the key

- **Lookups do not filter on the mode that stored an entry.** `cache_entries` records `mode` and `source_run_id`, but the key, the partition and the semantic query all ignore them
- **So within one partition, data crosses modes**
  - a payload stored by a `test` key run, deterministic mock data, can be served as an exact or semantic hit to a later `live` or `replay` run
  - a replayed cassette's payload can likewise serve a later live run
- **The [reference demo](../product/demo.md#phase-2-a-different-project-warms-the-maps-chain) depends on this:** its warm-up runs on a test key, and those entries are what the next run plans and executes against
- **The served step does not say which mode produced the entry.** The step row and the `X-SerpFlow-Mode` header carry the run's own mode; the entry's `mode` is visible only in the cache dashboard's entry list ([`GET /v1/cache/entries`](../api/overview.md#governance))
- **Where mock data must never reach a live caller**, keep test keys in their own project and leave organization-level sharing off. See [mock data mistaken for live](../security/threat-model.md#replay-or-mock-data-mistaken-for-live)

### Organization-level sharing

- **Opt-in, per project:** the `organization` partition applies only when the project has `shared_cache_enabled` **and** the organization's `cache_scope` is `organization` (`_cache_scope` in [`runs.py`](../../backend/app/services/runs.py))
- **It crosses a billing and a data boundary:** results fetched for one project become readable by another
  - so the UI says exactly that at the point of enabling it
- **The [ledger](../database/schema.md#governance) (`budget_ledger`) keeps the two sides apart:**

```
SPEND     attributed to the project that fetched
SAVINGS   attributed to the project that benefited
```

- [`GET /v1/analytics/cross-project`](../api/overview.md#governance) reports the flows between them
- The [reference demo](../product/demo.md#phase-2-a-different-project-warms-the-maps-chain) depends on it: a second project warms the chain the first one later plans against

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
- More: [ADR 0002](../adr/0002-deterministic-semantic-guard.md)

### Rejections are evidence

- **Every rejected near-match is written to [`semantic_guard_rejections`](../database/schema.md#cache)**, with both queries, both token sets, the similarity score and the reason
  - only on `lookup()`, a request that actually happened: planner probes are not persisted
- The [cache dashboard](frontend.md#routes) (`/app/cache`) renders them, from [`GET /v1/cache/guard-rejections`](../api/overview.md#governance)
- That is how the threshold gets tuned **with evidence**, not intuition
- [`serpflow_semantic_guard_rejections_total`](../operations/observability.md#cache) counts them by engine and reason (`numeral_mismatch`, `entity_mismatch`, `version_mismatch`)
  - it is incremented inside `inspect()`, so it also counts rejections seen while the planner probes candidates, and runs higher than the table
- A hit the guard let through anyway: [troubleshooting](../operations/troubleshooting.md#a-semantic-hit-returned-the-wrong-thing)

### Identifier lookups skip the layer entirely

- `google_maps_reviews?data_id=0x...` has no meaningful semantic neighbourhood: a "similar" `data_id` is **a different place**
- A semantic hit there would be a correctness bug, not a saving
- So requests addressed purely by an opaque identifier (`IDENTIFIER_PARAMS` in [`keys.py`](../../backend/app/services/cache/keys.py): `data_id`, `place_id`, `contributor_id`, `product_id`, `result_id`...) **never consult the layer**

### Threshold, and what the local embedder means for it

- **Default similarity threshold: `0.95`** (`SEMANTIC_SIMILARITY_THRESHOLD` in [`.env.example`](../../.env.example)), overridable per project with `semantic_threshold`
- **The default embedder is local and deterministic** (feature hashing, [`embedding.py`](../../backend/app/integrations/llm/embedding.py)): no network, no key, identical across processes and CI
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

- **No durable state is destroyed and no credits are lost**, which is why the hot layer can evict aggressively (`allkeys-lru`, 512 MiB: [Redis configuration](../operations/redis.md#configuration))
- **A Redis miss is not a cache miss:** the lookup falls through to the durable index, and repopulates Redis on the way back
- Hot keys are `sf:cache:<partition_key>:<engine>:<request_hash>`; everything else Redis holds is in [what lives in it](../operations/redis.md#what-lives-in-it)

## Object storage

- **Large SERP payloads do not belong in PostgreSQL.** They go to S3-compatible storage; PostgreSQL holds only `payload_ref`
  - the **filesystem by default** (`STORAGE_BACKEND=filesystem`), so `make dev` needs nothing extra; `STORAGE_BACKEND=s3` with MinIO from the compose `storage` profile ([Docker](../deployment/docker.md#running)), or any S3 endpoint
- **Keys are the SHA-256 of the gzipped body**, so two identical responses (common once engines are cached and replayed) deduplicate to one object
- Code: [`app/integrations/storage/`](../../backend/app/integrations/storage)

## The Searches Archive

- **Re-reading an archived SerpApi search consumes no credit**, so the executor checks [`archive_refs`](../database/schema.md#cache) (same partition, same request hash) before paying for a live call
  - in `live` and `record` modes only: replay and mock never reach SerpApi
  - a re-read is recorded in the ledger as an `archive` saving
- `search_id`, `engine`, the request hash and the credential fingerprint are recorded after every live call that returns a `search_id`
- **`get_archived` and `search` are separate client methods** ([`client.py`](../../backend/app/integrations/serpapi/client.py)), so no code path can accidentally bill for a re-read

## Billed empty results

**A SerpApi "no results" answer is a billed, successful, empty search, and it is cached like any other.**

- SerpApi reports "found nothing" through the same `error` field it uses for real failures: `"Google Finance hasn't returned any results for this query."`
- [`SerpApiResponse`](../../backend/app/integrations/serpapi/client.py) tells them apart:

```
is_empty_result   HTTP status below 400, an error field, and either
                  search_metadata.status == "Success" or the message
                  says it "hasn't returned any results"
is_error          any other error field, or HTTP 400 and above
```

- **An empty result is not `is_error`**, so the [executor](executor.md#writing-back) treats it as a successful live call:
  - the spend is written to the ledger and to [`serpflow_credits_spent_total`](../operations/observability.md#spend-and-savings)
  - the payload goes through `store()`, so the next identical request is an exact hit, not a second bill
  - an `archive_refs` row is recorded when SerpApi returned a `search_id`, and in `record` mode the cassette is saved
- **The result says why it is empty:** when the terminal step has no items, SerpApi's message is passed through as `summary.notice` (at most 300 characters), and the search page shows it
- **Before the fix** it was treated as a failure: the payload was thrown away and the ledger recorded **0 credits for a search SerpApi charged for**
- [`test_live_responses.py`](../../backend/tests/unit/test_live_responses.py) asserts which responses are empty and which stay errors
- The commonest cause, a sentence sent where Google Finance wants a ticker, is now prevented upstream by the [query adapter](planner.md#query-adapters)

## Adaptive TTL

Starts from the engine's `volatility_prior`, then moves on each refresh:

```
top-10 unchanged      TTL x 1.5
significant churn     TTL x 0.5      (3 or more of the top 10 moved)
minor churn           TTL held
```

- **Clamped between 5 minutes and 90 days** (`ADAPTIVE_TTL_MIN_SECONDS`, `ADAPTIVE_TTL_MAX_SECONDS`)
- **Learned per entry, and observed per query class, not only per engine**
  - `google` has a 24-hour prior, but `google?q=current gold price` behaves nothing like `google?q=history of the roman empire`
  - a per-engine-only controller averages them, and is wrong for both
  - each adjustment moves that entry's own TTL, and is recorded with its engine and query class, which is what the volatility view groups by
- **A TTL may never outlive the step's freshness requirement**
  - a 30-day entry serving a `realtime` step would stay available long after it stopped being acceptable
  - `cap_for_freshness` shortens it at write time, and records `ttl_source: freshness_capped`
- **Every TTL names its source:**

```
volatility_prior    seeded from the engine's prior
project_override    the project's per-engine TTL override, still clamped and capped
freshness_capped    shortened to the step's freshness bound
learned             moved by observed churn
```

- **Where learning runs:** `adapt` in [`ttl.py`](../../backend/app/services/cache/ttl.py) is applied by the `serpflow.cache.refresh` [Kafka consumer](../operations/kafka.md#topics) ([`handlers.py`](../../backend/app/workers/consumers/handlers.py))
  - a live re-fetch through the executor re-seeds the entry from the prior instead
  - at HEAD nothing in the request path publishes to that topic (`queue_cache_refresh` has no caller), so `learned` TTLs appear only when something produces refresh messages
- **Every adjustment is written to [`ttl_observations`](../database/schema.md#cache)** with the churn ratio and measured interval, and observed in [`serpflow_adaptive_ttl_seconds`](../operations/observability.md#cache): the volatility view in Analytics renders it, from [`GET /v1/analytics/volatility`](../api/overview.md#governance)

## Invalidation

| Trigger | How |
| --- | --- |
| **Manual** | from the [cache dashboard](frontend.md#routes), or [`POST /v1/cache/invalidate`](../api/overview.md#governance), by engine or by entry. Needs [`cache:invalidate`](../security/api-keys.md#roles) |
| **False-hit report** | an operator reports a bad semantic hit from the [Run Inspector](frontend.md#routes) ([`POST /v1/runs/{id}/report-false-hit`](../api/overview.md#runs)); writes a [`false_hit_reports`](../database/schema.md#cache) row and increments [`serpflow_semantic_false_hit_reports_total`](../operations/observability.md#cache) |
| **Expiry** | an entry past its `expires_at` (its TTL) is filtered out of every lookup. It is not deleted |

- **Manual invalidation** sets `invalidated_at` on the durable rows, and **deletes the matching Redis keys by pattern** (`sf:cache:<partition>:<engine or *>:*`), both audited as `cache.invalidated`
- **A false-hit report** sets `invalidated_at` on the matched entry when `invalidate_entry` is true (the default). It does not delete Redis keys, so a hot copy written by the bad hit can serve until its TTL runs out
- **Retention is a run property, not a cache trigger:** runs carry `expires_at` (30 days, 7 for high-PII), see [executor retention](executor.md#retention). Cache rows record `pii_risk`, but no job purges expired rows at HEAD
- Worked request: [report a bad semantic hit](../api/examples.md#report-a-bad-semantic-hit)

## Metrics

```
serpflow_cache_hits_total{layer, project_id}                  exact | semantic | archive | miss
serpflow_cache_lookup_seconds{layer}
serpflow_credits_saved_total{org_id, project_id, source}
serpflow_semantic_guard_rejections_total{engine, reason}
serpflow_semantic_false_hit_reports_total{project_id, engine}
serpflow_adaptive_ttl_seconds{engine, direction}              extended | shortened | unchanged
```

- **`credits_saved_total` is incremented on cache-layer hits only.** Routing savings and executor archive re-reads go to the ledger, which is what [`/v1/analytics/savings`](../api/overview.md#governance) decomposes
- What each series means, and what to alert on: [cache metrics](../operations/observability.md#cache)

## Related

- [Marginal replanning](marginal-replanning.md#costing-a-step): how `inspect()` feeds the cost model
- [Executor](executor.md#writing-back): how `lookup()` and `store()` are used at run time
- [The planner](planner.md#query-adapters) and [the engine catalog](catalog.md#volatility-and-pii): why a Google Finance step is cached under a ticker, and where each entry's `volatility_prior` and `pii_risk` come from
- [Redis](../operations/redis.md#why-none-of-it-is-authoritative): the hot layer, and why losing it costs no credits
- [Database schema](../database/schema.md#cache): `cache_entries`, `archive_refs`, `ttl_observations`, `semantic_guard_rejections`, `false_hit_reports`
- [Observability](../operations/observability.md#cache): the cache series, and what a falling rejection count means
- [ADR 0002](../adr/0002-deterministic-semantic-guard.md): the guard that ignores the score, and why a warm entry can still be refused
- [Troubleshooting](../operations/troubleshooting.md#nothing-is-ever-warm): nothing is ever warm, a wrong semantic hit, Redis evicting too much

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Marginal-cost replanning](../architecture/marginal-replanning.md) | [Docs index](../README.md) · [Architecture index](../architecture/README.md) | [The executor](../architecture/executor.md) |
