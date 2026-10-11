# Production

<p>
  <a href="../deployment/README.md"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="bootstrap: advisory-locked" src="https://img.shields.io/badge/bootstrap-advisory--locked-3fcf8e">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="OpenTelemetry: traces" src="https://img.shields.io/badge/OpenTelemetry-traces-425CC7?logo=opentelemetry&logoColor=white">
  <a href="../../backend/app/core/security.py"><img alt="source: core/security.py" src="https://img.shields.io/badge/source-core%2Fsecurity.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 11 min" src="https://img.shields.io/badge/read-11%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../deployment/README.md) › **Production** · page 12 of 50

**The bundled compose stack is honest about what it is:** a complete, working deployment for a single host. The step-by-step version of that host is the [deployment guide](deployment-guide.md). This page covers:

- what changes when it is **not** a single host
- what has to be true **before it holds anybody's real SerpApi credentials**

## Before anything else

| Check | Why |
| --- | --- |
| `ENVIRONMENT=production`, `DEBUG=false` | turns off development behaviour, and makes startup refuse to seed demo data ([bootstrap](../operations/bootstrap.md#3-an-environment-refusal)) |
| `JWT_SECRET`, `API_KEY_PEPPER`, `CREDENTIAL_KEK` replaced, distinct, none still `change-me` | the defaults are public ([generating real ones](../security/secrets.md#generating-real-ones)) |
| `CREDENTIAL_KEK` held in a secret manager or KMS and injected at deploy time; on a single host, at least a `chmod 600` `.env` ([step 4](deployment-guide.md#4-configure-the-environment)) | the KEK unlocks every upstream credential. The code reads it from the environment (`_load_kek` in [`app/core/security.py`](../../backend/app/core/security.py)); there is no KMS client yet, see [credentials](../security/credentials.md#envelope-encryption) |
| `CORS_ORIGINS` set to real origins, never `*` | credentials travel on these requests |
| TLS terminated in front of the service | tokens and keys travel in headers ([deployment guide: TLS](deployment-guide.md#9-put-tls-in-front)) |
| PostgreSQL password rotated away from the compose default | the default is in the repository |
| PostgreSQL reachable only from the application network | it holds every tenant's data ([locking down the ports](deployment-guide.md#5-lock-down-the-ports)) |
| `TRUSTED_PROXY_HOPS` equal to the number of proxies in front of the API | otherwise the audit log, sessions and key `last_used_ip` record the proxy's address, or one the caller made up ([troubleshooting](../operations/troubleshooting.md#every-caller-is-recorded-with-the-proxys-ip)) |
| `LOG_JSON=true`, log shipping configured | logs are the incident record ([logging](../operations/observability.md#logging)) |
| **The application's database role does not own the tables** | see below: easiest to miss |

**That last one matters most.** A table owner bypasses row-level security by default, so running the application as the owner **silently disables the backstop**:

```sql
CREATE ROLE serpflow_app LOGIN PASSWORD '...';
GRANT USAGE ON SCHEMA public TO serpflow_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO serpflow_app;
-- run as the owner, so tables that later migrations create are covered too
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO serpflow_app;
```

- **Migrations run as the owner; the application connects as `serpflow_app`**
  - **the startup bootstrap migrates with the application's own `DATABASE_URL`** ([`app/db/bootstrap.py`](../../backend/app/db/bootstrap.py)), so with a separate role set `RUN_MIGRATIONS_ON_STARTUP=false` and run `alembic upgrade head` as the owner before each rollout
  - in the bundled compose file the backend's `DATABASE_URL` is built from `POSTGRES_USER`; override it for the backend to connect as `serpflow_app` ([Docker](docker.md#running))
  - every table uses string identifiers, so there are no sequences to grant
- **`FORCE ROW LEVEL SECURITY` is not an alternative to this role.** It applies the policies to a table owner, but never to a superuser, and the bundled stack's `POSTGRES_USER` is a superuser. Use it in addition, for any path that still connects as the owner: [deployment guide, step 8](deployment-guide.md#8-make-row-level-security-bind)
- More: [secrets](../security/secrets.md) · [row-level security](../database/rls.md) · [threat model: cross-tenant data access](../security/threat-model.md#cross-tenant-data-access)

## Scaling

- **The API is stateless.** Everything durable lives in PostgreSQL, Redis, Kafka or object storage ([data stores](../architecture/overview.md#data-stores-and-what-each-is-for))
- So API containers **scale horizontally with no coordination**. Three things follow, all already handled:
  - **SSE across workers:** the stream buffer is mirrored into Redis (`sf:stream:`, [`app/services/stream.py`](../../backend/app/services/stream.py))
    - a client can attach to a run started by a different worker
    - `Last-Event-ID` resumption works across a reconnect that lands elsewhere ([reconnecting](../api/streaming.md#reconnecting))
  - **Background work can be scaled separately:** [`make worker`](local.md#everyday-targets) (`python -m app.workers.runner`) runs the Kafka consumers on their own ([running consumers](../operations/kafka.md#running-consumers))
    - scheduled, bulk, retried and webhook-triggered runs go through Kafka
    - **interactive search executes in-process** and never touches the broker
    - **every API process also starts the same consumers in-process** while `KAFKA_ENABLED=true` ([`app/main.py`](../../backend/app/main.py)). They share the `serpflow-workers` group with the workers, so partitions spread across both
    - there is no setting that turns off only the API's consumers: `KAFKA_ENABLED=false` also disables its producer, so its background events are dropped and `/readyz` reports Kafka `degraded`
  - **Rate limiting is central:** Redis-backed, so the limit is per principal across the fleet, not per container ([rate limiting](../api/overview.md#rate-limiting))
    - it **fails open** if Redis is down
    - budgets, session caps and upstream quota all stay enforced in PostgreSQL ([budget enforcement](../architecture/executor.md#budget-enforcement))
- **Per container, `python -m app.server` also takes `--workers`**; the compose `CMD` runs one process ([`app/server.py`](../../backend/app/server.py))

### Storage

Move the payload store off the filesystem:

```bash
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_BUCKET=serpflow-payloads
S3_REGION=...
S3_ACCESS_KEY_ID=...          # or leave both unset to use the SDK's default credential chain
S3_SECRET_ACCESS_KEY=...
```

- **Payloads are content-addressed** (`sha256:...`, `content_address` in [`app/core/security.py`](../../backend/app/core/security.py)): the same SERP body stored twice is one object ([object storage](../architecture/caching.md#object-storage))
- **The bucket is created on first use** if it does not exist, so the credentials need `CreateBucket` or the bucket must already exist ([`app/integrations/storage/__init__.py`](../../backend/app/integrations/storage/__init__.py))
- **`/readyz` reports the bucket** under `object_storage`, but a failing store does not change the overall status
- The bucket should be **private**, versioning off, with a **lifecycle rule** matching your retention settings
- **The S3 secret is a deployment secret:** [secrets: inventory](../security/secrets.md#inventory)

### PostgreSQL

The database is the part that actually needs attention.

- **Connection pooling**
  - `DATABASE_POOL_SIZE` (10) and `DATABASE_MAX_OVERFLOW` (20) are **per process**: multiply by replicas, uvicorn workers and `make worker` processes before sizing `max_connections`
  - past a handful of replicas, put **PgBouncer in transaction mode** in front
  - `SET LOCAL` is transaction-scoped, so RLS still works correctly through it. Session-level `SET` would not ([how RLS works](../database/rls.md#how-it-works))
  - the startup bootstrap's advisory locks are **session-scoped** on their own connection ([`app/db/bootstrap.py`](../../backend/app/db/bootstrap.py)), which transaction pooling does not preserve: point the migrating process at PostgreSQL directly
- **The HNSW index** (`ix_cache_entries_embedding_hnsw`, created in [`0001_initial`](../database/migrations.md#0001_initial))
  - `m=16, ef_construction=64` is tuned for recall at the corpus sizes this system produces
  - raising `ef_search` at query time improves recall at the cost of latency, with no rebuild
- **Vacuum**
  - [`cache_entries`](../database/schema.md#cache) is high-churn: written, updated on hit, expired
  - tighten `autovacuum_vacuum_scale_factor` for that table specifically, not globally

```sql
ALTER TABLE cache_entries SET (autovacuum_vacuum_scale_factor = 0.02);
```

- **Backups**
  - the audit log is hash chained, so a restore that silently loses entries is detectable with `GET /v1/audit/verify`
  - point-in-time recovery is worth the setup here
  - the single-host commands: [deployment guide: backups](deployment-guide.md#13-backups)

### Redis

- The hot layer, the principal cache, rate-limit counters and SSE buffers ([what lives in it](../operations/redis.md#what-lives-in-it)). **Not a source of truth:**
  - the durable cache index is in PostgreSQL; payloads are in object storage
  - a Redis restart repopulates lazily and **loses no credits**
- So `allkeys-lru` with a memory cap is the right policy, and `/readyz` reports Redis as degraded rather than failing
- More: [Redis operations: production](../operations/redis.md#production)

### Kafka

- **The compose broker is a single KRaft node with replication factor 1:** fine for a demo, not a production topology
- For real deployments: **at least three brokers**, and a higher replication factor on every topic
  - `ensure_topics` creates missing topics with replication factor 1 ([`app/workers/kafka.py`](../../backend/app/workers/kafka.py)), so create them yourself on a multi-broker cluster before the first worker starts
- More: [Kafka operations: production](../operations/kafka.md#production)

## Observability

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
LOG_JSON=true
METRICS_ENABLED=true
```

- **Scrape `/metrics`** from inside the network; it is unauthenticated, so do not expose it publicly ([deployment guide: TLS](deployment-guide.md#9-put-tls-in-front)). The alerting rules that matter are in [observability: alerting](../operations/observability.md#alerting)
- **The one specific to this system:** [`serpflow_semantic_false_hit_reports_total`](../operations/observability.md#cache) rising
  - it means the semantic layer is serving wrong data
  - it is a **correctness** page, not a performance one

## Zero-downtime deploys

1. **Migrations are expand-only:** add columns and indexes before the code that uses them; drop in a later release ([writing a new revision](../database/migrations.md#writing-a-new-revision))
   - with `RUN_MIGRATIONS_ON_STARTUP=true`, the first new container applies the migration under an advisory lock while old ones still serve
   - the other replicas wait on the lock instead of racing. See [bootstrap](../operations/bootstrap.md#1-an-advisory-lock)
2. **Build large indexes `CONCURRENTLY`**, in a separate migration
3. **Rotate API keys through the grace window**, rather than cutting them over: both keys work for 60 minutes by default ([API keys: rotation](../security/api-keys.md#rotation))
4. **Probes:** `/healthz` for liveness (touches nothing), `/readyz` for readiness (checks dependencies; `503` only when PostgreSQL is down) ([health](../operations/observability.md#health))

```yaml
livenessProbe:
  httpGet: { path: /healthz, port: 8000 }
readinessProbe:
  httpGet: { path: /readyz, port: 8000 }
  initialDelaySeconds: 10
```

- **`SEED_ON_STARTUP` is refused automatically** once `ENVIRONMENT` is `staging` or `production`, so demo data cannot reach a real deployment ([the environment refusal](../operations/bootstrap.md#3-an-environment-refusal))

## Behind a reverse proxy

**Streaming is the only route that needs care.** Buffering must be off, or frames are held until the response ends ([streaming: behind a proxy](../api/streaming.md#behind-a-proxy)):

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
- **Count your proxies into `TRUSTED_PROXY_HOPS`:** the client IP recorded in the audit log, refresh sessions and a key's `last_used_ip` is read that many entries from the right of `X-Forwarded-For` ([`app/api/deps.py`](../../backend/app/api/deps.py) `client_ip`)
  - the [rate limit](../api/overview.md#rate-limiting) does not use it: it is counted per principal and path, so a spoofed address buys no fresh bucket
  - **`0` is not yet safe for an API exposed directly:** [`app/server.py`](../../backend/app/server.py) starts uvicorn with `proxy_headers=True` and `forwarded_allow_ips="*"`, which replaces the socket peer with the **leftmost**, client-supplied `X-Forwarded-For` entry before `client_ip` sees it. Keep a proxy in front that sets the header itself

## Retention

```bash
RETENTION_STANDARD_DAYS=30
RETENTION_HIGH_PII_DAYS=7
```

- **High-PII runs get the shorter deadline:** a run takes the highest `pii_risk` of any engine it touched, and a `google_maps_contributor_reviews` payload is one named person's review history ([volatility and PII](../architecture/catalog.md#volatility-and-pii) · [threat model](../security/threat-model.md#personal-data-in-cached-payloads))
- **A run's `expires_at` uses these two global settings only** (`_retention_deadline` in [`app/services/executor/service.py`](../../backend/app/services/executor/service.py))
  - projects carry `retention_days` / `retention_high_pii_days` columns, which the console's Budgets page and the project update set (1 to 3650 and 1 to 365 days, [`app/schemas/identity.py`](../../backend/app/schemas/identity.py) `ProjectUpdate`), but nothing reads them: a per-project value has no effect, and nothing caps it at the global default
- **Nothing enforces `expires_at` yet.** It is recorded on the run and returned by the API, but no job, consumer or query deletes expired runs, steps or their payloads, and nothing deletes objects from the payload store
  - the Budgets page hint, "Days before ordinary run payloads are deleted", describes behaviour that does not exist
  - **until it does, enforce retention yourself**, with a scheduled job that deletes expired runs, or a lifecycle rule on the bucket ([storage](#storage))
  - payloads are content-addressed and shared with cache entries, so delete an object only when nothing still references it; a missing payload is served as a cache miss rather than an error ([`app/services/cache/service.py`](../../backend/app/services/cache/service.py))
  - cached SERPs follow their own TTL, filtered at lookup rather than deleted ([adaptive TTL](../architecture/caching.md#adaptive-ttl))
- More: [executor: retention](../architecture/executor.md#retention)

## What is deliberately not here

- **No Kubernetes manifests, no Terraform, no Helm chart**
- Those encode decisions about a specific environment this repository does not know, and a wrong manifest is worse than none
- Documented above instead: the images, the health endpoints, the configuration surface and the scaling properties
- **The orchestration is yours**

## Related

- [Deployment guide](deployment-guide.md): the single-host runbook this page extends
- [Docker](docker.md): the images and health endpoints an orchestrator would run
- [Startup bootstrap](../operations/bootstrap.md): advisory-locked migrations, and why seeding is refused here
- [Secrets](../security/secrets.md): the production checklist and KEK rotation
- [Row-level security](../database/rls.md): why the application role must not own the tables
- [Threat model](../security/threat-model.md): what each check in the first table defends
- [Observability](../operations/observability.md): the metrics, alerts and traces to wire up
- [Kafka operations](../operations/kafka.md): consumers, topics and the multi-broker topology

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Deployment guide](../deployment/deployment-guide.md) | [Docs index](../README.md) · [Deployment index](../deployment/README.md) | [Architecture index](../architecture/README.md) |
