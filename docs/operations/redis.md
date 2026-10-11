# Redis

<p>
  <a href="../operations/README.md"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="authoritative: never" src="https://img.shields.io/badge/authoritative-never-555555">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <a href="../../backend/app/services/cache/redis_client.py"><img alt="source: cache/redis_client.py" src="https://img.shields.io/badge/source-cache%2Fredis__client.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [Operations](../operations/README.md) › **Redis** · page 49 of 50

**Redis holds four things, and none of them is a source of truth.** That single fact decides every operational choice on this page.

Implementation: [`app/services/cache/redis_client.py`](../../backend/app/services/cache/redis_client.py) · [`docker/redis/redis.conf`](../../docker/redis/redis.conf) · key format in [`app/services/cache/keys.py`](../../backend/app/services/cache/keys.py)

## What lives in it

| Prefix | Holds | TTL |
| --- | --- | --- |
| `sf:cache:` | the hot exact-match layer: a **pointer** per request (`payload_ref`, `cache_entry_id`, `stored_at`, `query_text`, `ttl_source`). The SERP payload itself is in [object storage](../architecture/caching.md#object-storage) | the entry's TTL when stored; `max(60 s, remaining TTL)` when re-written on a hit |
| `sf:principal:` | resolved API principals ([resolution](../security/api-keys.md#resolution)) | 60 s, `REDIS_PRINCIPAL_CACHE_TTL` |
| `sf:rate:` | per-principal, per-path request counters | 60 s, reset on every request (see [rate limits](#rate-limits)) |
| `sf:stream:` | SSE frames, a list capped at 400, mirrored for cross-worker attach ([reconnecting](../api/streaming.md#reconnecting)) | 15 min, refreshed on every frame |

```
sf:cache:project:<project_id>:<engine>:<request_hash>     project partition, the default
sf:cache:org:<org_id>:<engine>:<request_hash>             organization-level sharing
sf:principal:<key_hash>
sf:rate:<principal_id>:<path>
sf:stream:<run_id>
```

- **The partition is the same one the PostgreSQL index uses** ([partitioning](../architecture/caching.md#partitioning)), so Redis cannot leak an entry across projects that the durable index would not
- **Any hit backed by an index entry rewrites the pointer under the requesting key**, a semantic hit included. The next identical request is then an `exact` hit in Redis, on the same payload, with the stored query as `matched_query`

### Rate limits

- **`RATE_LIMIT_PER_MINUTE` (240) per principal per path**, checked by `rate_limit` in [`app/api/deps.py`](../../backend/app/api/deps.py) on `POST /v1/plan`, `/v1/search` and `/v1/run` only; over it the API answers `429 RATE_LIMITED` ([rate limiting](../api/overview.md#rate-limiting))
- **`incr_rate` runs `INCR` then `EXPIRE 60` on every request**, so the key expires 60 s after the *last* request, not the first. A principal that never pauses for a full minute keeps counting up, and at a steady 5 requests a minute reaches 240 in 48 minutes. It is a sliding idle timeout, not a fixed window

## Why none of it is authoritative

| Data | If Redis loses it |
| --- | --- |
| **Hot cache** | latency on the next few lookups, and **zero credits**: the durable exact-match index in PostgreSQL still answers, and payloads live in object storage |
| **Principal cache** | resolution falls through to an indexed PostgreSQL lookup. Authentication never depends on Redis |
| **Rate limits** | rate limiting **fails open**. Budgets, session caps and upstream quota are still enforced in PostgreSQL, so spend stays bounded |
| **Stream buffer** | cross-worker resumption only. The in-process buffer is the primary; the run is unaffected |

- **That is why the architecture puts Redis in front of PostgreSQL**, not instead of it ([the Redis boundary](../architecture/caching.md#the-redis-boundary), [data stores](../architecture/overview.md#data-stores-and-what-each-is-for))
- **So `allkeys-lru` with a memory cap is correct policy, not a compromise.** Eviction under pressure is the intended behaviour
- **A cache outage taking the whole API down would be the worse failure**

## Configuration

```
appendonly yes
appendfsync everysec
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
```

- Also `timeout 0` (idle clients are never dropped) and `tcp-keepalive 300`. The compose service runs `redis:7-alpine` with this file mounted ([Docker: Redis](../deployment/docker.md#redis))
- **Persistence is on even though nothing here is authoritative**
  - not for durability: so a restart does not cold-start the whole hot layer and push every lookup down to PostgreSQL at once
- **Raise `maxmemory` for a real deployment**
  - sizing follows from pointer size times the working set of hot queries, plus stream buffers and principals, which is workload-specific. Payloads do not count: they are in object storage
  - the useful signal: `evicted_keys` climbing while `keyspace_hits` falls

The client side, in `get_redis()`:

```
REDIS_URL                redis://localhost:6379/0 locally, redis://redis:6379/0 in compose
socket_connect_timeout   3 s
socket_timeout           5 s
health_check_interval    30 s
max_connections          64 per process
```

## Degradation

**Every Redis call is wrapped.** A failure returns a miss or a no-op instead of propagating:

```python
async def hot_get(key: str) -> dict[str, Any] | None:
    try:
        ...
    except Exception as exc:
        # The hot layer is an optimisation. A Redis failure degrades to the
        # durable layers rather than failing the request.
        return None
```

- **`hot_get`, `hot_set` and the pattern delete log `redis.degraded` on each failure**, not once: during an outage expect one warning per cache lookup
- **`hot_ttl`, `hot_delete`, `incr_rate` and the stream mirror fail silently**
- **The 3-second connect timeout bounds the cost** of each failed call while Redis is down
- **`/readyz` reports Redis as degraded**, not 503. Only PostgreSQL being unreachable fails readiness ([health](observability.md#health))

## Inspecting

```bash
make redis-cli
```

```
INFO memory
INFO stats                      # keyspace_hits, keyspace_misses, evicted_keys
DBSIZE

SCAN 0 MATCH sf:cache:* COUNT 100
SCAN 0 MATCH sf:principal:* COUNT 100
TTL sf:cache:project:prj_01M3...:google_maps:a7f3...
GET sf:cache:project:prj_01M3...:google_maps:a7f3...      # the pointer, not the payload
LRANGE sf:stream:run_01M3... 0 -1                          # a run's buffered SSE frames
```

- `make redis-cli` is `docker compose exec redis redis-cli` ([everyday targets](../deployment/local.md#everyday-targets))

- **Use `SCAN`, never `KEYS`**
  - `KEYS` blocks the server for a full keyspace walk, and the one time it matters is the time you can least afford it
- **The application follows the same rule:** `hot_delete_pattern` uses `scan_iter`

## Invalidation

```http
POST /v1/cache/invalidate
{ "engine": "google_maps" }          one engine in this project's partition
{ "entry_id": "..." }                one entry
{ }                                  the whole partition
```

- **Needs `cache:invalidate`** and acts on the request's project ([governance endpoints](../api/overview.md#governance), [`cache/service.py`](../../backend/app/services/cache/service.py))
- **PostgreSQL entries are marked `invalidated_at`, not deleted; Redis keys are deleted** by a `SCAN` over `sf:cache:<partition>:<engine or *>:*`
  - with `entry_id` the Redis sweep has no engine, so it drops every hot key in the partition. That costs latency on the next lookups, not credits
- **Reporting a false semantic hit** from the Run Inspector marks the single offending entry invalidated in PostgreSQL ([report a bad semantic hit](../api/examples.md#report-a-bad-semantic-hit))
  - **it does not touch Redis.** The semantic hit wrote its pointer under the requesting query's key, so that exact query keeps being answered from Redis, as an `exact` hit on the bad payload, until the hot key expires. Follow a report with `POST /v1/cache/invalidate` for the engine to stop it now
- **Flushing Redis by hand is safe:**

```bash
docker compose exec redis redis-cli FLUSHDB
```

- The next lookups fall through to PostgreSQL and repopulate
- **No credits are spent**: the test of whether a cache layer is really a cache

## Metrics

```
serpflow_cache_hits_total{layer="exact"|"semantic"|"archive"|"miss", project_id}
serpflow_cache_lookup_seconds{layer}
```

- Types, labels and the rest: [observability: cache metrics](observability.md#cache)
- **Redis hits and durable-index hits are both labelled `exact`.** The metric does not separate them, and `cache_lookup_seconds{layer="exact"}` mixes a Redis round trip with a PostgreSQL query
- **The planner's per-step `cache_state.reason` does:** "exact hit in the Redis hot layer" against "exact hit in the durable PostgreSQL index (Redis cold)", recorded on each candidate plan ([what the Plan stores](../architecture/planner.md#what-the-plan-stores))
- **To size Redis**, read its own counters instead:
  - `keyspace_hits` against `keyspace_misses`: how much repeat traffic Redis answers
  - `evicted_keys` rising while `keyspace_hits` falls, with a stable overall `exact` hit rate: eviction pressure, **not** a correctness problem

## Production

- **A dedicated instance**, not shared with another application: the key prefixes are namespaced, but the memory policy is not
- **`requirepass` or ACLs**, and no public network exposure. Put the password in `REDIS_URL` (`redis://:password@host:6379/0`); the shipped `redis.conf` sets none ([deployment guide, step 5](../deployment/deployment-guide.md#5-lock-down-the-ports))
- **Managed Redis with a failover replica** if the hot layer is load-bearing for latency
  - it is still not a source of truth, so a failover that loses the keyspace is survivable
- **Watch** `evicted_keys`, `used_memory` and `keyspace_hits`
- **Several API replicas need one shared Redis** for cross-worker stream attach and a rate limit that holds across replicas ([production: Redis](../deployment/production.md#redis))

## Related

- [Caching architecture](../architecture/caching.md#the-redis-boundary): what the hot layer is allowed to answer, and what it defers to PostgreSQL
- [API keys](../security/api-keys.md#resolution): the principal cache in the key-resolution path
- [Streaming](../api/streaming.md#reconnecting): the frame buffer `sf:stream:` mirrors
- [Docker](../deployment/docker.md#redis): the compose service and its mounted config
- [Production](../deployment/production.md#redis): sizing and failover for a real deployment
- [Observability](observability.md#cache): every cache metric, with type and labels
- [Troubleshooting](troubleshooting.md#redis-evicting-too-much): eviction pressure, and what it does not mean

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Kafka](../operations/kafka.md) | [Docs index](../README.md) · [Operations index](../operations/README.md) | [Troubleshooting](../operations/troubleshooting.md) |
