"""Pydantic schemas: the public HTTP API contract (extended)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PermissionSchema(BaseModel):
    resource: str = Field(min_length=1, examples=["documents"])
    action: str = Field(min_length=1, examples=["read"])


# ---- Requests ------------------------------------------------------------
class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, examples=["Alice"])
    role_ids: list[str] = Field(default_factory=list)


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=1, examples=["admin"])
    permissions: list[PermissionSchema] = Field(default_factory=list)


class AssignRoleRequest(BaseModel):
    role_id: str = Field(min_length=1)


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, examples=["new-name"])


class ReplaceRolesRequest(BaseModel):
    role_ids: list[str] = Field(default_factory=list)


class ReplacePermissionsRequest(BaseModel):
    permissions: list[PermissionSchema] = Field(default_factory=list)


class PermissionCheckRequest(BaseModel):
    user_id: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    action: str = Field(min_length=1)


# ---- Responses -----------------------------------------------------------
class UserResponse(BaseModel):
    id: str
    name: str
    role_ids: list[str]
    created_at: datetime
    updated_at: datetime


class RoleResponse(BaseModel):
    id: str
    name: str
    permissions: list[PermissionSchema]
    created_at: datetime
    updated_at: datetime


class PermissionCheckResponse(BaseModel):
    allowed: bool


class EffectivePermissionsResponse(BaseModel):
    user_id: str
    permissions: list[PermissionSchema]


class CountResponse(BaseModel):
    count: int


class SystemInfoResponse(BaseModel):
    name: str
    version: str
    users: int
    roles: int


class HealthResponse(BaseModel):
    status: str


class AuditEntryResponse(BaseModel):
    timestamp: str
    action: str
    detail: dict[str, Any]
