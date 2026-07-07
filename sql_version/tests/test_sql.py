"""Tests for the SQLite (stdlib ``sqlite3``) version.

Each test gets its own empty database in a temp file. ``get_db`` is overridden
to open connections against that file, and we deliberately do NOT enter the
TestClient as a context manager so the app's startup ``lifespan`` (which would
create/seed the real ``rbac.db``) never runs.
"""

import pytest
from fastapi.testclient import TestClient

from sql_version.app.db import connect, get_db, init_db
from sql_version.app.main import app


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test.db"

    # Create the schema once in the temp file.
    setup_conn = connect(db_file)
    init_db(setup_conn)
    setup_conn.close()

    # One fresh connection per request, all pointing at the same temp file.
    def override_get_db():
        conn = connect(db_file)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)  # no `with`: skip lifespan, leave the real db alone
    yield test_client
    app.dependency_overrides.clear()


def test_create_and_get_user(client):
    created = client.post("/users", json={"name": "Bob"})
    assert created.status_code == 201
    user_id = created.json()["id"]
    fetched = client.get(f"/users/{user_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Bob"


def test_example_scenario(client):
    editor = client.post(
        "/roles",
        json={"name": "editor", "permissions": [{"resource": "documents", "action": "write"}]},
    ).json()
    bob = client.post("/users", json={"name": "Bob", "role_ids": [editor["id"]]}).json()

    allowed = client.post(
        "/check-permission",
        json={"user_id": bob["id"], "resource": "documents", "action": "write"},
    )
    assert allowed.json() == {"allowed": True}

    denied = client.post(
        "/check-permission",
        json={"user_id": bob["id"], "resource": "users", "action": "write"},
    )
    assert denied.json() == {"allowed": False}


def test_many_to_many_shared_role(client):
    role = client.post(
        "/roles",
        json={"name": "editor", "permissions": [{"resource": "documents", "action": "write"}]},
    ).json()
    a = client.post("/users", json={"name": "A", "role_ids": [role["id"]]}).json()
    b = client.post("/users", json={"name": "B", "role_ids": [role["id"]]}).json()
    for user in (a, b):
        r = client.post(
            "/check-permission",
            json={"user_id": user["id"], "resource": "documents", "action": "write"},
        )
        assert r.json() == {"allowed": True}
    holders = client.get(f"/roles/{role['id']}/users").json()
    assert {u["name"] for u in holders} == {"A", "B"}


def test_delete_role_cascades(client):
    role = client.post(
        "/roles",
        json={"name": "tmp", "permissions": [{"resource": "x", "action": "read"}]},
    ).json()
    user = client.post("/users", json={"name": "Bob", "role_ids": [role["id"]]}).json()
    assert client.delete(f"/roles/{role['id']}").status_code == 204
    # User remains but the role reference is gone; access revoked.
    refreshed = client.get(f"/users/{user['id']}").json()
    assert refreshed["role_ids"] == []
    r = client.post(
        "/check-permission", json={"user_id": user["id"], "resource": "x", "action": "read"}
    )
    assert r.json() == {"allowed": False}


def test_duplicate_user_name_returns_409(client):
    client.post("/users", json={"name": "Alice"})
    response = client.post("/users", json={"name": "alice"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_rename_user(client):
    user = client.post("/users", json={"name": "Bob"}).json()
    response = client.patch(f"/users/{user['id']}", json={"name": "Bobby"})
    assert response.status_code == 200
    assert response.json()["name"] == "Bobby"


def test_replace_user_roles(client):
    r1 = client.post("/roles", json={"name": "r1"}).json()
    r2 = client.post("/roles", json={"name": "r2"}).json()
    user = client.post("/users", json={"name": "Bob", "role_ids": [r1["id"]]}).json()
    response = client.put(f"/users/{user['id']}/roles", json={"role_ids": [r2["id"]]})
    assert response.json()["role_ids"] == [r2["id"]]


def test_effective_permissions_merge(client):
    r1 = client.post(
        "/roles", json={"name": "r1", "permissions": [{"resource": "a", "action": "read"}]}
    ).json()
    r2 = client.post(
        "/roles", json={"name": "r2", "permissions": [{"resource": "b", "action": "write"}]}
    ).json()
    user = client.post("/users", json={"name": "Bob", "role_ids": [r1["id"], r2["id"]]}).json()
    perms = client.get(f"/users/{user['id']}/permissions").json()["permissions"]
    assert perms == [{"resource": "a", "action": "read"}, {"resource": "b", "action": "write"}]


def test_permission_normalization(client):
    role = client.post(
        "/roles", json={"name": "R", "permissions": [{"resource": "Documents", "action": "WRITE"}]}
    ).json()
    user = client.post("/users", json={"name": "U", "role_ids": [role["id"]]}).json()
    r = client.post(
        "/check-permission",
        json={"user_id": user["id"], "resource": "documents", "action": "write"},
    )
    assert r.json() == {"allowed": True}


def test_search_users(client):
    client.post("/users", json={"name": "Alice"})
    client.post("/users", json={"name": "Bob"})
    names = [u["name"] for u in client.get("/users", params={"name": "ali"}).json()]
    assert names == ["Alice"]


def test_counts(client):
    client.post("/users", json={"name": "Bob"})
    assert client.get("/users/count").json() == {"count": 1}
    assert client.get("/roles/count").json() == {"count": 0}


def test_health_and_system_info(client):
    assert client.get("/health").json() == {"status": "ok"}
    info = client.get("/system/info").json()
    assert info["version"] == "2.0.0-sql"


def test_unknown_user_404_error_format(client):
    response = client.get("/users/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_check_unknown_user_is_false(client):
    r = client.post(
        "/check-permission", json={"user_id": "ghost", "resource": "x", "action": "read"}
    )
    assert r.json() == {"allowed": False}
