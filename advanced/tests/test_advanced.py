"""Tests for OAuth login, multi-tenancy, role hierarchy, and authorization."""

import pytest
from fastapi.testclient import TestClient

from advanced.app.dependencies import get_service
from advanced.app.main import app
from advanced.app.seed import build_seeded_service
from advanced.app.services import RBACService


@pytest.fixture
def client():
    fresh = build_seeded_service()  # two tenants, seeded users with passwords
    app.dependency_overrides[get_service] = lambda: fresh
    with TestClient(app) as c:
        yield c, fresh
    app.dependency_overrides.clear()


def token(client, username, password):
    response = client.post("/token", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def role_id_by_name(client, tok, name):
    roles = client.get("/roles", headers=auth(tok)).json()
    return next(r["id"] for r in roles if r["name"] == name)


# ---- OAuth login --------------------------------------------------------
def test_login_success_returns_token(client):
    c, _ = client
    assert token(c, "alice", "alice-pw")


def test_login_wrong_password_401(client):
    c, _ = client
    r = c.post("/token", data={"username": "alice", "password": "nope"})
    assert r.status_code == 401


def test_protected_endpoint_requires_token(client):
    c, _ = client
    assert c.get("/me").status_code == 401


def test_me_returns_identity_and_permissions(client):
    c, _ = client
    tok = token(c, "alice", "alice-pw")
    body = c.get("/me", headers=auth(tok)).json()
    assert body["name"] == "alice"
    assert body["tenant_id"] == "acme"


# ---- Role hierarchy (inheritance) ---------------------------------------
def test_admin_inherits_permissions_through_hierarchy(client):
    c, _ = client
    tok = token(c, "alice", "alice-pw")
    perms = {(p["resource"], p["action"]) for p in c.get("/me", headers=auth(tok)).json()["permissions"]}
    # admin -> editor -> viewer, so alice has all three levels' permissions:
    assert ("roles", "write") in perms       # own (admin)
    assert ("documents", "write") in perms   # inherited from editor
    assert ("documents", "read") in perms    # inherited from viewer


def test_check_uses_inherited_permission(client):
    c, _ = client
    tok = token(c, "alice", "alice-pw")
    alice_id = c.get("/me", headers=auth(tok)).json()["id"]
    r = c.post(
        "/check-permission",
        headers=auth(tok),
        json={"user_id": alice_id, "resource": "documents", "action": "read"},
    )
    assert r.json() == {"allowed": True}  # read is only on viewer, reached via hierarchy


def test_cycle_in_hierarchy_is_rejected(client):
    c, _ = client
    tok = token(c, "alice", "alice-pw")
    viewer = role_id_by_name(c, tok, "viewer")
    admin = role_id_by_name(c, tok, "admin")
    # admin already inherits viewer; making viewer inherit admin would be a cycle.
    r = c.put(f"/roles/{viewer}/parents", headers=auth(tok), json={"parent_ids": [admin]})
    assert r.status_code == 422


# ---- Multi-tenancy (isolation) ------------------------------------------
def test_tenants_are_isolated(client):
    c, _ = client
    acme = token(c, "alice", "alice-pw")
    globex = token(c, "carol", "carol-pw")
    acme_roles = {r["name"] for r in c.get("/roles", headers=auth(acme)).json()}
    globex_roles = {r["name"] for r in c.get("/roles", headers=auth(globex)).json()}
    assert "admin" in acme_roles and "admin" not in globex_roles
    assert globex_roles == {"gviewer"}


def test_cannot_assign_role_from_another_tenant(client):
    c, _ = client
    acme = token(c, "alice", "alice-pw")
    globex = token(c, "carol", "carol-pw")
    acme_admin = role_id_by_name(c, acme, "admin")
    carol_id = c.get("/me", headers=auth(globex)).json()["id"]
    # Alice (acme admin) tries to give carol (globex) an acme role -> carol not in her tenant.
    r = c.post(f"/users/{carol_id}/roles", headers=auth(acme), json={"role_id": acme_admin})
    assert r.status_code == 404


def test_cross_tenant_permission_check_is_false(client):
    c, _ = client
    acme = token(c, "alice", "alice-pw")
    globex = token(c, "carol", "carol-pw")
    carol_id = c.get("/me", headers=auth(globex)).json()["id"]
    # Alice checks a globex user -> denied, no leak.
    r = c.post(
        "/check-permission",
        headers=auth(acme),
        json={"user_id": carol_id, "resource": "documents", "action": "read"},
    )
    assert r.json() == {"allowed": False}


# ---- Authorization (RBAC guards the API itself) -------------------------
def test_admin_can_create_role(client):
    c, _ = client
    tok = token(c, "alice", "alice-pw")
    r = c.post("/roles", headers=auth(tok), json={"name": "auditor"})
    assert r.status_code == 201


def test_editor_cannot_create_role(client):
    c, _ = client
    tok = token(c, "bob", "bob-pw")  # editor: no roles:write
    r = c.post("/roles", headers=auth(tok), json={"name": "auditor"})
    assert r.status_code == 403


def test_admin_can_create_user_editor_cannot(client):
    c, _ = client
    admin_tok = token(c, "alice", "alice-pw")
    editor_tok = token(c, "bob", "bob-pw")
    ok = c.post("/users", headers=auth(admin_tok), json={"name": "dave", "password": "pw"})
    assert ok.status_code == 201
    denied = c.post("/users", headers=auth(editor_tok), json={"name": "erin", "password": "pw"})
    assert denied.status_code == 403


def test_duplicate_role_name_within_tenant_conflicts(client):
    c, _ = client
    tok = token(c, "alice", "alice-pw")
    assert c.post("/roles", headers=auth(tok), json={"name": "dupe"}).status_code == 201
    assert c.post("/roles", headers=auth(tok), json={"name": "dupe"}).status_code == 409
