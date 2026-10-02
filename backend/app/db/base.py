"""Declarative base, prefixed ULID identifiers, and shared column types."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def ulid() -> str:
    """Lexicographically sortable 26-character identifier."""
    timestamp = int(time.time() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    return _encode_crockford(timestamp, 10) + _encode_crockford(randomness, 16)


def prefixed_id(prefix: str) -> str:
    return prefix + "_" + ulid()


def new_id(prefix: str):
    """Default factory for a prefixed primary key column."""

    def _factory() -> str:
        return prefixed_id(prefix)

    return _factory


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = metadata

    type_annotation_map: dict[Any, Any] = {}

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        skip = exclude or set()
        out: dict[str, Any] = {}
        for column in self.__table__.columns:
            if column.name in skip:
                continue
            value = getattr(self, column.name)
            out[column.name] = value.isoformat() if isinstance(value, datetime) else value
        return out

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        pk = getattr(self, "id", None)
        return "<" + type(self).__name__ + " " + str(pk) + ">"


class TimestampMixin:
    @declared_attr
    def created_at(cls) -> Mapped[datetime]:  # noqa: N805
        return mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
            index=True,
        )

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:  # noqa: N805
        return mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )


class OrgScopedMixin:
    """Every tenant-scoped table carries org_id, indexed, and is additionally
    protected by PostgreSQL RLS (section 36)."""

    @declared_attr
    def org_id(cls) -> Mapped[str]:  # noqa: N805
        from sqlalchemy import ForeignKey, String

        return mapped_column(
            String(40),
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


__all__ = [
    "Base",
    "OrgScopedMixin",
    "TimestampMixin",
    "metadata",
    "new_id",
    "prefixed_id",
    "ulid",
    "utcnow",
]
