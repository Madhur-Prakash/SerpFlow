"""SerpFlow API application."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.middleware import (
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    register_exception_handlers,
)
from app.api.v1 import api_router
from app.core import metrics
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.telemetry import setup_telemetry
from app.db.bootstrap import bootstrap
from app.db.session import dispose_engine
from app.db.session import ping as db_ping
from app.schemas.common import HealthResponse
from app.services.cache.redis_client import close_redis
from app.services.cache.redis_client import ping as redis_ping
from app.services.catalog.loader import load_catalog
from app.workers import kafka

log = get_logger("serpflow.main")

VERSION = "0.1.0"

DESCRIPTION = """
SerpFlow is a search control plane for SerpApi.

It accepts a natural-language intent, discovers the correct engine or engine
chain, synthesizes parameters, computes valid dependency paths, generates
multiple candidate plans, inspects current cache state, computes the marginal
cost of each candidate, re-ranks on that marginal cost, executes only the
required live searches, enforces budgets, records provenance, and explains
every routing and cost decision.

The central thesis: SerpFlow does not merely cache search results. It re-plans
execution based on what is already warm, optimizing marginal cost rather than
cold cost.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    setup_telemetry(app)

    # Migrations and seeding, both opt-in by environment variable and both
    # advisory-locked so several replicas starting together cannot race. This
    # runs before anything else touches the database.
    await bootstrap()

    index = load_catalog()
    log.info(
        "serpflow starting",
        extra={
            "event": "app.startup",
            "environment": settings.environment,
            "mode": settings.serpflow_mode,
            "catalog_version": index.version,
            "llm_provider": settings.llm_provider,
            **index.stats(),
        },
    )

    consumer_runner = None
    if settings.kafka_enabled:
        from app.workers.consumers.handlers import HANDLERS
        from app.workers.kafka import KafkaConsumerRunner

        consumer_runner = KafkaConsumerRunner(HANDLERS)
        try:
            await consumer_runner.start()
        except Exception as exc:
            log.warning(
                "kafka consumers unavailable",
                extra={"event": "app.kafka_unavailable", "error": type(exc).__name__},
            )
            consumer_runner = None

    try:
        yield
    finally:
        if consumer_runner is not None:
            await consumer_runner.stop()
        await kafka.stop_producer()
        await close_redis()
        await dispose_engine()
        log.info("serpflow stopped", extra={"event": "app.shutdown"})


app = FastAPI(
    title="SerpFlow",
    description=DESCRIPTION,
    version=VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "SerpFlow", "url": "https://github.com/serpflow/serpflow"},
    license_info={"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"},
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-Id",
        "X-SerpFlow-Cache",
        "X-SerpFlow-Matched-Query",
        "X-SerpFlow-Age",
        "X-SerpFlow-TTL-Source",
        "X-SerpFlow-Budget-Remaining",
        "X-SerpFlow-Run-Id",
        "X-SerpFlow-Trace-Id",
        "X-SerpFlow-Mode",
        "X-SerpFlow-Catalog-Version",
    ],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/healthz", response_model=HealthResponse, tags=["infrastructure"])
async def healthz() -> HealthResponse:
    """Liveness. Answers without touching any dependency."""
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=VERSION,
        environment=settings.environment,
        mode=settings.serpflow_mode,
        catalog_version=load_catalog().version,
        checks={},
        timestamp=datetime.now(UTC),
    )


@app.get("/readyz", response_model=HealthResponse, tags=["infrastructure"])
async def readyz(response: Response) -> HealthResponse:
    """Readiness. Checks every dependency the API actually needs."""
    from app.integrations.storage import get_object_store

    (database, database_detail), redis, kafka_ok, storage = await asyncio.gather(
        db_ping(),
        redis_ping(),
        kafka.ping(),
        get_object_store().health(),
    )
    checks = {
        "postgres": {
            "status": "ok" if database else "error",
            **({"detail": database_detail} if database_detail else {}),
        },
        "redis": {"status": "ok" if redis else "degraded"},
        "kafka": {"status": "ok" if kafka_ok else "degraded"},
        "object_storage": storage,
        "catalog": {"status": "ok", **load_catalog().stats()},
        "llm": {"provider": settings.llm_provider},
    }
    # Postgres is required. Redis and Kafka degrade gracefully by design:
    # Redis is a hot cache, not the source of truth, and Kafka carries only
    # background work.
    status: Literal["ok", "degraded", "error"]
    if not database:
        status = "error"
        response.status_code = 503
    elif not redis or not kafka_ok:
        status = "degraded"
    else:
        status = "ok"

    return HealthResponse(
        status=status,
        service=settings.service_name,
        version=VERSION,
        environment=settings.environment,
        mode=settings.serpflow_mode,
        catalog_version=load_catalog().version,
        checks=checks,
        timestamp=datetime.now(UTC),
    )


@app.get("/metrics", tags=["infrastructure"])
async def prometheus_metrics() -> Response:
    if not settings.metrics_enabled:
        return Response(status_code=404)
    return Response(content=metrics.render(), media_type=metrics.CONTENT_TYPE)


@app.get("/", tags=["infrastructure"])
async def root() -> dict:
    index = load_catalog()
    return {
        "service": "SerpFlow",
        "version": VERSION,
        "description": "A search control plane for SerpApi with cache-aware marginal-cost replanning.",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/healthz",
        "readiness": "/readyz",
        "metrics": "/metrics",
        "api": settings.api_v1_prefix,
        "mode": settings.serpflow_mode,
        "catalog_version": index.version,
        "engines": len(index.engines),
    }


__all__ = ["VERSION", "app"]
