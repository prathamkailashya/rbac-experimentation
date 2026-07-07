"""Domain models for the advanced (in-memory) RBAC service.

Adds three things on top of the basic model:
  * ``tenant_id`` on Role and User  -> multi-tenancy (data is scoped per tenant)
  * ``parent_ids`` on Role          -> role hierarchy (a role inherits its parents)
  * ``password_hash`` on User       -> OAuth login (the user is the auth account)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Permission:
    resource: str
    action: str


@dataclass
class Role:
    id: str
    tenant_id: str
    name: str
    permissions: set[Permission] = field(default_factory=set)
    parent_ids: set[str] = field(default_factory=set)   # role hierarchy


@dataclass
class User:
    id: str
    tenant_id: str
    name: str
    password_hash: str
    role_ids: set[str] = field(default_factory=set)
