# Redis

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="authoritative: never" src="https://img.shields.io/badge/authoritative-never-555555">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <a href="../../backend/app/services/cache/redis_client.py"><img alt="source: cache/redis_client.py" src="https://img.shields.io/badge/source-cache%2Fredis__client.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Redis** · page 34 of 50

**Redis holds four things, and none of them is a source of truth.** That single fact decides every operational choice on this page.

Implementation: [`app/services/cache/redis_client.py`](../../backend/app/services/cache/redis_client.py) · [`docker/redis/redis.conf`](../../docker/redis/redis.conf)

## What lives in it

| Prefix | Holds | TTL |
| --- | --- | --- |
| `sf:cache:` | the hot cache layer: exact-match SERP payloads | the entry's TTL |
| `sf:principal:` | resolved API principals | 60 s, `REDIS_PRINCIPAL_CACHE_TTL` |
| `sf:rate:` | rate-limit counters | 60 s window |
| `sf:stream:` | SSE frame buffers, mirrored for cross-worker attach | 15 min |

```
sf:cache:<partition_key>:<engine>:<request_hash>
sf:principal:<key_hash>
sf:rate:<principal>:<path>
sf:stream:<run_id>
```

## Why none of it is authoritative

| Data | If Redis loses it |
| --- | --- |
| **Hot cache** | latency on the next few lookups, and **zero credits**: the durable exact-match index in PostgreSQL still answers, and payloads live in object storage |
| **Principal cache** | resolution falls through to an indexed PostgreSQL lookup. Authentication never depends on Redis |
| **Rate limits** | rate limiting **fails open**. Budgets, session caps and upstream quota are still enforced in PostgreSQL, so spend stays bounded |
| **Stream buffer** | cross-worker resumption only. The in-process buffer is the primary; the run is unaffected |

- **That is why the architecture puts Redis in front of PostgreSQL**, not instead of it
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

- **Persistence is on even though nothing here is authoritative**
  - not for durability: so a restart does not cold-start the whole hot layer and push every lookup down to PostgreSQL at once
- **Raise `maxmemory` for a real deployment**
  - sizing follows from payload size times the working set of hot queries, which is workload-specific
  - the useful signal: `evicted_keys` climbing while `keyspace_hits` falls

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

- **`/readyz` reports Redis as degraded**, not 503. Only PostgreSQL being unreachable fails readiness

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
TTL sf:cache:prj_01M3.../google_maps/a7f3...
```

- **Use `SCAN`, never `KEYS`**
  - `KEYS` blocks the server for a full keyspace walk, and the one time it matters is the time you can least afford it
- **The application follows the same rule:** `hot_delete_pattern` uses `scan_iter`

## Invalidation

```http
POST /v1/cache/invalidate
{ "engine": "google_maps", "scope": "project" }
```

- **Drops matching entries from both Redis and PostgreSQL**
- **Reporting a false semantic hit** from the Run Inspector invalidates the single offending entry
- **Flushing Redis by hand is safe:**

```bash
docker compose exec redis redis-cli FLUSHDB
```

- The next lookups fall through to PostgreSQL and repopulate
- **No credits are spent**: the test of whether a cache layer is really a cache

## Metrics

```
serpflow_cache_hits_total{layer="exact"|"semantic"|"archive"|"miss"}
serpflow_cache_lookup_seconds{layer}
```

- **Redis hits and durable-index hits are both labelled `exact`.** The metric does not separate them
- **To size Redis**, read its own counters instead:
  - `keyspace_hits` against `keyspace_misses`: how much repeat traffic Redis answers
  - `evicted_keys` rising while `keyspace_hits` falls, with a stable overall `exact` hit rate: eviction pressure, **not** a correctness problem

## Production

- **A dedicated instance**, not shared with another application: the key prefixes are namespaced, but the memory policy is not
- **`requirepass` or ACLs**, and no public network exposure
- **Managed Redis with a failover replica** if the hot layer is load-bearing for latency
  - it is still not a source of truth, so a failover that loses the keyspace is survivable
- **Watch** `evicted_keys`, `used_memory` and `keyspace_hits`

## Related

- [Caching architecture](../architecture/caching.md)
- [Docker](../deployment/docker.md)
- [Observability](observability.md)
- [Troubleshooting](troubleshooting.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Kafka](../operations/kafka.md) | [Docs index](../README.md) | [Troubleshooting](../operations/troubleshooting.md) |
