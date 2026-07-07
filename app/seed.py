"""Seed data.

Builds a fresh service pre-populated with the assignment's example scenario so
the API and frontend have something to show immediately after startup.
"""

from app.models import Permission
from app.services import RBACService
from app.storage import InMemoryStore


def build_seeded_service() -> RBACService:
    service = RBACService(InMemoryStore())

    # The four permissions used across the system.
    documents_read = Permission("documents", "read")
    documents_write = Permission("documents", "write")
    users_write = Permission("users", "write")
    settings_read = Permission("settings", "read")

    # Roles and the permissions they grant.
    # admin also gets settings/read so every seeded permission has a home.
    admin = service.create_role("admin", [documents_write, users_write, settings_read])
    editor = service.create_role("editor", [documents_write])
    viewer = service.create_role("viewer", [documents_read])

    # Users mapped to roles.
    service.create_user("Alice", [admin.id])
    service.create_user("Bob", [editor.id])
    service.create_user("Charlie", [viewer.id])

    return service
