"""SQLite storage for the RBAC service — plain stdlib ``sqlite3``, no ORM.

The whole database lives in one file. Each request gets its own short-lived
connection (see ``get_db``); the schema is created once at startup by
``init_db``. Because there is no ORM, every query in ``services.py`` is plain,
parameterized SQL that you can read top to bottom.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

# The database is a single file next to this package (created on first run).
DB_PATH = Path(__file__).resolve().parent.parent / "rbac.db"

# The full schema in one place. ``IF NOT EXISTS`` makes startup idempotent.
#   * users / roles      -> the two entities (UUID string ids)
#   * permissions        -> (resource, action) pairs, unique together
#   * user_roles         -> which users have which roles      (many-to-many)
#   * role_permissions   -> which roles grant which permissions (many-to-many)
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS permissions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    resource TEXT NOT NULL,
    action   TEXT NOT NULL,
    UNIQUE (resource, action)
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       TEXT    NOT NULL REFERENCES roles(id)       ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- Index the columns we filter or join on the most.
CREATE INDEX IF NOT EXISTS ix_users_name ON users(name);
CREATE INDEX IF NOT EXISTS ix_roles_name ON roles(name);
CREATE INDEX IF NOT EXISTS ix_permissions_resource_action ON permissions(resource, action);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open one SQLite connection, configured the way every caller wants it."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # Rows behave like dicts, so we can write row["name"] instead of row[0].
    conn.row_factory = sqlite3.Row
    # SQLite leaves foreign keys OFF by default; turn them on so the
    # ``ON DELETE CASCADE`` rules in the schema actually run. This must be set
    # on every connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes. Safe to call repeatedly."""
    conn.executescript(SCHEMA)
    conn.commit()


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, always closed.

    Business functions commit their own writes; this wrapper just rolls back if
    the request raised and releases the connection at the end.
    """
    conn = connect()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
