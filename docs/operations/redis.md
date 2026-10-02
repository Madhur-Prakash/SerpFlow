# Redis

Redis holds four things, none of which is a source of truth. That single fact
determines every operational decision on this page.

Implementation:
[`app/services/cache/redis_client.py`](../../backend/app/services/cache/redis_client.py),
[`docker/redis/redis.conf`](../../docker/redis/redis.conf).

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

**The hot cache.** The durable cache index is in PostgreSQL and the payloads
are content-addressed in object storage. A Redis flush costs latency on the
next few lookups and **zero credits**, because the exact-match layer in
PostgreSQL still answers. This is why the four-layer architecture puts Redis in
front of PostgreSQL rather than instead of it.

**The principal cache.** Resolution falls through to an indexed PostgreSQL
lookup. Authentication does not depend on Redis being up.

**Rate limiting.** Fails **open** if Redis is unavailable. A deliberate trade:
budgets, session caps and upstream quota are all still enforced in PostgreSQL,
so the money is still bounded, and a cache outage taking the whole API down
would be the worse failure.

**The stream buffer.** The in-process buffer is the primary; Redis is the
mirror that lets a client attach to a run started by a different worker. Losing
it costs cross-worker resumption, not the run.

So: `allkeys-lru` with a memory cap is correct policy, not a compromise.
Eviction under pressure is the intended behaviour.

## Configuration

```
appendonly yes
appendfsync everysec
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
```

Persistence is on even though nothing here is authoritative. It is not for
durability; it is so a restart does not cold-start the whole hot layer and
force every lookup down to PostgreSQL at once.

Raise `maxmemory` for a real deployment. Sizing follows from payload size times
the working set of hot queries, which is workload-specific; the useful signal
is `evicted_keys` climbing while hit rate falls.

## Degradation

Every Redis call is wrapped. A failure returns a miss or a no-op rather than
propagating:

```python
async def hot_get(key: str) -> dict[str, Any] | None:
    try:
        ...
    except Exception as exc:
        # The hot layer is an optimisation. A Redis failure degrades to the
        # durable layers rather than failing the request.
        return None
```

`/readyz` reports Redis as degraded rather than returning 503. Only PostgreSQL
being unreachable fails readiness.

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

Use `SCAN`, never `KEYS`. `KEYS` blocks the server for the duration of a full
keyspace walk, and the one time it matters is the one time you can least
afford it.

The application follows the same rule: `hot_delete_pattern` uses `scan_iter`.

## Invalidation

```http
POST /v1/cache/invalidate
{ "engine": "google_maps", "scope": "project" }
```

Drops matching entries from both Redis and PostgreSQL. Reporting a false
semantic hit from the Run Inspector invalidates the single offending entry.

Flushing Redis by hand is safe:

```bash
docker compose exec redis redis-cli FLUSHDB
```

The next lookups fall through to PostgreSQL and repopulate. No credits are
spent, which is the test of whether a cache layer is really a cache.

## Metrics

```
serpflow_cache_hits_total{layer="hot"|"exact"|"semantic"|"archive"|"miss"}
serpflow_cache_lookup_seconds{layer}
```

The ratio between `hot` and `exact` tells you whether Redis is sized correctly:
a healthy system answers most repeat traffic from `hot`, and a collapse of
`hot` into `exact` with stable overall hit rate means eviction pressure, not a
correctness problem.

## Production

- Dedicated instance, not shared with another application; the key prefixes are
  namespaced but the memory policy is not.
- `requirepass` or ACLs, and no public network exposure.
- Managed Redis with a failover replica if the hot layer is load-bearing for
  latency. It is still not a source of truth, so a failover that loses the
  keyspace is survivable.
- Watch `evicted_keys`, `used_memory`, and the hot/exact hit ratio.

## Related

- [Caching architecture](../architecture/caching.md)
- [Docker](../deployment/docker.md)
- [Observability](observability.md)
- [Troubleshooting](troubleshooting.md)
