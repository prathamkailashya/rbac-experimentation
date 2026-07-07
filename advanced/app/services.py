"""Business logic for the advanced RBAC service.

Everything is scoped by ``tenant_id`` (multi-tenancy): a caller only ever sees or
touches data in their own tenant. Effective permissions follow the role
hierarchy (a role inherits its parents' permissions). The permission check is
unchanged in spirit -- it is still "is this permission in the user's effective
set" -- only the way we build that set now includes inheritance.
"""

from uuid import uuid4

from advanced.app.auth import hash_password, verify_password
from advanced.app.errors import ConflictError, NotFoundError, ValidationError
from advanced.app.models import Permission, Role, User
from advanced.app.storage import InMemoryStore


def _clean(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError("Value must not be blank")
    return cleaned


class RBACService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    # ---- Roles (tenant-scoped) -------------------------------------------
    def create_role(self, tenant_id, name, permissions=None, parent_ids=None) -> Role:
        name = _clean(name)
        for role in self.store.roles.values():
            if role.tenant_id == tenant_id and role.name.lower() == name.lower():
                raise ConflictError(f"Role '{name}' already exists in this tenant")
        parents = set(parent_ids or [])
        for parent_id in parents:
            self.get_role(tenant_id, parent_id)  # parents must exist in the tenant
        role = Role(
            id=str(uuid4()),
            tenant_id=tenant_id,
            name=name,
            permissions=set(permissions or []),
            parent_ids=parents,
        )
        self.store.roles[role.id] = role
        return role

    def get_role(self, tenant_id, role_id) -> Role:
        role = self.store.roles.get(role_id)
        if role is None or role.tenant_id != tenant_id:  # isolation: other tenants are invisible
            raise NotFoundError("Role", role_id)
        return role

    def list_roles(self, tenant_id) -> list[Role]:
        return [r for r in self.store.roles.values() if r.tenant_id == tenant_id]

    def add_permission(self, tenant_id, role_id, permission: Permission) -> Role:
        role = self.get_role(tenant_id, role_id)
        role.permissions.add(permission)
        return role

    def set_role_parents(self, tenant_id, role_id, parent_ids) -> Role:
        role = self.get_role(tenant_id, role_id)
        for parent_id in parent_ids:
            self.get_role(tenant_id, parent_id)                 # exists in tenant
            if role_id in self._reachable(parent_id):           # cycle guard
                raise ValidationError("Setting this parent would create a cycle")
        role.parent_ids = set(parent_ids)
        return role

    def _reachable(self, start_id) -> set[str]:
        """All role ids reachable by following parent_ids from start (incl. start)."""
        seen, stack = set(), [start_id]
        while stack:
            rid = stack.pop()
            if rid in seen:
                continue
            seen.add(rid)
            role = self.store.roles.get(rid)
            if role is not None:
                stack.extend(role.parent_ids)
        return seen

    # ---- Users (tenant-scoped) -------------------------------------------
    def create_user(self, tenant_id, name, password, role_ids=None) -> User:
        name = _clean(name)
        # Login names are global identities, so they must be globally unique.
        for user in self.store.users.values():
            if user.name.lower() == name.lower():
                raise ConflictError(f"User name '{name}' already exists")
        role_ids = set(role_ids or [])
        for role_id in role_ids:
            self.get_role(tenant_id, role_id)  # can only grant same-tenant roles
        user = User(
            id=str(uuid4()),
            tenant_id=tenant_id,
            name=name,
            password_hash=hash_password(_clean(password)),
            role_ids=role_ids,
        )
        self.store.users[user.id] = user
        return user

    def get_user(self, tenant_id, user_id) -> User:
        user = self.store.users.get(user_id)
        if user is None or user.tenant_id != tenant_id:
            raise NotFoundError("User", user_id)
        return user

    def list_users(self, tenant_id) -> list[User]:
        return [u for u in self.store.users.values() if u.tenant_id == tenant_id]

    def assign_role(self, tenant_id, user_id, role_id) -> User:
        user = self.get_user(tenant_id, user_id)
        self.get_role(tenant_id, role_id)  # role must be in the same tenant
        user.role_ids.add(role_id)
        return user

    # ---- Auth ------------------------------------------------------------
    def authenticate(self, name, password) -> User | None:
        for user in self.store.users.values():
            if user.name.lower() == name.lower() and verify_password(password, user.password_hash):
                return user
        return None

    # ---- Effective permissions (with hierarchy) --------------------------
    def _role_effective(self, role_id, seen: set[str]) -> set[Permission]:
        if role_id in seen:                 # already expanded (or cycle) -> skip
            return set()
        seen.add(role_id)
        role = self.store.roles.get(role_id)
        if role is None:
            return set()
        permissions = set(role.permissions)
        for parent_id in role.parent_ids:   # inherit from parents
            permissions |= self._role_effective(parent_id, seen)
        return permissions

    def effective_permissions(self, tenant_id, user_id) -> set[Permission]:
        user = self.get_user(tenant_id, user_id)
        permissions: set[Permission] = set()
        seen: set[str] = set()
        for role_id in user.role_ids:
            permissions |= self._role_effective(role_id, seen)
        return permissions

    def can_user_perform_action(self, tenant_id, user_id, resource, action) -> bool:
        user = self.store.users.get(user_id)
        # Unknown user, or a user in another tenant -> denied (fail closed).
        if user is None or user.tenant_id != tenant_id:
            return False
        required = Permission(resource=resource, action=action)
        return required in self.effective_permissions(tenant_id, user_id)
