"""Shared response envelopes and primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ErrorBody(APIModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None


class ErrorResponse(APIModel):
    """The canonical error envelope (section 74). Stack traces never appear."""

    error: ErrorBody


class Page[T](APIModel):
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class OkResponse(APIModel):
    ok: bool = True
    message: str = ""


class HealthResponse(APIModel):
    status: Literal["ok", "degraded", "error"]
    service: str
    version: str
    environment: str
    mode: str
    catalog_version: str
    checks: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class ModeInfo(APIModel):
    """The resolved execution mode, surfaced on every response (section 21)."""

    mode: str
    label: str
    reason: str
    credited: bool


__all__ = [
    "APIModel",
    "ErrorBody",
    "ErrorResponse",
    "HealthResponse",
    "ModeInfo",
    "OkResponse",
    "Page",
]
