"""OpenTelemetry wiring (section 63).

The trace tree the spec asks for::

    serpflow.plan
    |- serpflow.catalog.retrieve
    |- serpflow.plan.select
    |- serpflow.plan.pathfind
    |- serpflow.plan.candidates
    |- serpflow.plan.marginal_cost
    `- serpflow.execute
       `- serpflow.execute.step
          `- serpflow.upstream.call

Telemetry is optional: with ``OTEL_ENABLED=false`` every span becomes a cheap
no-op so the code paths stay identical in development.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, Status, StatusCode

from app.core.config import settings

SPAN_PLAN = "serpflow.plan"
SPAN_CATALOG_RETRIEVE = "serpflow.catalog.retrieve"
SPAN_PLAN_SELECT = "serpflow.plan.select"
SPAN_PLAN_SYNTHESIZE = "serpflow.plan.synthesize"
SPAN_PLAN_PATHFIND = "serpflow.plan.pathfind"
SPAN_PLAN_CANDIDATES = "serpflow.plan.candidates"
SPAN_PLAN_MARGINAL_COST = "serpflow.plan.marginal_cost"
SPAN_EXECUTE = "serpflow.execute"
SPAN_EXECUTE_STEP = "serpflow.execute.step"
SPAN_UPSTREAM_CALL = "serpflow.upstream.call"
SPAN_CACHE_LOOKUP = "serpflow.cache.lookup"

_initialised = False


def setup_telemetry(app: Any = None) -> None:
    global _initialised
    if _initialised:
        return
    _initialised = True
    if not settings.otel_enabled:
        return

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint + "/v1/traces")
            )
        )
    elif settings.debug:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    if app is not None:
        # Instrumentation is best effort: a missing optional package must not
        # stop the service from booting.
        with contextlib.suppress(Exception):  # pragma: no cover
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")


def get_tracer(name: str = "serpflow") -> trace.Tracer:
    return trace.get_tracer(name)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    """Start a span, attaching non-null attributes. No-op when OTel is off."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                value = [str(v) for v in value]
            elif not isinstance(value, (str, int, float, bool)):
                value = str(value)
            current.set_attribute(key, value)
        try:
            yield current
        except Exception as exc:
            current.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
            current.record_exception(exc)
            raise


def set_attributes(**attributes: Any) -> None:
    current = trace.get_current_span()
    if current is None:
        return
    for key, value in attributes.items():
        if value is None:
            continue
        if not isinstance(value, (str, int, float, bool)):
            value = str(value)
        current.set_attribute(key, value)


def current_trace_id() -> str | None:
    current = trace.get_current_span()
    if current is None:
        return None
    ctx = current.get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


__all__ = [
    "SPAN_CACHE_LOOKUP",
    "SPAN_CATALOG_RETRIEVE",
    "SPAN_EXECUTE",
    "SPAN_EXECUTE_STEP",
    "SPAN_PLAN",
    "SPAN_PLAN_CANDIDATES",
    "SPAN_PLAN_MARGINAL_COST",
    "SPAN_PLAN_PATHFIND",
    "SPAN_PLAN_SELECT",
    "SPAN_PLAN_SYNTHESIZE",
    "SPAN_UPSTREAM_CALL",
    "current_trace_id",
    "get_tracer",
    "set_attributes",
    "setup_telemetry",
    "span",
]
