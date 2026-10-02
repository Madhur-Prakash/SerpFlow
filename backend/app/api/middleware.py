"""HTTP middleware: request ids, provenance headers, security headers, errors.

Section 45 requires provenance on every response. Section 74 requires a stable
error envelope and no stack traces.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core import metrics
from app.core.config import settings
from app.core.exceptions import SerpFlowError
from app.core.logging import bind, get_logger, redact_text
from app.core.telemetry import current_trace_id

log = get_logger("serpflow.http")

PROVENANCE_HEADERS = (
    "X-SerpFlow-Cache",
    "X-SerpFlow-Matched-Query",
    "X-SerpFlow-Age",
    "X-SerpFlow-TTL-Source",
    "X-SerpFlow-Budget-Remaining",
    "X-SerpFlow-Run-Id",
    "X-SerpFlow-Trace-Id",
    "X-SerpFlow-Mode",
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, binds logging context, records metrics, and
    attaches security and provenance headers."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.provenance = {}
        trace_id = current_trace_id()
        bind(request_id=request_id, trace_id=trace_id)

        started = time.perf_counter()
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)

        try:
            response = await call_next(request)
        except SerpFlowError as exc:
            response = JSONResponse(
                status_code=exc.status_code, content=exc.to_envelope(request_id)
            )
        except Exception as exc:
            # Never expose a stack trace. The request id is the handle an
            # operator uses to find the full record in the logs.
            log.error(
                "unhandled request error",
                extra={
                    "event": "http.unhandled_error",
                    "path": request.url.path,
                    "error": type(exc).__name__,
                },
                exc_info=True,
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred.",
                        "request_id": request_id,
                    }
                },
            )

        elapsed = time.perf_counter() - started
        response.headers["X-Request-Id"] = request_id
        if trace_id:
            response.headers["X-SerpFlow-Trace-Id"] = trace_id
        response.headers["X-SerpFlow-Mode"] = _resolved_mode(request)
        response.headers["X-SerpFlow-Catalog-Version"] = _catalog_version()
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        for key, value in (getattr(request.state, "provenance", None) or {}).items():
            if value is not None:
                response.headers[key] = str(value)[:400]

        if settings.metrics_enabled:
            metrics.api_requests_total.labels(
                method=request.method,
                route=metrics.safe_label(route_path),
                status=str(response.status_code),
            ).inc()
            metrics.api_request_seconds.labels(
                method=request.method, route=metrics.safe_label(route_path)
            ).observe(elapsed)

        if not request.url.path.endswith(("/healthz", "/readyz", "/metrics")):
            log.info(
                "request",
                extra={
                    "event": "http.request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration": round(elapsed * 1000.0, 2),
                },
            )
        return response


def _resolved_mode(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    if principal is not None and getattr(principal, "key_environment", None) == "test":
        return "MOCK"
    return settings.serpflow_mode.upper()


def _catalog_version() -> str:
    try:
        from app.services.catalog.loader import load_catalog

        return load_catalog().version
    except Exception:
        return "unknown"


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Request size limit (section 67)."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_request_body_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": (
                            "Request body exceeds the "
                            + str(settings.max_request_body_bytes)
                            + " byte limit."
                        ),
                        "request_id": getattr(request.state, "request_id", None),
                    }
                },
            )
        return await call_next(request)


def set_provenance(request: Request, **headers: Any) -> None:
    """Attach section 45 provenance headers from inside a route."""
    store = getattr(request.state, "provenance", None)
    if store is None:
        store = {}
        request.state.provenance = store
    mapping = {
        "cache": "X-SerpFlow-Cache",
        "matched_query": "X-SerpFlow-Matched-Query",
        "age": "X-SerpFlow-Age",
        "ttl_source": "X-SerpFlow-TTL-Source",
        "budget_remaining": "X-SerpFlow-Budget-Remaining",
        "run_id": "X-SerpFlow-Run-Id",
        "trace_id": "X-SerpFlow-Trace-Id",
        "mode": "X-SerpFlow-Mode",
    }
    for key, value in headers.items():
        header = mapping.get(key)
        if header and value is not None:
            store[header] = redact_text(str(value)) if isinstance(value, str) else value


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SerpFlowError)
    async def _serpflow_error(request: Request, exc: SerpFlowError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_envelope(getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "The request payload failed validation.",
                    "details": {
                        "fields": [
                            {
                                "location": ".".join(str(p) for p in err.get("loc", [])),
                                "message": err.get("msg", ""),
                            }
                            for err in exc.errors()[:20]
                        ]
                    },
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.exception_handler(404)
    async def _not_found(request: Request, exc: Any) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "The requested resource does not exist.",
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )


__all__ = [
    "PROVENANCE_HEADERS",
    "SECURITY_HEADERS",
    "BodySizeLimitMiddleware",
    "RequestContextMiddleware",
    "register_exception_handlers",
    "set_provenance",
]
