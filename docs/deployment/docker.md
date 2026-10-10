# Docker

<p>
  <a href="../README.md#deployment"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="services: 8" src="https://img.shields.io/badge/services-8-2496ED">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="nginx: 1.27" src="https://img.shields.io/badge/nginx-1.27-009639?logo=nginx&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Redis: 7" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="Kafka: 4.0 KRaft" src="https://img.shields.io/badge/Kafka-4.0%20KRaft-231F20?logo=apachekafka&logoColor=white">
  <a href="../../backend/Dockerfile"><img alt="source: backend/Dockerfile" src="https://img.shields.io/badge/source-backend%2FDockerfile-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../README.md#deployment) › **Docker** · page 7 of 50

The whole stack runs in containers, from one compose file:

| You run | You get |
| --- | --- |
| `make up` | **dependencies only:** postgres, redis, kafka. What local dev needs |
| `make docker-up` / `docker compose up` | the **full application**, built from source |
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

| Service | Port | Image |
| --- | --- | --- |
| postgres | 5432 | `pgvector/pgvector:pg17` |
| redis | 6379 | `redis:7-alpine` |
| kafka | 9092 | `apache/kafka:4.0.0` |
| backend | 8000 | built from `backend/Dockerfile` |
| frontend | 5173 | built from `frontend/Dockerfile`, nginx on 80 |
| minio | 9000 / 9001 | `storage` profile |
| prometheus | 9090 | `observability` profile |
| grafana | 3001 | `observability` profile |

- **Every port is overridable** through `.env` (`POSTGRES_PORT`, `BACKEND_PORT`, and so on)
  - a machine already running PostgreSQL on 5432 should not have to stop it
- **Services restart `unless-stopped`.** Containers come back on their own when Docker restarts. Use `make docker-down` to stop them for good

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
- **It runs as a non-root user** (uid 1001); only `/app/.serpflow-objects` and `/app/logs` are writable
- **It is self-bootstrapping:** the app itself migrates and seeds on startup
  - `RUN_MIGRATIONS_ON_STARTUP` and `SEED_ON_STARTUP` are both on in compose
  - both take a **PostgreSQL advisory lock**, so two replicas starting together cannot race
  - a shell `alembic upgrade head &&` in front of the server could not do that
  - schema changes still go only through Alembic. Details: [bootstrap](../operations/bootstrap.md)
- **It starts `app.server`, not uvicorn directly:** that module passes an explicit asyncio `loop_factory`. See [local development](local.md#troubleshooting)
- **It bundles the fixtures:** the startup seed loads the benchmark suite, and replay mode reads cassettes
- **Runtime packages:** `libpq5` and `curl` only. `curl` is there for the healthcheck

## The frontend image

- **Vite builds the bundle; nginx serves it** and proxies the API, so the browser talks to a single origin
- **Proxied to the backend:** `/v1`, `/healthz`, `/readyz`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`
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

- Without `proxy_buffering off`, frames are held until the response ends, and the pipeline animation arrives all at once at the end
- **`VITE_API_BASE_URL` is a build argument**, not a runtime variable: Vite inlines it at build time

### Known issue: `/docs` deep links

- **Symptom:** in the container deployment, opening or refreshing an in-app docs URL such as `http://localhost:5173/docs/readme` returns a JSON `404` from the API
- **Cause:** the proxy rule `location ~ ^/(v1|healthz|readyz|metrics|docs|redoc|openapi.json)` matches **every** path that starts with `/docs`, so the SPA's `/docs/*` routes reach the backend
  - bare `/docs` shows the backend's Swagger UI instead of the docs browser
  - clicking through inside the app still works, because client-side navigation makes no request
- **Not caught by `make test-ui`:** that runs against `vite preview`, not nginx
- **Fix:** drop `docs` from that rule and anchor it, for example `^/(v1|healthz|readyz|metrics|redoc|openapi\.json)(/|$)`. Swagger stays reachable on the API port at `:8000/docs`

## Service configuration

### PostgreSQL

- `pgvector/pgvector:pg17` already carries the `vector` extension
- `docker/postgres/init/` creates `vector`, `pg_trgm` and `btree_gin` at first boot, so migrations do not need superuser
- **`POSTGRES_INITDB_ARGS: --data-checksums`** costs a little write throughput, and turns silent corruption into a loud error

### Redis

- `docker/redis/redis.conf` sets an **LRU eviction policy with a memory cap**
- Redis holds the hot cache layer and the resolved-principal cache: both reconstructible, neither a source of truth
- So eviction under pressure is **correct behaviour**, not data loss

### Kafka

- **Kafka 4.x in KRaft mode.** There is no ZooKeeper service, and there will not be one: ZooKeeper is removed in Kafka 4

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
  - the failure is hard to diagnose: connect succeeds, metadata returns an unreachable address, the producer hangs
- **Topics are created explicitly** by `make kafka-topics` rather than by auto-creation, so partition counts are intentional

## Healthchecks and ordering

- **`depends_on` waits for `service_healthy`** on PostgreSQL and Redis, so the backend never starts against a database that is still initialising
- **Kafka uses `service_started`:** the backend degrades rather than failing when the broker is not ready
  - waiting 30 seconds for a quorum to serve a cached search would be the wrong trade
- **`/healthz`** (the backend's own healthcheck) touches no dependency
- **`/readyz`** checks PostgreSQL, Redis, Kafka, object storage and the catalog, and returns `503` **only** when PostgreSQL is unreachable

## Volumes

```
postgres-data  redis-data  kafka-data  minio-data
object-data        filesystem payload store
prometheus-data  grafana-data
```

- `make docker-down` runs `compose down -v` and **drops all of them**
- `make down` stops the containers and **keeps** them

## Building

```bash
make docker-build                      # both images
docker compose build backend           # one
docker compose build --no-cache backend
```

- Images carry OCI labels, including `org.opencontainers.image.licenses="Apache-2.0"`
- **Memory:** the full stack plus the Docker Desktop VM wants several GB. On a 16 GB laptop, close heavy apps before also running a headless browser or a large build

## Related

- [Local development](local.md)
- [Production](production.md)
- [Bootstrap](../operations/bootstrap.md)
- [Kafka operations](../operations/kafka.md)
- [Redis operations](../operations/redis.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Local development](../deployment/local.md) | [Docs index](../README.md) | [Deployment guide](../deployment/deployment-guide.md) |
