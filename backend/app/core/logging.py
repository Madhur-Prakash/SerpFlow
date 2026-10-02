"""Logifyx-backed structured logging with a hard credential redaction filter.

Section 64: passwords, API keys, upstream SerpApi credentials and raw sensitive
payloads must never reach a log sink. The leak path is always an exception
handler, so the filter runs on the record *and* on the formatted message, and
``tests/unit/test_security.py`` asserts it.
"""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
from typing import Any

from logifyx import ContextLoggerAdapter, configure_logging, get_logify_logger

from app.core.config import settings

# --- request-scoped context ----------------------------------------------
_ctx_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_ctx_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_ctx_run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
_ctx_org_id: ContextVar[str | None] = ContextVar("org_id", default=None)
_ctx_project_id: ContextVar[str | None] = ContextVar("project_id", default=None)
_ctx_principal_id: ContextVar[str | None] = ContextVar("principal_id", default=None)

_CONTEXT_VARS = {
    "request_id": _ctx_request_id,
    "trace_id": _ctx_trace_id,
    "run_id": _ctx_run_id,
    "org_id": _ctx_org_id,
    "project_id": _ctx_project_id,
    "principal_id": _ctx_principal_id,
}

REDACTED = "[REDACTED]"

# Secrets we can recognise structurally no matter where they appear.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # SerpFlow API keys: sf_live_abc123_<32 chars>
    re.compile(r"\bsf_(?:live|test)_[A-Za-z0-9]{4,12}_[A-Za-z0-9]{8,}"),
    # SerpApi keys are 64 hex characters.
    re.compile(r"\b[0-9a-f]{64}\b"),
    # Groq / OpenAI style tokens.
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    # JWTs.
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    # key=value / "key": "value" for any sensitive-looking name.
    re.compile(
        r"(?i)\b(api[_-]?key|apikey|serpapi[_-]?key|password|passwd|secret|token|"
        r"authorization|bearer|credential|encrypted_dek|dek|kek|pepper|private[_-]?key)"
        r"(\"?\s*[:=]\s*\"?)([^\s,;}\"']{3,})"
    ),
)

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "serpapi_api_key",
    "serpapi_key",
    "password",
    "password_hash",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "credential",
    "ciphertext",
    "encrypted_dek",
    "dek",
    "kek",
    "pepper",
    "key_hash",
    "raw_payload",
    "payload",
}


def redact_text(value: str) -> str:
    """Scrub secrets out of an arbitrary string."""
    out = value
    for pattern in _PATTERNS:
        if pattern.groups >= 3:
            out = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", out)
        else:
            out = pattern.sub(REDACTED, out)
    return out


def redact_mapping(data: Any, _depth: int = 0) -> Any:
    """Recursively scrub a mapping/sequence destined for a log record."""
    if _depth > 8:
        return data
    if isinstance(data, dict):
        return {
            k: (REDACTED if str(k).lower() in _SENSITIVE_KEYS else redact_mapping(v, _depth + 1))
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return type(data)(redact_mapping(v, _depth + 1) for v in data)
    if isinstance(data, str):
        return redact_text(data)
    return data


class CredentialRedactionFilter(logging.Filter):
    """Scrubs every log record before it reaches any handler."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        elif isinstance(record.msg, (dict, list, tuple)):
            record.msg = redact_mapping(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_mapping(record.args)
            else:
                record.args = tuple(redact_mapping(a) for a in record.args)

        for key, value in list(record.__dict__.items()):
            if key in _SENSITIVE_KEYS:
                record.__dict__[key] = REDACTED
            elif isinstance(value, str) and key not in {"name", "pathname", "funcName"}:
                record.__dict__[key] = redact_text(value)

        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            scrubbed = redact_text(str(exc))
            if scrubbed != str(exc):
                record.exc_info = (
                    record.exc_info[0],
                    type(exc)(scrubbed) if _is_simple_exc(exc) else Exception(scrubbed),
                    record.exc_info[2],
                )
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True


def _is_simple_exc(exc: BaseException) -> bool:
    try:
        type(exc)("probe")
        return True
    except Exception:
        return False


class ContextInjectionFilter(logging.Filter):
    """Attaches the request-scoped identifiers required by section 64."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.service = settings.service_name
        for name, var in _CONTEXT_VARS.items():
            if not hasattr(record, name):
                setattr(record, name, var.get())
        return True


_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    configure_logging(
        level=settings.log_level,
        output=settings.log_output,
        log_file=settings.log_file,
        json_mode=settings.log_json,
        color=not settings.log_json,
        mask=True,
    )
    root = logging.getLogger()
    redaction = CredentialRedactionFilter()
    context = ContextInjectionFilter()
    root.addFilter(redaction)
    root.addFilter(context)
    for handler in root.handlers:
        handler.addFilter(redaction)
        handler.addFilter(context)
    # Library loggers that would otherwise emit at INFO on every request or
    # mapper configuration and bury the application's own events.
    for noisy in (
        "httpx",
        "httpcore",
        "aiokafka",
        "kafka",
        "botocore",
        "boto3",
        "urllib3",
        "asyncio",
        "sqlalchemy",
        "sqlalchemy.engine",
        "sqlalchemy.orm",
        "sqlalchemy.pool",
        "sqlalchemy.dialects",
        "uvicorn.access",
        "multipart",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    logger = get_logify_logger(name)
    redaction = CredentialRedactionFilter()
    if not any(isinstance(f, CredentialRedactionFilter) for f in logger.filters):
        logger.addFilter(redaction)
        logger.addFilter(ContextInjectionFilter())
    for handler in logger.handlers:
        if not any(isinstance(f, CredentialRedactionFilter) for f in handler.filters):
            handler.addFilter(redaction)
    return logger


def bind(**fields: Any) -> None:
    """Bind request-scoped context values for the current task."""
    for key, value in fields.items():
        var = _CONTEXT_VARS.get(key)
        if var is not None:
            var.set(str(value) if value is not None else None)


def current_context() -> dict[str, str | None]:
    return {name: var.get() for name, var in _CONTEXT_VARS.items()}


def context_logger(name: str, **fields: Any) -> ContextLoggerAdapter:
    merged = {k: v for k, v in {**current_context(), **fields}.items() if v is not None}
    return ContextLoggerAdapter(get_logger(name), merged)


__all__ = [
    "CredentialRedactionFilter",
    "REDACTED",
    "bind",
    "context_logger",
    "current_context",
    "get_logger",
    "redact_mapping",
    "redact_text",
    "setup_logging",
]
