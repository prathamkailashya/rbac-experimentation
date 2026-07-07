"""In-memory storage: just two dicts keyed by id (no database)."""

from advanced.app.models import Role, User


class InMemoryStore:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.roles: dict[str, Role] = {}
