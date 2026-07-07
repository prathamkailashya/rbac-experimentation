"""Business logic for the SQLite-backed RBAC service.

Only the standard-library ``sqlite3`` is used, so every database call is plain,
parameterized SQL — nothing is hidden behind an ORM. Each function takes an open
``sqlite3.Connection`` and commits its own writes.

Compare this file with the in-memory ``app/services.py``: the *rules* are the
same (validation, normalization, uniqueness, the permission check); only the
storage calls differ.
"""

import sqlite3
from datetime import datetime
from uuid import uuid4

from .errors import ConflictError, NotFoundError, ValidationError
from .models import Permission, Role, User, utcnow


# ---- normalization helpers (same rules as the in-memory version) ---------
def clean_name(name: str) -> str:
    """Trim a name and reject blank / whitespace-only values."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValidationError("Name must not be blank")
    return cleaned


def clean_permission(resource: str, action: str) -> tuple[str, str]:
    """Trim and lowercase a permission so matching is case-insensitive."""
    r = (resource or "").strip().lower()
    a = (action or "").strip().lower()
    if not r or not a:
        raise ValidationError("Permission resource and action must not be blank")
    return r, a


# ---- row -> dataclass helpers -------------------------------------------
def _to_dt(value: str) -> datetime:
    """Parse an ISO-8601 timestamp string read back from SQLite."""
    return datetime.fromisoformat(value)


def _load_role(conn: sqlite3.Connection, row: sqlite3.Row) -> Role:
    """Turn a ``roles`` row into a Role, loading its permissions."""
    permission_rows = conn.execute(
        """
        SELECT p.resource, p.action
        FROM permissions p
        JOIN role_permissions rp ON rp.permission_id = p.id
        WHERE rp.role_id = ?
        ORDER BY p.resource, p.action
        """,
        (row["id"],),
    ).fetchall()
    return Role(
        id=row["id"],
        name=row["name"],
        permissions=[Permission(p["resource"], p["action"]) for p in permission_rows],
        created_at=_to_dt(row["created_at"]),
        updated_at=_to_dt(row["updated_at"]),
    )


def _load_user(conn: sqlite3.Connection, row: sqlite3.Row) -> User:
    """Turn a ``users`` row into a User, loading its role ids."""
    role_rows = conn.execute(
        "SELECT role_id FROM user_roles WHERE user_id = ?", (row["id"],)
    ).fetchall()
    return User(
        id=row["id"],
        name=row["name"],
        role_ids=[r["role_id"] for r in role_rows],
        created_at=_to_dt(row["created_at"]),
        updated_at=_to_dt(row["updated_at"]),
    )


# ---- small internal helpers ---------------------------------------------
def _get_or_create_permission(conn: sqlite3.Connection, resource: str, action: str) -> int:
    """Return the id of a permission row, inserting it if it is new.

    Permissions are shared: each (resource, action) pair is stored once and
    referenced by many roles.
    """
    r, a = clean_permission(resource, action)
    row = conn.execute(
        "SELECT id FROM permissions WHERE resource = ? AND action = ?", (r, a)
    ).fetchone()
    if row is not None:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO permissions (resource, action) VALUES (?, ?)", (r, a)
    )
    return cursor.lastrowid


def _assert_unique_role_name(conn, name: str, exclude_id: str | None = None) -> None:
    """Raise 409 if another role already has this name (case-insensitive)."""
    row = conn.execute(
        "SELECT id FROM roles WHERE name = ? COLLATE NOCASE AND id != ?",
        (name, exclude_id or ""),
    ).fetchone()
    if row is not None:
        raise ConflictError(f"Role name '{name}' already exists")


def _assert_unique_user_name(conn, name: str, exclude_id: str | None = None) -> None:
    """Raise 409 if another user already has this name (case-insensitive)."""
    row = conn.execute(
        "SELECT id FROM users WHERE name = ? COLLATE NOCASE AND id != ?",
        (name, exclude_id or ""),
    ).fetchone()
    if row is not None:
        raise ConflictError(f"User name '{name}' already exists")


def _touch_role(conn, role_id: str) -> None:
    """Bump a role's updated_at after a change."""
    conn.execute(
        "UPDATE roles SET updated_at = ? WHERE id = ?", (utcnow().isoformat(), role_id)
    )


def _touch_user(conn, user_id: str) -> None:
    """Bump a user's updated_at after a change."""
    conn.execute(
        "UPDATE users SET updated_at = ? WHERE id = ?", (utcnow().isoformat(), user_id)
    )


# ---- Roles ---------------------------------------------------------------
def create_role(conn: sqlite3.Connection, name: str, permissions=None) -> Role:
    cleaned = clean_name(name)
    _assert_unique_role_name(conn, cleaned)
    role_id = str(uuid4())
    now = utcnow().isoformat()
    try:
        conn.execute(
            "INSERT INTO roles (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (role_id, cleaned, now, now),
        )
    except sqlite3.IntegrityError:  # UNIQUE(name) backstop for a race
        raise ConflictError(f"Role name '{cleaned}' already exists")
    for p in permissions or []:
        permission_id = _get_or_create_permission(conn, p.resource, p.action)
        conn.execute(
            "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            (role_id, permission_id),
        )
    conn.commit()
    return get_role(conn, role_id)


def list_roles(conn: sqlite3.Connection, name: str | None = None) -> list[Role]:
    if name and name.strip():
        rows = conn.execute(
            "SELECT * FROM roles WHERE name LIKE ? COLLATE NOCASE ORDER BY name",
            (f"%{name.strip()}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM roles ORDER BY name").fetchall()
    # One extra query per role loads its permissions. That is fine at this scale;
    # a single JOIN + grouping in Python would remove the N+1 if the list grew.
    return [_load_role(conn, row) for row in rows]


def get_role(conn: sqlite3.Connection, role_id: str) -> Role:
    row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
    if row is None:
        raise NotFoundError("Role", role_id)
    return _load_role(conn, row)


def rename_role(conn: sqlite3.Connection, role_id: str, new_name: str) -> Role:
    get_role(conn, role_id)  # 404 if missing
    cleaned = clean_name(new_name)
    _assert_unique_role_name(conn, cleaned, exclude_id=role_id)
    conn.execute(
        "UPDATE roles SET name = ?, updated_at = ? WHERE id = ?",
        (cleaned, utcnow().isoformat(), role_id),
    )
    conn.commit()
    return get_role(conn, role_id)


def add_permission(conn: sqlite3.Connection, role_id: str, resource: str, action: str) -> Role:
    get_role(conn, role_id)  # 404 if missing
    permission_id = _get_or_create_permission(conn, resource, action)
    conn.execute(
        "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
        (role_id, permission_id),
    )
    _touch_role(conn, role_id)
    conn.commit()
    return get_role(conn, role_id)


def remove_permission(conn: sqlite3.Connection, role_id: str, resource: str, action: str) -> Role:
    get_role(conn, role_id)  # 404 if missing
    r, a = clean_permission(resource, action)
    conn.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = ?
          AND permission_id = (
              SELECT id FROM permissions WHERE resource = ? AND action = ?
          )
        """,
        (role_id, r, a),
    )
    _touch_role(conn, role_id)
    conn.commit()
    return get_role(conn, role_id)


def replace_role_permissions(conn: sqlite3.Connection, role_id: str, permissions) -> Role:
    get_role(conn, role_id)  # 404 if missing
    conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
    for p in permissions:
        permission_id = _get_or_create_permission(conn, p.resource, p.action)
        conn.execute(
            "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            (role_id, permission_id),
        )
    _touch_role(conn, role_id)
    conn.commit()
    return get_role(conn, role_id)


def delete_role(conn: sqlite3.Connection, role_id: str) -> None:
    get_role(conn, role_id)  # 404 if missing
    # ON DELETE CASCADE also removes the matching user_roles and role_permissions
    # rows (this works because get_db enabled PRAGMA foreign_keys = ON).
    conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    conn.commit()


def list_users_with_role(conn: sqlite3.Connection, role_id: str) -> list[User]:
    get_role(conn, role_id)  # 404 if the role does not exist
    rows = conn.execute(
        """
        SELECT u.* FROM users u
        JOIN user_roles ur ON ur.user_id = u.id
        WHERE ur.role_id = ?
        ORDER BY u.name
        """,
        (role_id,),
    ).fetchall()
    return [_load_user(conn, row) for row in rows]


# ---- Users ---------------------------------------------------------------
def create_user(conn: sqlite3.Connection, name: str, role_ids=None) -> User:
    cleaned = clean_name(name)
    _assert_unique_user_name(conn, cleaned)
    role_ids = role_ids or []
    for role_id in role_ids:
        get_role(conn, role_id)  # validate every role exists before inserting
    user_id = str(uuid4())
    now = utcnow().isoformat()
    try:
        conn.execute(
            "INSERT INTO users (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, cleaned, now, now),
        )
    except sqlite3.IntegrityError:  # UNIQUE(name) backstop for a race
        raise ConflictError(f"User name '{cleaned}' already exists")
    for role_id in role_ids:
        conn.execute(
            "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
            (user_id, role_id),
        )
    conn.commit()
    return get_user(conn, user_id)


def list_users(conn: sqlite3.Connection, name: str | None = None) -> list[User]:
    if name and name.strip():
        rows = conn.execute(
            "SELECT * FROM users WHERE name LIKE ? COLLATE NOCASE ORDER BY name",
            (f"%{name.strip()}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    return [_load_user(conn, row) for row in rows]


def get_user(conn: sqlite3.Connection, user_id: str) -> User:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFoundError("User", user_id)
    return _load_user(conn, row)


def rename_user(conn: sqlite3.Connection, user_id: str, new_name: str) -> User:
    get_user(conn, user_id)  # 404 if missing
    cleaned = clean_name(new_name)
    _assert_unique_user_name(conn, cleaned, exclude_id=user_id)
    conn.execute(
        "UPDATE users SET name = ?, updated_at = ? WHERE id = ?",
        (cleaned, utcnow().isoformat(), user_id),
    )
    conn.commit()
    return get_user(conn, user_id)


def assign_role(conn: sqlite3.Connection, user_id: str, role_id: str) -> User:
    get_user(conn, user_id)  # 404 if missing
    get_role(conn, role_id)  # role must exist
    conn.execute(
        "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
        (user_id, role_id),
    )
    _touch_user(conn, user_id)
    conn.commit()
    return get_user(conn, user_id)


def remove_role(conn: sqlite3.Connection, user_id: str, role_id: str) -> User:
    get_user(conn, user_id)  # 404 if missing
    conn.execute(
        "DELETE FROM user_roles WHERE user_id = ? AND role_id = ?", (user_id, role_id)
    )
    _touch_user(conn, user_id)
    conn.commit()
    return get_user(conn, user_id)


def replace_user_roles(conn: sqlite3.Connection, user_id: str, role_ids) -> User:
    get_user(conn, user_id)  # 404 if missing
    for role_id in role_ids:
        get_role(conn, role_id)  # validate all before replacing (all-or-nothing)
    conn.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
    for role_id in role_ids:
        conn.execute(
            "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
            (user_id, role_id),
        )
    _touch_user(conn, user_id)
    conn.commit()
    return get_user(conn, user_id)


def delete_user(conn: sqlite3.Connection, user_id: str) -> None:
    get_user(conn, user_id)  # 404 if missing
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()


# ---- Permissions & checking ----------------------------------------------
def get_effective_permissions(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    """All distinct permissions a user has across every role they hold."""
    get_user(conn, user_id)  # 404 if missing
    rows = conn.execute(
        """
        SELECT DISTINCT p.resource, p.action
        FROM permissions p
        JOIN role_permissions rp ON rp.permission_id = p.id
        JOIN user_roles ur       ON ur.role_id = rp.role_id
        WHERE ur.user_id = ?
        ORDER BY p.resource, p.action
        """,
        (user_id,),
    ).fetchall()
    return [{"resource": r["resource"], "action": r["action"]} for r in rows]


def can_user_perform_action(
    conn: sqlite3.Connection, user_id: str, resource: str, action: str
) -> bool:
    """The core check. One JOIN answers it: does any role the user holds grant
    this exact (resource, action)? An unknown user simply matches no rows.
    """
    r = (resource or "").strip().lower()
    a = (action or "").strip().lower()
    row = conn.execute(
        """
        SELECT 1
        FROM user_roles ur
        JOIN role_permissions rp ON rp.role_id = ur.role_id
        JOIN permissions p       ON p.id = rp.permission_id
        WHERE ur.user_id = ? AND p.resource = ? AND p.action = ?
        LIMIT 1
        """,
        (user_id, r, a),
    ).fetchone()
    return row is not None


# ---- Stats ---------------------------------------------------------------
def count_users(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_roles(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
