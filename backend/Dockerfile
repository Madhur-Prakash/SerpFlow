# SerpFlow backend.
#
# Two stages: uv resolves and installs into a venv, then a slim runtime image
# copies only that venv plus the application. No build toolchain ships to
# production.

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first: it only rebuilds when pyproject.toml changes.
COPY pyproject.toml README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv --python 3.13 && \
    VIRTUAL_ENV=/opt/venv uv pip install --python /opt/venv -r pyproject.toml

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
# The committed benchmark fixtures and cassettes. 76 KB, and the image is
# incomplete without them: the startup seed loads the benchmark suite, and
# replay mode reads cassettes. Compose bind-mounts this directory over the
# top for recording, which is why its absence was invisible there.
COPY fixtures ./fixtures
RUN --mount=type=cache,target=/root/.cache/uv \
    VIRTUAL_ENV=/opt/venv uv pip install --python /opt/venv --no-deps -e .


FROM python:3.13-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="SerpFlow" \
      org.opencontainers.image.description="A search control plane for SerpApi with cache-aware marginal-cost replanning." \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/serpflow/serpflow"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 serpflow \
    && useradd --system --uid 1001 --gid serpflow --create-home serpflow

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=serpflow:serpflow /app /app

# Writable paths for the filesystem object store and log files.
RUN mkdir -p /app/.serpflow-objects /app/logs \
    && chown -R serpflow:serpflow /app/.serpflow-objects /app/logs

USER serpflow
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Migrations and seeding are handled inside the application, on startup, so
# this is just the server. Both are opt-in (RUN_MIGRATIONS_ON_STARTUP,
# SEED_ON_STARTUP) and both take a Postgres advisory lock, which a shell
# `alembic upgrade head &&` in front of the server could not do - two replicas
# starting together would race. All schema changes still go through Alembic.
CMD ["python", "-m", "app.server", "--host", "0.0.0.0", "--port", "8000"]
