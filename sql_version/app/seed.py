"""Seed data for the SQLite version.

Inserts the same example scenario as the in-memory version, but only when the
database is empty, so restarting the server never duplicates rows.
"""

import sqlite3

from . import services
from .models import Permission


def seed_if_empty(conn: sqlite3.Connection) -> None:
    if services.count_roles(conn) > 0:
        return  # already seeded

    # Roles and the permissions they grant.
    admin = services.create_role(
        conn,
        "admin",
        [
            Permission("documents", "write"),
            Permission("users", "write"),
            Permission("settings", "read"),
        ],
    )
    editor = services.create_role(conn, "editor", [Permission("documents", "write")])
    viewer = services.create_role(conn, "viewer", [Permission("documents", "read")])

    # Users mapped to roles.
    services.create_user(conn, "Alice", [admin.id])
    services.create_user(conn, "Bob", [editor.id])
    services.create_user(conn, "Charlie", [viewer.id])
