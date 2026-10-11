# Docker

<p>
  <a href="../deployment/README.md"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="services: 8" src="https://img.shields.io/badge/services-8-2496ED">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="nginx: 1.27" src="https://img.shields.io/badge/nginx-1.27-009639?logo=nginx&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka: 4.0 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <a href="../../backend/Dockerfile"><img alt="source: backend/Dockerfile" src="https://img.shields.io/badge/source-backend%2FDockerfile-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 11 min" src="https://img.shields.io/badge/read-11%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../deployment/README.md) › **Docker** · page 10 of 57

The whole stack runs in containers, from one compose file:

| You run | You get |
| --- | --- |
| `make up` | **dependencies only:** postgres, redis, kafka. What [local dev](local.md#what-is-running) needs |
| `make docker-up` / `docker compose up` | the **full application**, built from source ([installation: path B](installation.md#path-b-everything-in-docker)) |
| `--profile storage` | adds **MinIO** |
| `--profile observability` | adds **Prometheus and Grafana** |
| `--profile full` | everything |

Files: [`docker-compose.yml`](../../docker-compose.yml) · [`backend/Dockerfile`](../../backend/Dockerfile) · [`frontend/Dockerfile`](../../frontend/Dockerfile) · [`docker/`](../../docker)

## Running

```bash
make up            # postgres, redis, kafka only - what local dev needs
make docker-up     # the full stack, built from source
make docker-down   # stop everything and drop the volumes
```

```bash
docker compose --profile storage up -d        # add MinIO
docker compose --profile observability up -d  # add Prometheus and Grafana
docker compose --profile full up -d           # everything
```

- **Without service names, `--profile ... up -d` also starts the five default services**, building the backend and frontend images. Alongside `make dev`, name the services instead (`... up -d minio`): [local development](local.md#what-is-running)

| Service | Port | Image |
| --- | --- | --- |
| postgres | 5432 | `pgvector/pgvector:pg17` |
| redis | 6379 | `redis:7-alpine` |
| kafka | 9092 | `apache/kafka:4.0.0` |
| backend | 8000 | built from `backend/Dockerfile` |
| frontend | 5173 | built from `frontend/Dockerfile`, nginx on 80 |
| minio | 9000 / 9001 | `minio/minio:latest`, `storage` and `full` profiles |
| prometheus | 9090 | `prom/prometheus:latest`, `observability` and `full` profiles; scrapes `backend:8000/metrics` |
| grafana | 3001 (container 3000) | `grafana/grafana:latest`, `observability` and `full` profiles; `GRAFANA_USER` / `GRAFANA_PASSWORD`, default `admin` / `admin` |

- **Eight services in all:** five start by default, three sit behind profiles. `make up` starts three of the five; `make docker-up` all five
- **Every port is overridable** through `.env` (`POSTGRES_PORT`, `REDIS_PORT`, `KAFKA_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`, `MINIO_PORT`, `MINIO_CONSOLE_PORT`, `PROMETHEUS_PORT`, `GRAFANA_PORT`): [secrets: inventory](../security/secrets.md#inventory)
  - a machine already running PostgreSQL on 5432 should not have to stop it
  - **except Kafka, in practice:** `KAFKA_PORT` moves the host port, but the broker still advertises `localhost:9092`, so a host client bootstraps and then dials the wrong port. See [Kafka](#kafka)
  - a host process (`make dev`) also needs its `DATABASE_URL` / `REDIS_URL` changed to the new port; the containers talk over the compose network and do not
- **Services restart `unless-stopped`.** Containers come back on their own when Docker restarts. Use `make docker-down` to stop them for good
- **On a server, unpublish the datastore ports:** compose publishes them on every interface, and `ufw` does not filter Docker's rules. See [deployment guide: lock down the ports](deployment-guide.md#5-lock-down-the-ports)

**How the backend container is configured:**

- **`env_file: .env`** supplies every setting, then compose's `environment:` **overrides** these with container addresses:

```yaml
DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-serpflow}:${POSTGRES_PASSWORD:-serpflow}@postgres:5432/${POSTGRES_DB:-serpflow}
REDIS_URL: redis://redis:6379/0
KAFKA_BOOTSTRAP_SERVERS: kafka:19092
S3_ENDPOINT_URL: ${S3_ENDPOINT_URL:-}
RUN_MIGRATIONS_ON_STARTUP: ${RUN_MIGRATIONS_ON_STARTUP:-true}
SEED_ON_STARTUP: ${SEED_ON_STARTUP:-true}
```

- So **`DATABASE_URL` in `.env` has no effect in the container**: change `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` instead
- **`S3_ENDPOINT_URL` is passed through from `.env`**, whose example value `http://localhost:9000` points at the backend container itself. With `STORAGE_BACKEND=s3` and the bundled MinIO, set it to `http://minio:9000`

## The backend image

**Two stages:** `uv` resolves and installs into `/opt/venv`; a slim runtime copies only that venv plus the application. No build toolchain ships to production.

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
COPY pyproject.toml README.md ./        # dependency layer first
RUN uv venv /opt/venv --python 3.13 && uv pip install -r pyproject.toml
COPY app ./app
...

FROM python:3.13-slim-bookworm AS runtime
COPY --from=builder /opt/venv /opt/venv
USER serpflow
CMD ["python", "-m", "app.server", "--host", "0.0.0.0", "--port", "8000"]
```

- **Dependencies are a separate layer:** `pyproject.toml` is copied before the source, so editing a handler does not reinstall SQLAlchemy
- **It runs as a non-root user**, `serpflow` (uid 1001)
  - `/opt/venv` is copied without `--chown`, so it stays root-owned and the app cannot modify its own dependencies
  - `/app` is copied with `--chown=serpflow:serpflow`, so the application tree is owned by that user; `/app/.serpflow-objects` and `/app/logs` are created for the object store and log file
- **It is self-bootstrapping:** the app itself migrates and seeds on startup
  - `RUN_MIGRATIONS_ON_STARTUP` and `SEED_ON_STARTUP` are both on in compose (the code default is off)
  - both take a **PostgreSQL advisory lock**, so two replicas starting together cannot race
  - a shell `alembic upgrade head &&` in front of the server could not do that
  - schema changes still go only through Alembic. Details: [bootstrap](../operations/bootstrap.md) · [migrations](../database/migrations.md)
- **It starts `app.server`, not uvicorn directly:** that module passes an explicit asyncio `loop_factory`. See [async on Windows](../architecture/backend.md#async-on-windows)
- **It bundles `fixtures/`:** the benchmark tasks and results, because the startup seed loads the benchmark suite
  - no cassettes are committed, so `fixtures/cassettes/` starts empty and `replay` with a live key misses until something is recorded
  - compose bind-mounts `./backend/fixtures` over `/app/fixtures`, so cassettes recorded in the container land on the host
- **Runtime packages:** `libpq5` and `curl` only. `curl` serves the image's own `HEALTHCHECK`; compose replaces it with a Python `urllib` probe of `/healthz` (every 10 s, 12 retries, 20 s start period)

## The frontend image

- **Vite builds the bundle** (`node:22-alpine`, `npm ci`); **nginx serves it** (`nginx:1.27-alpine`) and proxies the API, so the browser can talk to a single origin
- **Proxied to the backend** by [`frontend/nginx.conf`](../../frontend/nginx.conf): `/v1`, `/healthz`, `/readyz`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`
  - `/metrics` is proxied too, so whatever serves this origin publicly serves the Prometheus metrics: [deployment guide: TLS](deployment-guide.md#9-put-tls-in-front) blocks it
- **Everything else** falls through to `index.html` for client-side routing; `/assets/` is cached for a year as immutable; `X-Content-Type-Options`, `X-Frame-Options: DENY` and `Referrer-Policy` are added to the static responses
- **Why same-origin matters for SSE:**
  - `EventSource` has no header API
  - a cross-origin long-lived stream adds a CORS preflight to a connection meant to stay open
  - same-origin removes the problem instead of configuring around it
- **`nginx.conf` disables buffering on the stream route specifically:**

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

- Without `proxy_buffering off`, frames are held until the response ends, and the pipeline animation arrives all at once at the end ([troubleshooting](../operations/troubleshooting.md#the-stream-arrives-all-at-once-at-the-end) · [streaming: behind a proxy](../api/streaming.md#behind-a-proxy))
- **`VITE_API_BASE_URL` is a build argument**, not a runtime variable: Vite inlines it at build time
  - **REST calls use it** as their prefix ([`src/lib/api.ts`](../../frontend/src/lib/api.ts)); **the SSE stream does not**, it always opens a relative `/v1/runs/{id}/stream` ([`src/hooks/useRunStream.ts`](../../frontend/src/hooks/useRunStream.ts)), so it always goes through nginx
  - **compose defaults it to `http://localhost:8000`**, so in the laptop stack REST goes cross-origin to the API port (allowed by `CORS_ORIGINS`) and only the stream uses the nginx proxy
  - **an empty value does not restore same-origin:** `${VITE_API_BASE_URL:-...}` substitutes the default for empty too. On a server, set it to the public origin ([deployment guide: configure](deployment-guide.md#4-configure-the-environment) · [troubleshooting](../operations/troubleshooting.md#the-production-frontend-calls-localhost8000))

### Known issue: `/docs` deep links

- **Symptom:** in the container deployment, opening or refreshing an in-app docs URL such as `http://localhost:5173/docs/readme` returns a JSON `404` from the API
- **Cause:** the proxy rule `location ~ ^/(v1|healthz|readyz|metrics|docs|redoc|openapi.json)` matches **every** path that starts with `/docs`, so the SPA's `/docs/*` routes reach the backend
  - bare `/docs` shows the backend's Swagger UI instead of the docs browser
  - clicking through inside the app still works, because client-side navigation makes no request
- **Not caught by `make test-ui`:** that runs against `vite preview`, not nginx ([verifying the web surface](../architecture/web.md#verifying-it))
- **Fix:** drop `docs` from that rule and anchor it, for example `^/(v1|healthz|readyz|metrics|redoc|openapi\.json)(/|$)`. Swagger stays reachable on the API port at `:8000/docs`
  - the one-line `sed` that applies it: [deployment guide, step 6](deployment-guide.md#6-fix-the-docs-proxy-rule) · symptom entry: [troubleshooting](../operations/troubleshooting.md#docs-returns-a-json-404-in-the-container-deployment)

## Service configuration

### PostgreSQL

- `pgvector/pgvector:pg17` already carries the `vector` extension
- [`docker/postgres/init/01-extensions.sql`](../../docker/postgres/init/01-extensions.sql) creates `vector`, `pg_trgm` and `btree_gin` at first boot, so migrations do not need superuser ([troubleshooting: `type "vector" does not exist`](../operations/troubleshooting.md#type-vector-does-not-exist))
- **It also sets the database default of `app.current_org` to `''`**, the empty value every [row-level security](../database/rls.md) policy reads when no tenant is set ([the empty-value clause](../database/rls.md#the-empty-value-clause))
  - the script names the database `serpflow` literally, so keep `POSTGRES_DB=serpflow` or edit the script; `make psql` assumes `-U serpflow -d serpflow` as well
- **Init scripts run only on an empty volume.** Changing them, or `POSTGRES_PASSWORD`, later needs a fresh `postgres-data` volume or a manual `ALTER`
- **`POSTGRES_INITDB_ARGS: --data-checksums`** costs a little write throughput, and turns silent corruption into a loud error

### Redis

- [`docker/redis/redis.conf`](../../docker/redis/redis.conf) sets **`maxmemory 512mb` with `allkeys-lru`**, and AOF persistence (`appendonly yes`, `everysec`) so a restart does not start the cache cold
- Redis holds the hot cache layer, the resolved-principal cache, rate-limit counters and SSE frame buffers ([what lives in it](../operations/redis.md#what-lives-in-it)): all reconstructible, none a source of truth
- So eviction under pressure is **correct behaviour**, not data loss ([troubleshooting: Redis evicting too much](../operations/troubleshooting.md#redis-evicting-too-much))

### Kafka

- **Kafka 4.x in KRaft mode.** There is no ZooKeeper service, and there will not be one: ZooKeeper is removed in Kafka 4
- Kafka carries **background work only**; interactive search never touches it

```yaml
KAFKA_PROCESS_ROLES: broker,controller
KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,INTERNAL://0.0.0.0:19092
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092,INTERNAL://kafka:19092
```

- **Two client listeners, deliberately:**
  - `PLAINTEXT` advertises `localhost:9092`, for a process on the host
  - `INTERNAL` advertises `kafka:19092`, for containers on the compose network
- A single listener cannot advertise an address that is correct from both sides
  - the failure is hard to diagnose: connect succeeds, metadata returns an unreachable address, the producer hangs ([troubleshooting](../operations/troubleshooting.md#producer-hangs-with-no-error) · [Kafka: listeners](../operations/kafka.md#listeners))
  - the same failure follows from changing `KAFKA_PORT` alone: `PLAINTEXT` still advertises `localhost:9092`. Edit `KAFKA_ADVERTISED_LISTENERS` in the compose file to match, or leave the port
- **Topics:** compose leaves auto-creation on (`KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"`, `KAFKA_NUM_PARTITIONS: 3`), so a first publish creates its topic
  - `make kafka-topics`, and `make worker` on start, create all 8 topics up front with 3 partitions and replication factor 1 ([`app/workers/kafka.py`](../../backend/app/workers/kafka.py) `ensure_topics`; [topics](../operations/kafka.md#topics))
- **Single node, replication factor 1:** a development topology. Production needs more ([production: Kafka](production.md#kafka))

## Healthchecks and ordering

- **`depends_on` waits for `service_healthy`** on PostgreSQL and Redis, so the backend never starts against a database that is still initialising
- **Kafka uses `service_started`:** the backend degrades rather than failing when the broker is not ready
  - waiting 30 seconds for a quorum to serve a cached search would be the wrong trade ([Kafka: degradation](../operations/kafka.md#degradation))
- **The frontend waits only for the backend to start**, not to be healthy: nginx serves the bundle either way
- **Healthchecks:** `pg_isready` (postgres), `redis-cli ping` (redis), `kafka-broker-api-versions.sh` with a 30 s start period (kafka), `mc ready local` (minio), `/healthz` (backend), and the frontend image's own `wget` of `/`. Prometheus and Grafana have none
- **`/healthz`** (the backend's own healthcheck) touches no dependency
- **`/readyz`** checks PostgreSQL, Redis, Kafka, object storage and the catalog, and returns `503` **only** when PostgreSQL is unreachable ([observability: health](../operations/observability.md#health) · [`app/main.py`](../../backend/app/main.py))

## Volumes

```
postgres-data  redis-data  kafka-data  minio-data
object-data        filesystem payload store
prometheus-data  grafana-data
```

- `make docker-down` runs `compose down -v` and **drops all of them**
- `make down` stops the containers and **keeps** them
- **Volume names are prefixed with the project name**, `serpflow` (`name: serpflow` in the compose file): `serpflow_postgres-data`, `serpflow_object-data`, and so on. The [backup commands](deployment-guide.md#13-backups) use those names

## Building

```bash
make docker-build                      # both images
docker compose build backend           # one
docker compose build --no-cache backend
```

- Images carry OCI labels, including `org.opencontainers.image.licenses="Apache-2.0"` and, on the backend, `org.opencontainers.image.source="https://github.com/Madhur-Prakash/SerpFlow"`
- **Memory:** the full stack plus the Docker Desktop VM wants several GB. On a 16 GB laptop, close heavy apps before also running a headless browser or a large build ([troubleshooting: Docker Desktop quits mid-run](../operations/troubleshooting.md#docker-desktop-quits-mid-run))

## Related

- [Local development](local.md): what `make up` is for, and every `make` target
- [Installation](installation.md): path B, the whole stack in Docker, step by step
- [Deployment guide](deployment-guide.md): this compose file on a server, with ports locked down and TLS in front
- [Production](production.md): what changes past a single host
- [Startup bootstrap](../operations/bootstrap.md): the migrations and seeding the backend container runs on start
- [Kafka operations](../operations/kafka.md): the two listeners, topics and consumers
- [Redis operations](../operations/redis.md): why eviction is safe
- [Troubleshooting: deployment](../operations/troubleshooting.md#deployment): the `/docs` proxy rule, `localhost:8000` in the bundle, and open datastore ports

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Local development](../deployment/local.md) | [Docs index](../README.md) · [Deployment index](../deployment/README.md) | [Deployment guide](../deployment/deployment-guide.md) |
