"""HTTP endpoints for the advanced service.

Public:    POST /token, GET /health
Protected: everything else needs a Bearer token.
Guarded:   write endpoints also require an RBAC permission (roles:write /
           users:write) checked against the caller's own effective permissions.
Every protected call is scoped to the caller's tenant (from the token).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from advanced.app.auth import create_access_token
from advanced.app.dependencies import get_current_user, get_service, require_permission
from advanced.app.models import Permission, Role, User
from advanced.app.schemas import (
    AssignRoleRequest,
    CheckRequest,
    CheckResponse,
    CreateRoleRequest,
    CreateUserRequest,
    MeResponse,
    PermissionSchema,
    RoleResponse,
    SetParentsRequest,
    TokenResponse,
    UserResponse,
)
from advanced.app.services import RBACService

router = APIRouter()


def _perms(permissions) -> list[PermissionSchema]:
    return [
        PermissionSchema(resource=p.resource, action=p.action)
        for p in sorted(permissions, key=lambda p: (p.resource, p.action))
    ]


def _role_to_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        permissions=_perms(role.permissions),
        parent_ids=sorted(role.parent_ids),
    )


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id, tenant_id=user.tenant_id, name=user.name, role_ids=sorted(user.role_ids)
    )


# ---- Auth ---------------------------------------------------------------
@router.post("/token", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), service: RBACService = Depends(get_service)):
    user = service.authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user_id=user.id, tenant_id=user.tenant_id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), service: RBACService = Depends(get_service)):
    permissions = service.effective_permissions(user.tenant_id, user.id)
    return MeResponse(
        id=user.id, tenant_id=user.tenant_id, name=user.name, permissions=_perms(permissions)
    )


# ---- Roles (tenant-scoped) ----------------------------------------------
@router.get("/roles", response_model=list[RoleResponse])
def list_roles(user: User = Depends(get_current_user), service: RBACService = Depends(get_service)):
    return [_role_to_response(r) for r in service.list_roles(user.tenant_id)]


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    body: CreateRoleRequest,
    user: User = Depends(require_permission("roles", "write")),
    service: RBACService = Depends(get_service),
):
    permissions = [Permission(resource=p.resource, action=p.action) for p in body.permissions]
    role = service.create_role(user.tenant_id, body.name, permissions, body.parent_ids)
    return _role_to_response(role)


@router.post("/roles/{role_id}/permissions", response_model=RoleResponse)
def add_permission(
    role_id: str,
    body: PermissionSchema,
    user: User = Depends(require_permission("roles", "write")),
    service: RBACService = Depends(get_service),
):
    role = service.add_permission(user.tenant_id, role_id, Permission(body.resource, body.action))
    return _role_to_response(role)


@router.put("/roles/{role_id}/parents", response_model=RoleResponse)
def set_parents(
    role_id: str,
    body: SetParentsRequest,
    user: User = Depends(require_permission("roles", "write")),
    service: RBACService = Depends(get_service),
):
    role = service.set_role_parents(user.tenant_id, role_id, body.parent_ids)
    return _role_to_response(role)


# ---- Users (tenant-scoped) ----------------------------------------------
@router.get("/users", response_model=list[UserResponse])
def list_users(user: User = Depends(get_current_user), service: RBACService = Depends(get_service)):
    return [_user_to_response(u) for u in service.list_users(user.tenant_id)]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    user: User = Depends(require_permission("users", "write")),
    service: RBACService = Depends(get_service),
):
    created = service.create_user(user.tenant_id, body.name, body.password, body.role_ids)
    return _user_to_response(created)


@router.post("/users/{user_id}/roles", response_model=UserResponse)
def assign_role(
    user_id: str,
    body: AssignRoleRequest,
    user: User = Depends(require_permission("users", "write")),
    service: RBACService = Depends(get_service),
):
    updated = service.assign_role(user.tenant_id, user_id, body.role_id)
    return _user_to_response(updated)


# ---- Permission check ---------------------------------------------------
@router.post("/check-permission", response_model=CheckResponse)
def check_permission(
    body: CheckRequest,
    user: User = Depends(get_current_user),
    service: RBACService = Depends(get_service),
):
    allowed = service.can_user_perform_action(user.tenant_id, body.user_id, body.resource, body.action)
    return CheckResponse(allowed=allowed)


@router.get("/health")
def health():
    return {"status": "ok"}
