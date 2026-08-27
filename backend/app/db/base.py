"""Declarative base and shared column helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def pk_column() -> Mapped[uuid.UUID]:
    return mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)


def created_column() -> Mapped[datetime]:
    return mapped_column(sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now(), nullable=False)


def updated_column() -> Mapped[datetime]:
    return mapped_column(
        sa.DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=sa.func.now(),
        nullable=False,
    )


def enum_column(name: str, values: tuple[str, ...]) -> sa.Enum:
    """VARCHAR + CHECK constraint. Portable, and changing the value set does
    not require an ALTER TYPE migration."""
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, validate_strings=True)
