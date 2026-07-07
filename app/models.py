"""Domain models for the extended RBAC service.

Same shape as the original submission, plus ``created_at`` / ``updated_at``
timestamps (a common interview follow-up). Models are still plain dataclasses,
separate from the Pydantic wire schemas.
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
    permissions: set[Permission] = field(default_factory=set)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class User:
    id: str
    name: str
    role_ids: set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
