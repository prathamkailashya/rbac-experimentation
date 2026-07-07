"""HTTP API endpoints (extended).

Routes stay thin: validate input with Pydantic, delegate to the service, and
convert domain objects into response schemas.

Ordering note: static paths like ``/users/count`` are declared *before* the
parametrized ``/users/{user_id}`` so they are matched first.
"""

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import get_service
from app.models import Permission, Role, User
from app.schemas import (
    AssignRoleRequest,
    AuditEntryResponse,
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
from app.services import RBACService

router = APIRouter()

API_VERSION = "2.0.0"


def _sorted_permission_schemas(permissions) -> list[PermissionSchema]:
    return [
        PermissionSchema(resource=p.resource, action=p.action)
        for p in sorted(permissions, key=lambda p: (p.resource, p.action))
    ]


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        role_ids=sorted(user.role_ids),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _role_to_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        permissions=_sorted_permission_schemas(role.permissions),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


# ==== Users ===============================================================
@router.get("/users", response_model=list[UserResponse])
def list_users(name: str | None = Query(default=None), service: RBACService = Depends(get_service)):
    return [_user_to_response(u) for u in service.search_users(name)]


@router.get("/users/count", response_model=CountResponse)
def count_users(service: RBACService = Depends(get_service)):
    return CountResponse(count=service.count_users())


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserRequest, service: RBACService = Depends(get_service)):
    return _user_to_response(service.create_user(name=body.name, role_ids=body.role_ids))


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, service: RBACService = Depends(get_service)):
    return _user_to_response(service.get_user(user_id))


@router.patch("/users/{user_id}", response_model=UserResponse)
def rename_user(user_id: str, body: RenameRequest, service: RBACService = Depends(get_service)):
    return _user_to_response(service.rename_user(user_id, body.name))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, service: RBACService = Depends(get_service)):
    service.delete_user(user_id)


@router.post("/users/{user_id}/roles", response_model=UserResponse)
def assign_role(user_id: str, body: AssignRoleRequest, service: RBACService = Depends(get_service)):
    return _user_to_response(service.assign_role(user_id=user_id, role_id=body.role_id))


@router.put("/users/{user_id}/roles", response_model=UserResponse)
def replace_user_roles(user_id: str, body: ReplaceRolesRequest, service: RBACService = Depends(get_service)):
    return _user_to_response(service.replace_user_roles(user_id, body.role_ids))


@router.delete("/users/{user_id}/roles/{role_id}", response_model=UserResponse)
def remove_role(user_id: str, role_id: str, service: RBACService = Depends(get_service)):
    return _user_to_response(service.remove_role(user_id=user_id, role_id=role_id))


@router.get("/users/{user_id}/permissions", response_model=EffectivePermissionsResponse)
def user_permissions(user_id: str, service: RBACService = Depends(get_service)):
    permissions = service.get_effective_permissions(user_id)
    return EffectivePermissionsResponse(user_id=user_id, permissions=_sorted_permission_schemas(permissions))


# ==== Roles ===============================================================
@router.get("/roles", response_model=list[RoleResponse])
def list_roles(name: str | None = Query(default=None), service: RBACService = Depends(get_service)):
    return [_role_to_response(r) for r in service.search_roles(name)]


@router.get("/roles/count", response_model=CountResponse)
def count_roles(service: RBACService = Depends(get_service)):
    return CountResponse(count=service.count_roles())


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(body: CreateRoleRequest, service: RBACService = Depends(get_service)):
    permissions = [Permission(resource=p.resource, action=p.action) for p in body.permissions]
    return _role_to_response(service.create_role(name=body.name, permissions=permissions))


@router.get("/roles/{role_id}", response_model=RoleResponse)
def get_role(role_id: str, service: RBACService = Depends(get_service)):
    return _role_to_response(service.get_role(role_id))


@router.patch("/roles/{role_id}", response_model=RoleResponse)
def rename_role(role_id: str, body: RenameRequest, service: RBACService = Depends(get_service)):
    return _role_to_response(service.rename_role(role_id, body.name))


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: str, service: RBACService = Depends(get_service)):
    service.delete_role(role_id)


@router.post("/roles/{role_id}/permissions", response_model=RoleResponse)
def add_permission(role_id: str, body: PermissionSchema, service: RBACService = Depends(get_service)):
    permission = Permission(resource=body.resource, action=body.action)
    return _role_to_response(service.add_permission(role_id=role_id, permission=permission))


@router.put("/roles/{role_id}/permissions", response_model=RoleResponse)
def replace_role_permissions(role_id: str, body: ReplacePermissionsRequest, service: RBACService = Depends(get_service)):
    permissions = [Permission(resource=p.resource, action=p.action) for p in body.permissions]
    return _role_to_response(service.replace_role_permissions(role_id, permissions))


@router.delete("/roles/{role_id}/permissions", response_model=RoleResponse)
def remove_permission(role_id: str, body: PermissionSchema, service: RBACService = Depends(get_service)):
    permission = Permission(resource=body.resource, action=body.action)
    return _role_to_response(service.remove_permission(role_id=role_id, permission=permission))


@router.get("/roles/{role_id}/users", response_model=list[UserResponse])
def users_with_role(role_id: str, service: RBACService = Depends(get_service)):
    return [_user_to_response(u) for u in service.list_users_with_role(role_id)]


# ==== Permission check & system ===========================================
@router.post("/check-permission", response_model=PermissionCheckResponse)
def check_permission(body: PermissionCheckRequest, service: RBACService = Depends(get_service)):
    allowed = service.can_user_perform_action(
        user_id=body.user_id, resource=body.resource, action=body.action
    )
    return PermissionCheckResponse(allowed=allowed)


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@router.get("/system/info", response_model=SystemInfoResponse)
def system_info(service: RBACService = Depends(get_service)):
    return SystemInfoResponse(
        name="RBAC Service (extended)",
        version=API_VERSION,
        users=service.count_users(),
        roles=service.count_roles(),
    )


@router.get("/system/audit", response_model=list[AuditEntryResponse])
def system_audit(limit: int = Query(default=50, ge=1, le=500), service: RBACService = Depends(get_service)):
    return [AuditEntryResponse(**entry) for entry in service.get_audit_log(limit)]
