"""HTTP API endpoints for the SQLite version.

Same URLs and responses as the in-memory version. Routes depend on a database
connection (``Depends(get_db)``) instead of the in-memory service object, and
convert the dataclasses returned by ``services`` into response schemas.

Ordering note: static paths like ``/users/count`` are declared before the
parametrized ``/users/{user_id}`` so they are matched first.
"""

import sqlite3

from fastapi import APIRouter, Depends, Query, status

from . import services
from .db import get_db
from .models import Role, User
from .schemas import (
    AssignRoleRequest,
    CountResponse,
    CreateRoleRequest,
    CreateUserRequest,
    EffectivePermissionsResponse,
    HealthResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
    PermissionSchema,
    RenameRequest,
    ReplacePermissionsRequest,
    ReplaceRolesRequest,
    RoleResponse,
    SystemInfoResponse,
    UserResponse,
)

router = APIRouter()

API_VERSION = "2.0.0-sql"


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        role_ids=sorted(user.role_ids),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _role_to_response(role: Role) -> RoleResponse:
    permissions = sorted(role.permissions, key=lambda p: (p.resource, p.action))
    return RoleResponse(
        id=role.id,
        name=role.name,
        permissions=[PermissionSchema(resource=p.resource, action=p.action) for p in permissions],
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


# ==== Users ===============================================================
@router.get("/users", response_model=list[UserResponse])
def list_users(name: str | None = Query(default=None), db: sqlite3.Connection = Depends(get_db)):
    return [_user_to_response(u) for u in services.list_users(db, name)]


@router.get("/users/count", response_model=CountResponse)
def count_users(db: sqlite3.Connection = Depends(get_db)):
    return CountResponse(count=services.count_users(db))


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserRequest, db: sqlite3.Connection = Depends(get_db)):
    return _user_to_response(services.create_user(db, body.name, body.role_ids))


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _user_to_response(services.get_user(db, user_id))


@router.patch("/users/{user_id}", response_model=UserResponse)
def rename_user(user_id: str, body: RenameRequest, db: sqlite3.Connection = Depends(get_db)):
    return _user_to_response(services.rename_user(db, user_id, body.name))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: sqlite3.Connection = Depends(get_db)):
    services.delete_user(db, user_id)


@router.post("/users/{user_id}/roles", response_model=UserResponse)
def assign_role(user_id: str, body: AssignRoleRequest, db: sqlite3.Connection = Depends(get_db)):
    return _user_to_response(services.assign_role(db, user_id, body.role_id))


@router.put("/users/{user_id}/roles", response_model=UserResponse)
def replace_user_roles(user_id: str, body: ReplaceRolesRequest, db: sqlite3.Connection = Depends(get_db)):
    return _user_to_response(services.replace_user_roles(db, user_id, body.role_ids))


@router.delete("/users/{user_id}/roles/{role_id}", response_model=UserResponse)
def remove_role(user_id: str, role_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _user_to_response(services.remove_role(db, user_id, role_id))


@router.get("/users/{user_id}/permissions", response_model=EffectivePermissionsResponse)
def user_permissions(user_id: str, db: sqlite3.Connection = Depends(get_db)):
    permissions = services.get_effective_permissions(db, user_id)
    return EffectivePermissionsResponse(
        user_id=user_id, permissions=[PermissionSchema(**p) for p in permissions]
    )


# ==== Roles ===============================================================
@router.get("/roles", response_model=list[RoleResponse])
def list_roles(name: str | None = Query(default=None), db: sqlite3.Connection = Depends(get_db)):
    return [_role_to_response(r) for r in services.list_roles(db, name)]


@router.get("/roles/count", response_model=CountResponse)
def count_roles(db: sqlite3.Connection = Depends(get_db)):
    return CountResponse(count=services.count_roles(db))


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(body: CreateRoleRequest, db: sqlite3.Connection = Depends(get_db)):
    return _role_to_response(services.create_role(db, body.name, body.permissions))


@router.get("/roles/{role_id}", response_model=RoleResponse)
def get_role(role_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _role_to_response(services.get_role(db, role_id))


@router.patch("/roles/{role_id}", response_model=RoleResponse)
def rename_role(role_id: str, body: RenameRequest, db: sqlite3.Connection = Depends(get_db)):
    return _role_to_response(services.rename_role(db, role_id, body.name))


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: str, db: sqlite3.Connection = Depends(get_db)):
    services.delete_role(db, role_id)


@router.post("/roles/{role_id}/permissions", response_model=RoleResponse)
def add_permission(role_id: str, body: PermissionSchema, db: sqlite3.Connection = Depends(get_db)):
    return _role_to_response(services.add_permission(db, role_id, body.resource, body.action))


@router.put("/roles/{role_id}/permissions", response_model=RoleResponse)
def replace_role_permissions(role_id: str, body: ReplacePermissionsRequest, db: sqlite3.Connection = Depends(get_db)):
    return _role_to_response(services.replace_role_permissions(db, role_id, body.permissions))


@router.delete("/roles/{role_id}/permissions", response_model=RoleResponse)
def remove_permission(role_id: str, body: PermissionSchema, db: sqlite3.Connection = Depends(get_db)):
    return _role_to_response(services.remove_permission(db, role_id, body.resource, body.action))


@router.get("/roles/{role_id}/users", response_model=list[UserResponse])
def users_with_role(role_id: str, db: sqlite3.Connection = Depends(get_db)):
    return [_user_to_response(u) for u in services.list_users_with_role(db, role_id)]


# ==== Permission check & system ===========================================
@router.post("/check-permission", response_model=PermissionCheckResponse)
def check_permission(body: PermissionCheckRequest, db: sqlite3.Connection = Depends(get_db)):
    allowed = services.can_user_perform_action(db, body.user_id, body.resource, body.action)
    return PermissionCheckResponse(allowed=allowed)


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@router.get("/system/info", response_model=SystemInfoResponse)
def system_info(db: sqlite3.Connection = Depends(get_db)):
    return SystemInfoResponse(
        name="RBAC Service (SQLite)",
        version=API_VERSION,
        users=services.count_users(db),
        roles=services.count_roles(db),
    )
