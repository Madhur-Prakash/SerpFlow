# Production

<p>
  <a href="../README.md#deployment"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="bootstrap: advisory-locked" src="https://img.shields.io/badge/bootstrap-advisory--locked-3fcf8e">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="OpenTelemetry: traces" src="https://img.shields.io/badge/OpenTelemetry-traces-425CC7?logo=opentelemetry&logoColor=white">
  <a href="../../frontend/nginx.conf"><img alt="source: frontend/nginx.conf" src="https://img.shields.io/badge/source-frontend%2Fnginx.conf-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../README.md#deployment) › **Production** · page 9 of 50

**The bundled compose stack is honest about what it is:** a complete, working deployment for a single host. This page covers:

- what changes when it is **not** a single host
- what has to be true **before it holds anybody's real SerpApi credentials**

## Before anything else

| Check | Why |
| --- | --- |
| `ENVIRONMENT=production`, `DEBUG=false` | turns off development behaviour, and makes startup refuse to seed demo data |
| `JWT_SECRET`, `API_KEY_PEPPER`, `CREDENTIAL_KEK` replaced, distinct, none still `change-me` | the defaults are public |
| `CREDENTIAL_KEK` supplied by a KMS, not an environment variable | the KEK unlocks every upstream credential |
| `CORS_ORIGINS` set to real origins, never `*` | credentials travel on these requests |
| TLS terminated in front of the service | tokens and keys travel in headers |
| PostgreSQL password rotated away from the compose default | the default is in the repository |
| PostgreSQL reachable only from the application network | it holds every tenant's data |
| `LOG_JSON=true`, log shipping configured | logs are the incident record |
| **The application's database role does not own the tables** | see below: easiest to miss |

**That last one matters most.** A table owner bypasses row-level security by default, so running the application as the owner **silently disables the backstop**:

```sql
CREATE ROLE serpflow_app LOGIN PASSWORD '...';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO serpflow_app;
GRANT USAGE ON SCHEMA public TO serpflow_app;
```

- **Migrations run as the owner; the application connects as `serpflow_app`**
- Alternatively, mark the tables `FORCE ROW LEVEL SECURITY`, which applies the policies to the owner too
- More: [secrets](../security/secrets.md) · [row-level security](../database/rls.md)

## Scaling

- **The API is stateless.** Everything durable lives in PostgreSQL, Redis, Kafka or object storage
- So API containers **scale horizontally with no coordination**. Three things follow, all already handled:
  - **SSE across workers:** the stream buffer is mirrored into Redis
    - a client can attach to a run started by a different worker
    - `Last-Event-ID` resumption works across a reconnect that lands elsewhere
  - **Background work is separate:** `make worker` runs the Kafka consumers on their own; scale them independently
    - scheduled, bulk, retried and webhook-triggered runs go through Kafka
    - **interactive search executes in-process** and never touches the broker
  - **Rate limiting is central:** Redis-backed, so the limit is per principal across the fleet, not per container
    - it **fails open** if Redis is down
    - budgets, session caps and upstream quota all stay enforced in PostgreSQL

### Storage

Move the payload store off the filesystem:

```bash
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_BUCKET=serpflow-payloads
S3_REGION=...
```

- **Payloads are content-addressed** (`sha256:...`): the same SERP body stored twice is one object
- The bucket should be **private**, versioning off, with a **lifecycle rule** matching your retention settings

### PostgreSQL

The database is the part that actually needs attention.

- **Connection pooling**
  - `DATABASE_POOL_SIZE` and `DATABASE_MAX_OVERFLOW` are **per container**: multiply by replica count before sizing `max_connections`
  - past a handful of replicas, put **PgBouncer in transaction mode** in front
  - `SET LOCAL` is transaction-scoped, so RLS still works correctly through it. Session-level `SET` would not
- **The HNSW index**
  - `m=16, ef_construction=64` is tuned for recall at the corpus sizes this system produces
  - raising `ef_search` at query time improves recall at the cost of latency, with no rebuild
- **Vacuum**
  - `cache_entries` is high-churn: written, updated on hit, expired
  - tighten `autovacuum_vacuum_scale_factor` for that table specifically, not globally

```sql
ALTER TABLE cache_entries SET (autovacuum_vacuum_scale_factor = 0.02);
```

- **Backups**
  - the audit log is hash chained, so a restore that silently loses entries is detectable with `GET /v1/audit/verify`
  - point-in-time recovery is worth the setup here

### Redis

- The hot layer and the principal cache. **Not a source of truth:**
  - the durable cache index is in PostgreSQL; payloads are in object storage
  - a Redis restart repopulates lazily and **loses no credits**
- So `allkeys-lru` with a memory cap is the right policy, and `/readyz` reports Redis as degraded rather than failing

### Kafka

- **The compose broker is a single KRaft node with replication factor 1:** fine for a demo, not a production topology
- For real deployments: **at least three brokers**, and a higher replication factor on every topic
- More: [Kafka operations](../operations/kafka.md)

## Observability

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
LOG_JSON=true
METRICS_ENABLED=true
```

- **Scrape `/metrics`.** The alerting rules that matter are in [observability](../operations/observability.md)
- **The one specific to this system:** `serpflow_semantic_false_hit_reports_total` rising
  - it means the semantic layer is serving wrong data
  - it is a **correctness** page, not a performance one

## Zero-downtime deploys

1. **Migrations are expand-only:** add columns and indexes before the code that uses them; drop in a later release
   - with `RUN_MIGRATIONS_ON_STARTUP=true`, the first new container applies the migration under an advisory lock while old ones still serve
   - the other replicas wait on the lock instead of racing. See [bootstrap](../operations/bootstrap.md)
2. **Build large indexes `CONCURRENTLY`**, in a separate migration
3. **Rotate API keys through the grace window**, rather than cutting them over
4. **Probes:** `/healthz` for liveness (touches nothing), `/readyz` for readiness (checks dependencies)

```yaml
livenessProbe:
  httpGet: { path: /healthz, port: 8000 }
readinessProbe:
  httpGet: { path: /readyz, port: 8000 }
  initialDelaySeconds: 10
```

- **`SEED_ON_STARTUP` is refused automatically** once `ENVIRONMENT` is `staging` or `production`, so demo data cannot reach a real deployment

## Behind a reverse proxy

**Streaming is the only route that needs care.** Buffering must be off, or frames are held until the response ends:

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

- The bundled [`frontend/nginx.conf`](../../frontend/nginx.conf) already does this
- Serving the frontend and API from **one origin** also avoids a CORS preflight on a long-lived connection
- **Watch the `/docs` prefix:** the bundled config proxies it to the API, which shadows the in-app docs routes. See [Docker: known issue](docker.md#known-issue-docs-deep-links)

## Retention

```bash
RETENTION_STANDARD_DAYS=30
RETENTION_HIGH_PII_DAYS=7
```

- **High-PII payloads expire first:** a `google_maps_contributor_reviews` payload is one named person's review history
- The shorter window is the point, not a side effect
- Projects can set retention **below** the global default, never above it

## What is deliberately not here

- **No Kubernetes manifests, no Terraform, no Helm chart**
- Those encode decisions about a specific environment this repository does not know, and a wrong manifest is worse than none
- Documented above instead: the images, the health endpoints, the configuration surface and the scaling properties
- **The orchestration is yours**

## Related

- [Docker](docker.md)
- [Local development](local.md)
- [Bootstrap](../operations/bootstrap.md)
- [Secrets](../security/secrets.md)
- [Threat model](../security/threat-model.md)
- [Observability](../operations/observability.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Deployment guide](../deployment/deployment-guide.md) | [Docs index](../README.md) | [Architecture overview](../architecture/overview.md) |
