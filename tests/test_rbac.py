"""Unit tests for the RBAC service and a few API-level tests.

The service tests exercise the business logic directly (fast, no HTTP). The
API tests use FastAPI's TestClient with a fresh service injected via
dependency override, so they never touch the seeded singleton.
"""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_service
from app.main import app
from app.models import Permission
from app.services import NotFoundError, RBACService
from app.storage import InMemoryStore


@pytest.fixture
def service() -> RBACService:
    return RBACService(InMemoryStore())


@pytest.fixture
def client():
    """A TestClient whose service is a fresh, empty in-memory store."""
    test_service = RBACService(InMemoryStore())
    app.dependency_overrides[get_service] = lambda: test_service
    with TestClient(app) as test_client:
        yield test_client, test_service
    app.dependency_overrides.clear()


# ---- Permission checking -------------------------------------------------
def test_permission_check_allowed(service):
    role = service.create_role("editor", [Permission("documents", "write")])
    user = service.create_user("Bob", [role.id])
    assert service.can_user_perform_action(user.id, "documents", "write") is True


def test_permission_check_denied(service):
    role = service.create_role("viewer", [Permission("documents", "read")])
    user = service.create_user("Charlie", [role.id])
    assert service.can_user_perform_action(user.id, "documents", "write") is False


# ---- Assign / remove role ------------------------------------------------
def test_assign_role_grants_permission(service):
    role = service.create_role("editor", [Permission("documents", "write")])
    user = service.create_user("Bob")
    assert service.can_user_perform_action(user.id, "documents", "write") is False
    service.assign_role(user.id, role.id)
    assert service.can_user_perform_action(user.id, "documents", "write") is True


def test_remove_role_revokes_permission(service):
    role = service.create_role("editor", [Permission("documents", "write")])
    user = service.create_user("Bob", [role.id])
    service.remove_role(user.id, role.id)
    assert service.can_user_perform_action(user.id, "documents", "write") is False


# ---- Add / remove permission --------------------------------------------
def test_add_permission(service):
    role = service.create_role("editor")
    user = service.create_user("Bob", [role.id])
    assert service.can_user_perform_action(user.id, "documents", "write") is False
    service.add_permission(role.id, Permission("documents", "write"))
    assert service.can_user_perform_action(user.id, "documents", "write") is True


def test_remove_permission(service):
    role = service.create_role("editor", [Permission("documents", "write")])
    user = service.create_user("Bob", [role.id])
    service.remove_permission(role.id, Permission("documents", "write"))
    assert service.can_user_perform_action(user.id, "documents", "write") is False


# ---- Edge cases ----------------------------------------------------------
def test_invalid_user_returns_false(service):
    assert service.can_user_perform_action("does-not-exist", "documents", "read") is False


def test_user_with_no_roles_is_denied(service):
    user = service.create_user("Dana")
    assert service.can_user_perform_action(user.id, "documents", "read") is False


def test_duplicate_role_assignment_is_idempotent(service):
    role = service.create_role("editor", [Permission("documents", "write")])
    user = service.create_user("Bob")
    service.assign_role(user.id, role.id)
    service.assign_role(user.id, role.id)
    assert user.role_ids == {role.id}


def test_duplicate_permission_assignment_is_idempotent(service):
    role = service.create_role("editor")
    service.add_permission(role.id, Permission("documents", "write"))
    service.add_permission(role.id, Permission("documents", "write"))
    assert role.permissions == {Permission("documents", "write")}


def test_create_user_with_unknown_role_raises(service):
    with pytest.raises(NotFoundError):
        service.create_user("Ghost", ["missing-role-id"])


def test_assign_unknown_role_raises(service):
    user = service.create_user("Bob")
    with pytest.raises(NotFoundError):
        service.assign_role(user.id, "missing-role-id")


# ---- Delete user / role --------------------------------------------------
def test_delete_user(service):
    user = service.create_user("Bob")
    service.delete_user(user.id)
    with pytest.raises(NotFoundError):
        service.get_user(user.id)


def test_delete_unknown_user_raises(service):
    with pytest.raises(NotFoundError):
        service.delete_user("missing-user-id")


def test_delete_role_cascades_to_users(service):
    role = service.create_role("editor", [Permission("documents", "write")])
    user = service.create_user("Bob", [role.id])
    service.delete_role(role.id)
    with pytest.raises(NotFoundError):
        service.get_role(role.id)
    # The user must no longer reference the deleted role, and lose its access.
    assert role.id not in service.get_user(user.id).role_ids
    assert service.can_user_perform_action(user.id, "documents", "write") is False


def test_delete_unknown_role_raises(service):
    with pytest.raises(NotFoundError):
        service.delete_role("missing-role-id")


# ---- API-level tests -----------------------------------------------------
def test_api_example_scenario(client):
    test_client, _ = client
    editor = test_client.post(
        "/roles",
        json={"name": "editor", "permissions": [{"resource": "documents", "action": "write"}]},
    ).json()
    bob = test_client.post("/users", json={"name": "Bob", "role_ids": [editor["id"]]}).json()

    allowed = test_client.post(
        "/check-permission",
        json={"user_id": bob["id"], "resource": "documents", "action": "write"},
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"allowed": True}

    denied = test_client.post(
        "/check-permission",
        json={"user_id": bob["id"], "resource": "users", "action": "write"},
    )
    assert denied.json() == {"allowed": False}


def test_api_create_user_returns_201(client):
    test_client, _ = client
    response = test_client.post("/users", json={"name": "Zoe"})
    assert response.status_code == 201
    assert response.json()["name"] == "Zoe"


def test_api_unknown_role_returns_404(client):
    test_client, _ = client
    response = test_client.post("/users", json={"name": "Ghost", "role_ids": ["nope"]})
    assert response.status_code == 404


def test_api_missing_name_returns_422(client):
    test_client, _ = client
    response = test_client.post("/users", json={})
    assert response.status_code == 422


def test_api_delete_user_returns_204(client):
    test_client, _ = client
    user = test_client.post("/users", json={"name": "Bob"}).json()
    response = test_client.delete(f"/users/{user['id']}")
    assert response.status_code == 204
    remaining = test_client.get("/users").json()
    assert all(u["id"] != user["id"] for u in remaining)


def test_api_delete_role_returns_204(client):
    test_client, _ = client
    role = test_client.post("/roles", json={"name": "editor"}).json()
    response = test_client.delete(f"/roles/{role['id']}")
    assert response.status_code == 204


def test_api_delete_unknown_user_returns_404(client):
    test_client, _ = client
    response = test_client.delete("/users/does-not-exist")
    assert response.status_code == 404
