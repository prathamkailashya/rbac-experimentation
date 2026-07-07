"""Plain data holders for rows read from SQLite.

There is no ORM here: ``services.py`` reads rows and fills in these dataclasses,
and ``routes.py`` turns them into response schemas. Keeping them as dataclasses
means the route mapping helpers look the same as in the in-memory version.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware UTC now. One helper so every timestamp is consistent."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Permission:
    """A capability: an ``action`` on a ``resource`` (frozen -> hashable)."""

    resource: str
    action: str


@dataclass
class Role:
    id: str
    name: str
    permissions: list[Permission] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class User:
    id: str
    name: str
    role_ids: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
