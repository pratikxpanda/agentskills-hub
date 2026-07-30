"""Column types.

SQLite has no timezone-aware datetime type: a `DateTime(timezone=True)` column silently returns a
naive value. `UtcDateTime` stores naive UTC and returns aware UTC, so a timestamp that goes into
the database as UTC comes back comparable to `datetime.now(UTC)`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected; pass an aware datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return cast(datetime, value).replace(tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)
