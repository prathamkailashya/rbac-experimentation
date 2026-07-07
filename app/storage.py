"""In-memory persistence layer (extended).

Still just plain Python containers. Beyond ``users`` and ``roles`` it now holds:
  * ``audit_log``  - an append-only list of what happened (bonus feature);
  * ``permission_cache`` - a per-user cache of effective permissions, which the
    service invalidates on writes (demonstrates a simple cache seam).
"""

from typing import Any

from app.models import Role, User


class InMemoryStore:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.roles: dict[str, Role] = {}
        self.audit_log: list[dict[str, Any]] = []
        self.permission_cache: dict[str, set] = {}
