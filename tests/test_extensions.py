"""Tests for the extended features (Parts 1 & 2).

Service-level tests exercise the logic directly; API-level tests drive the
endpoints via TestClient with a fresh service injected through
``dependency_overrides``.
"""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_service
from app.errors import ConflictError, NotFoundError, ValidationError
from app.main import app
from app.models import Permission
from app.services import RBACService
from app.storage import InMemoryStore


@pytest.fixture
def service() -> RBACService:
    return RBACService(InMemoryStore())


@pytest.fixture
def client():
    test_service = RBACService(InMemoryStore())
    app.dependency_overrides[get_service] = lambda: test_service
    with TestClient(app) as test_client:
        yield test_client, test_service
    app.dependency_overrides.clear()


# ---- Get by id -----------------------------------------------------------
def test_get_user_by_id(service):
    user = service.create_user("Bob")
    assert service.get_user(user.id).name == "Bob"


def test_get_role_by_id_unknown_raises(service):
    with pytest.raises(NotFoundError):
        service.get_role("missing")


# ---- Rename --------------------------------------------------------------
def test_rename_user(service):
    user = service.create_user("Bob")
    service.rename_user(user.id, "Bobby")
    assert service.get_user(user.id).name == "Bobby"


def test_rename_user_to_existing_name_conflicts(service):
    service.create_user("Alice")
    bob = service.create_user("Bob")
    with pytest.raises(ConflictError):
        service.rename_user(bob.id, "Alice")


def test_rename_role(service):
    role = service.create_role("editor")
    service.rename_role(role.id, "writer")
    assert service.get_role(role.id).name == "writer"


# ---- Replace roles / permissions -----------------------------------------
def test_replace_user_roles(service):
    r1 = service.create_role("r1")
    r2 = service.create_role("r2")
    user = service.create_user("Bob", [r1.id])
    service.replace_user_roles(user.id, [r2.id])
    assert service.get_user(user.id).role_ids == {r2.id}


def test_replace_user_roles_is_all_or_nothing(service):
    r1 = service.create_role("r1")
    user = service.create_user("Bob", [r1.id])
    with pytest.raises(NotFoundError):
        service.replace_user_roles(user.id, [r1.id, "bad-role"])
    # Unchanged because validation happens before assignment.
    assert service.get_user(user.id).role_ids == {r1.id}


def test_replace_role_permissions(service):
    role = service.create_role("editor", [Permission("documents", "read")])
    service.replace_role_permissions(role.id, [Permission("users", "write")])
    assert service.get_role(role.id).permissions == {Permission("users", "write")}


# ---- Effective permissions + cache ---------------------------------------
def test_effective_permissions_merge_across_roles(service):
    r1 = service.create_role("r1", [Permission("a", "read")])
    r2 = service.create_role("r2", [Permission("b", "write")])
    user = service.create_user("Bob", [r1.id, r2.id])
    assert service.get_effective_permissions(user.id) == {
        Permission("a", "read"),
        Permission("b", "write"),
    }


def test_cache_is_invalidated_on_permission_change(service):
    role = service.create_role("editor")
    user = service.create_user("Bob", [role.id])
    assert service.get_effective_permissions(user.id) == set()  # caches empty set
    service.add_permission(role.id, Permission("documents", "write"))
    # Must reflect the change, i.e. the cache was invalidated.
    assert Permission("documents", "write") in service.get_effective_permissions(user.id)


# ---- Users with a role / search ------------------------------------------
def test_list_users_with_role(service):
    role = service.create_role("editor")
    a = service.create_user("A", [role.id])
    service.create_user("B")
    holders = {u.id for u in service.list_users_with_role(role.id)}
    assert holders == {a.id}


def test_search_users_is_case_insensitive_substring(service):
    service.create_user("Alice")
    service.create_user("Alicia")
    service.create_user("Bob")
    names = {u.name for u in service.search_users("ali")}
    assert names == {"Alice", "Alicia"}


# ---- Duplicate prevention & validation -----------------------------------
def test_duplicate_user_name_conflicts(service):
    service.create_user("Alice")
    with pytest.raises(ConflictError):
        service.create_user("alice")  # case-insensitive uniqueness


def test_duplicate_role_name_conflicts(service):
    service.create_role("admin")
    with pytest.raises(ConflictError):
        service.create_role("ADMIN")


def test_blank_name_is_rejected(service):
    with pytest.raises(ValidationError):
        service.create_user("   ")


def test_blank_permission_is_rejected(service):
    with pytest.raises(ValidationError):
        service.create_role("r", [Permission("  ", "read")])


def test_names_are_trimmed(service):
    user = service.create_user("  Bob  ")
    assert user.name == "Bob"


def test_permissions_are_normalized_lowercase(service):
    role = service.create_role("R", [Permission("Documents", "WRITE")])
    user = service.create_user("U", [role.id])
    assert Permission("documents", "write") in role.permissions
    assert service.can_user_perform_action(user.id, "DOCUMENTS", "Write") is True


# ---- Stats & audit -------------------------------------------------------
def test_counts(service):
    service.create_user("A")
    service.create_role("r")
    assert service.count_users() == 1
    assert service.count_roles() == 1


def test_audit_log_records_operations(service):
    service.create_user("A")
    assert any(entry["action"] == "create_user" for entry in service.get_audit_log())


# ==== API-level ===========================================================
def test_api_get_user_by_id(client):
    test_client, _ = client
    user = test_client.post("/users", json={"name": "Bob"}).json()
    response = test_client.get(f"/users/{user['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Bob"


def test_api_rename_user_patch(client):
    test_client, _ = client
    user = test_client.post("/users", json={"name": "Bob"}).json()
    response = test_client.patch(f"/users/{user['id']}", json={"name": "Bobby"})
    assert response.status_code == 200
    assert response.json()["name"] == "Bobby"


def test_api_duplicate_name_returns_409(client):
    test_client, _ = client
    test_client.post("/users", json={"name": "Alice"})
    response = test_client.post("/users", json={"name": "Alice"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_api_whitespace_name_returns_422(client):
    test_client, _ = client
    response = test_client.post("/users", json={"name": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_api_replace_user_roles_put(client):
    test_client, _ = client
    r1 = test_client.post("/roles", json={"name": "r1"}).json()
    r2 = test_client.post("/roles", json={"name": "r2"}).json()
    user = test_client.post("/users", json={"name": "Bob", "role_ids": [r1["id"]]}).json()
    response = test_client.put(f"/users/{user['id']}/roles", json={"role_ids": [r2["id"]]})
    assert response.status_code == 200
    assert response.json()["role_ids"] == [r2["id"]]


def test_api_effective_permissions(client):
    test_client, _ = client
    role = test_client.post(
        "/roles", json={"name": "editor", "permissions": [{"resource": "documents", "action": "write"}]}
    ).json()
    user = test_client.post("/users", json={"name": "Bob", "role_ids": [role["id"]]}).json()
    response = test_client.get(f"/users/{user['id']}/permissions")
    assert response.status_code == 200
    assert response.json()["permissions"] == [{"resource": "documents", "action": "write"}]


def test_api_users_with_role(client):
    test_client, _ = client
    role = test_client.post("/roles", json={"name": "editor"}).json()
    test_client.post("/users", json={"name": "Bob", "role_ids": [role["id"]]})
    response = test_client.get(f"/roles/{role['id']}/users")
    assert response.status_code == 200
    assert [u["name"] for u in response.json()] == ["Bob"]


def test_api_search_users_query(client):
    test_client, _ = client
    test_client.post("/users", json={"name": "Alice"})
    test_client.post("/users", json={"name": "Bob"})
    response = test_client.get("/users", params={"name": "ali"})
    assert [u["name"] for u in response.json()] == ["Alice"]


def test_api_counts(client):
    test_client, _ = client
    test_client.post("/users", json={"name": "Bob"})
    assert test_client.get("/users/count").json() == {"count": 1}
    assert test_client.get("/roles/count").json() == {"count": 0}


def test_api_health(client):
    test_client, _ = client
    assert test_client.get("/health").json() == {"status": "ok"}


def test_api_system_info(client):
    test_client, _ = client
    body = test_client.get("/system/info").json()
    assert body["version"] == "2.0.0"
    assert body["users"] == 0


def test_api_audit_records_actions(client):
    test_client, _ = client
    test_client.post("/users", json={"name": "Bob"})
    actions = [entry["action"] for entry in test_client.get("/system/audit").json()]
    assert "create_user" in actions


def test_api_error_format_is_consistent(client):
    test_client, _ = client
    response = test_client.get("/users/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
