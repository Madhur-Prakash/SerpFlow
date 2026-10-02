# Docker

The whole stack runs in containers. The same compose file serves three
purposes, selected by profile: dependencies only (the default, for local
development), the full application, and the observability stack.

Files: [`docker-compose.yml`](../../docker-compose.yml),
[`backend/Dockerfile`](../../backend/Dockerfile),
[`frontend/Dockerfile`](../../frontend/Dockerfile),
[`docker/`](../../docker).

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

Every port is overridable through `.env` (`POSTGRES_PORT`, `BACKEND_PORT`, and
so on), because a machine that already runs a PostgreSQL on 5432 should not
have to stop it.

## The backend image

Two stages. `uv` resolves and installs into `/opt/venv`; a slim runtime copies
only that venv plus the application, so no build toolchain ships to production.

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
COPY pyproject.toml README.md ./        # dependency layer first
RUN uv venv /opt/venv --python 3.13 && uv pip install -r pyproject.toml
COPY app ./app
...

FROM python:3.13-slim-bookworm AS runtime
COPY --from=builder /opt/venv /opt/venv
USER serpflow
```

Four things worth noting:

- **Dependencies are a separate layer.** `pyproject.toml` is copied before the
  source, so editing a handler does not reinstall SQLAlchemy.
- **It runs as a non-root user** (uid 1001), with only
  `/app/.serpflow-objects` and `/app/logs` writable.
- **Migrations run before the server.** The command is
  `alembic upgrade head && exec python -m app.server`, so a fresh database is
  usable the moment the container is up, and schema changes still go only
  through Alembic.
- **It starts `app.server`, not uvicorn directly.** That module exists to pass
  an explicit asyncio `loop_factory`; see
  [local development](local.md#troubleshooting).

Runtime packages are `libpq5` and `curl` only. `curl` is there for the
healthcheck.

## The frontend image

Vite builds the bundle; nginx serves it and proxies `/v1` to the backend, so
the browser talks to a single origin.

That matters more than it looks for SSE. `EventSource` has no header API, and a
cross-origin long-lived stream adds a CORS preflight to a connection that is
meant to stay open. Same-origin removes the problem rather than configuring
around it.

`nginx.conf` disables buffering on the stream route specifically:

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

Without `proxy_buffering off`, frames are held until the response ends and the
pipeline animation arrives all at once at the end, which defeats the point.

`VITE_API_BASE_URL` is a build argument, not a runtime variable, because Vite
inlines it at build time.

## Service configuration

### PostgreSQL

`pgvector/pgvector:pg17` already carries the `vector` extension;
`docker/postgres/init/` creates `vector`, `pg_trgm` and `btree_gin` at first
boot so migrations do not have to be superuser.

`POSTGRES_INITDB_ARGS: --data-checksums` is set. It costs a little write
throughput and turns silent corruption into a loud error.

### Redis

`docker/redis/redis.conf` configures an LRU eviction policy with a memory cap.
Redis holds the hot cache layer and the resolved principal cache - both
reconstructible, neither a source of truth - so eviction under pressure is
correct behaviour rather than data loss.

### Kafka

Kafka 4.x in **KRaft mode**. There is no ZooKeeper service and there will not
be one: ZooKeeper is removed in Kafka 4.

```yaml
KAFKA_PROCESS_ROLES: broker,controller
KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,INTERNAL://0.0.0.0:19092
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092,INTERNAL://kafka:19092
```

Two client listeners, deliberately. `PLAINTEXT` advertises `localhost:9092` for
a process on the host; `INTERNAL` advertises `kafka:19092` for containers on
the compose network. A single listener cannot advertise an address that is
correct from both sides, and the resulting failure - connect succeeds, metadata
returns an unreachable address, producer hangs - is one of the more annoying
ones to diagnose.

Topics are created explicitly by `make kafka-topics` rather than relying on
auto-creation, so partition counts are intentional.

## Healthchecks and ordering

`depends_on` uses `condition: service_healthy` for PostgreSQL and Redis, so the
backend does not start against a database that is still initialising. Kafka
uses `service_started`, because the backend degrades rather than failing when
the broker is not ready, and waiting 30 seconds for a quorum to serve a
cached search would be the wrong trade.

The backend's own healthcheck hits `/healthz`, which touches no dependency.
`/readyz` is the one that checks PostgreSQL, Redis, Kafka, object storage and
the catalog, and it returns 503 only when PostgreSQL is unreachable.

## Volumes

```
postgres-data  redis-data  kafka-data  minio-data
object-data        filesystem payload store
prometheus-data  grafana-data
```

`make docker-down` runs `compose down -v` and drops all of them. `make down`
stops the containers and keeps them.

## Building

```bash
make docker-build                      # both images
docker compose build backend           # one
docker compose build --no-cache backend
```

Images carry OCI labels including `org.opencontainers.image.licenses="Apache-2.0"`.

## Related

- [Local development](local.md)
- [Production](production.md)
- [Kafka operations](../operations/kafka.md)
- [Redis operations](../operations/redis.md)
