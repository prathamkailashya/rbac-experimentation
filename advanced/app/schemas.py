"""Pydantic request/response schemas for the advanced service."""

from pydantic import BaseModel, Field


class PermissionSchema(BaseModel):
    resource: str = Field(min_length=1)
    action: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=1)
    permissions: list[PermissionSchema] = Field(default_factory=list)
    parent_ids: list[str] = Field(default_factory=list)


class SetParentsRequest(BaseModel):
    parent_ids: list[str] = Field(default_factory=list)


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1)
    password: str = Field(min_length=1)
    role_ids: list[str] = Field(default_factory=list)


class AssignRoleRequest(BaseModel):
    role_id: str = Field(min_length=1)


class CheckRequest(BaseModel):
    user_id: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    action: str = Field(min_length=1)


class RoleResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    permissions: list[PermissionSchema]
    parent_ids: list[str]


class UserResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    role_ids: list[str]


class MeResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    permissions: list[PermissionSchema]


class CheckResponse(BaseModel):
    allowed: bool
