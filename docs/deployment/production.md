# Production

SerpFlow ships a compose stack that is honest about what it is: a complete,
working deployment suited to a single host. This page covers what changes when
it is not a single host, and what has to be true before it holds anybody's real
SerpApi credentials.

## Before anything else

- [ ] `ENVIRONMENT=production`, `DEBUG=false`
- [ ] `JWT_SECRET`, `API_KEY_PEPPER` and `CREDENTIAL_KEK` all replaced, all
      distinct, none still saying `change-me`
- [ ] `CREDENTIAL_KEK` supplied by a KMS, not an environment variable
- [ ] `CORS_ORIGINS` set to real origins, never `*`
- [ ] TLS terminated in front of the service
- [ ] PostgreSQL password rotated away from the compose default
- [ ] PostgreSQL reachable only from the application network
- [ ] `LOG_JSON=true` and log shipping configured
- [ ] The application's database role does not own the tables

That last one is the easiest to miss. A table owner bypasses row-level security
by default, so running the application as the owner silently disables the
backstop:

```sql
CREATE ROLE serpflow_app LOGIN PASSWORD '...';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO serpflow_app;
GRANT USAGE ON SCHEMA public TO serpflow_app;
```

Migrations run as the owner; the application connects as `serpflow_app`.
Alternatively, mark the tables `FORCE ROW LEVEL SECURITY`, which applies the
policies to the owner too.

See [secrets](../security/secrets.md) and
[row-level security](../database/rls.md).

## Scaling

The API is stateless. Everything that persists is in PostgreSQL, Redis, Kafka
or object storage, so API containers scale horizontally with no coordination.

Three things follow from that and are already handled:

**SSE across workers.** The stream buffer is mirrored into Redis, so a client
can attach to a run started by a different worker process, and `Last-Event-ID`
resumption works across a reconnect that lands elsewhere.

**Background work is separate.** `make worker` runs the Kafka consumers on
their own. Scale them independently of the API: scheduled, bulk, retried and
webhook-triggered runs go through Kafka, while interactive search executes
in-process and never touches the broker.

**Rate limiting is central.** It is Redis-backed, so the limit is per principal
across the fleet rather than per container. It fails open if Redis is
unavailable; budgets, session caps and upstream quota all remain enforced in
PostgreSQL.

### Storage

Switch the payload store off the filesystem:

```bash
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_BUCKET=serpflow-payloads
S3_REGION=...
```

Payloads are content-addressed (`sha256:...`), so the same SERP body stored
twice is one object. The bucket should be private, versioned off, and covered
by a lifecycle rule that matches your retention settings.

### PostgreSQL

The database is the part that actually needs attention.

- **Connection pooling.** `DATABASE_POOL_SIZE` and `DATABASE_MAX_OVERFLOW` are
  per container; multiply by the replica count before sizing `max_connections`.
  Past a handful of replicas, put PgBouncer in transaction mode in front —
  noting that `SET LOCAL` is transaction-scoped, so RLS still works correctly
  through it, which is not true of session-level `SET`.
- **The HNSW index.** `m=16, ef_construction=64` is tuned for recall at the
  corpus sizes this system produces. Raising `ef_search` at query time improves
  recall at the cost of latency; the index itself does not need rebuilding for
  that.
- **Vacuum.** `cache_entries` is a high-churn table: entries are written,
  updated on hit, and expired. Tighten `autovacuum_vacuum_scale_factor` for it
  specifically rather than globally.

```sql
ALTER TABLE cache_entries SET (autovacuum_vacuum_scale_factor = 0.02);
```

- **Backups.** The audit log is hash chained, so a restore that silently loses
  entries is detectable with `GET /v1/audit/verify`. Point-in-time recovery is
  worth the setup here.

### Redis

Redis is the hot layer and the principal cache. It is **not** a source of
truth: the durable cache index is in PostgreSQL and payloads are in object
storage, so a Redis restart repopulates lazily and loses no credits.

That is why `allkeys-lru` with a memory cap is the right policy, and why
`/readyz` reports Redis as degraded rather than failing.

### Kafka

The compose broker is a single KRaft node with replication factor 1, which is
fine for a demo and is not a production topology. For a real deployment use at
least three brokers and raise the replication factor on every topic. See
[Kafka operations](../operations/kafka.md).

## Observability

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
LOG_JSON=true
METRICS_ENABLED=true
```

Scrape `/metrics`. The alerting rules that matter are in
[observability](../operations/observability.md); the one that is specific to
this system is `serpflow_semantic_false_hit_reports_total` rising, which means
the semantic layer is serving wrong data and is a correctness page, not a
performance one.

## Zero-downtime deploys

1. Migrations are expand-only: add columns and indexes before the code that
   uses them, drop in a later release. The container runs
   `alembic upgrade head` at start, so a rolling deploy applies the migration
   from the first new container while old ones are still serving.
2. Build indexes `CONCURRENTLY` in a separate migration when the table is
   large.
3. Rotate API keys through the grace window rather than cutting them over.
4. `/healthz` is the liveness probe (touches nothing); `/readyz` is the
   readiness probe (checks dependencies).

```yaml
livenessProbe:
  httpGet: { path: /healthz, port: 8000 }
readinessProbe:
  httpGet: { path: /readyz, port: 8000 }
  initialDelaySeconds: 10
```

## Behind a reverse proxy

Streaming is the only route that needs care. Buffering must be off, or frames
are held until the response ends:

```nginx
location ~ ^/v1/runs/[^/]+/stream$ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding off;
    proxy_read_timeout 10m;
}
```

The bundled [`frontend/nginx.conf`](../../frontend/nginx.conf) already does
this. Serving the frontend and the API from one origin also avoids a CORS
preflight on a long-lived connection.

## Retention

```bash
RETENTION_STANDARD_DAYS=30
RETENTION_HIGH_PII_DAYS=7
```

High-PII payloads expire first. A `google_maps_contributor_reviews` payload is
one named person's review history, so a shorter window is the point rather than
a side effect. Projects can set their own retention below the global default,
never above it.

## What is deliberately not here

No Kubernetes manifests, no Terraform, no Helm chart. Those encode decisions
about a specific environment that this repository does not know, and a wrong
manifest is worse than none. The container images, the healthcheck endpoints,
the configuration surface and the scaling properties are all documented above;
the orchestration is yours.

## Related

- [Docker](docker.md)
- [Local development](local.md)
- [Secrets](../security/secrets.md)
- [Threat model](../security/threat-model.md)
- [Observability](../operations/observability.md)
