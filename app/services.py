"""Business logic for the extended RBAC service.

Same layering as the original: routes -> service -> storage. The service owns
all rules (validation, normalization, uniqueness, the permission check) and
never imports FastAPI.

Beyond the original it adds: get-by-id, rename, replace-roles,
replace-permissions, effective-permission listing, users-of-a-role, search,
counts, an audit log, and a small effective-permission cache.
"""

from uuid import uuid4

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import Permission, Role, User, utcnow
from app.storage import InMemoryStore

# Re-exported so existing imports (`from app.services import NotFoundError`) and
# the copied test suite keep working.
__all__ = ["RBACService", "NotFoundError", "ConflictError", "ValidationError"]


def clean_name(name: str) -> str:
    """Trim a name and reject blank / whitespace-only values."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValidationError("Name must not be blank")
    return cleaned


def clean_permission(resource: str, action: str) -> Permission:
    """Trim and lowercase a permission so matching is case-insensitive."""
    r = (resource or "").strip().lower()
    a = (action or "").strip().lower()
    if not r or not a:
        raise ValidationError("Permission resource and action must not be blank")
    return Permission(resource=r, action=a)


class RBACService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    # ---- internal helpers -------------------------------------------------
    def _log(self, action: str, detail: dict) -> None:
        self.store.audit_log.append(
            {"timestamp": utcnow().isoformat(), "action": action, "detail": detail}
        )

    def _invalidate_cache(self, user_id: str | None = None) -> None:
        """Drop cached effective permissions. ``None`` clears everything."""
        if user_id is None:
            self.store.permission_cache.clear()
        else:
            self.store.permission_cache.pop(user_id, None)

    def _assert_unique_user_name(self, name: str, exclude_id: str | None = None) -> None:
        lowered = name.lower()
        for user in self.store.users.values():
            if user.id != exclude_id and user.name.lower() == lowered:
                raise ConflictError(f"User name '{name}' already exists")

    def _assert_unique_role_name(self, name: str, exclude_id: str | None = None) -> None:
        lowered = name.lower()
        for role in self.store.roles.values():
            if role.id != exclude_id and role.name.lower() == lowered:
                raise ConflictError(f"Role name '{name}' already exists")

    # ---- Roles ------------------------------------------------------------
    def create_role(self, name: str, permissions: list[Permission] | None = None) -> Role:
        cleaned = clean_name(name)
        self._assert_unique_role_name(cleaned)
        perms = {clean_permission(p.resource, p.action) for p in (permissions or [])}
        role = Role(id=str(uuid4()), name=cleaned, permissions=perms)
        self.store.roles[role.id] = role
        self._log("create_role", {"role_id": role.id, "name": cleaned})
        return role

    def list_roles(self) -> list[Role]:
        return list(self.store.roles.values())

    def search_roles(self, name: str | None) -> list[Role]:
        roles = self.list_roles()
        if name and name.strip():
            query = name.strip().lower()
            roles = [r for r in roles if query in r.name.lower()]
        return roles

    def get_role(self, role_id: str) -> Role:
        role = self.store.roles.get(role_id)
        if role is None:
            raise NotFoundError("Role", role_id)
        return role

    def rename_role(self, role_id: str, new_name: str) -> Role:
        role = self.get_role(role_id)
        cleaned = clean_name(new_name)
        self._assert_unique_role_name(cleaned, exclude_id=role_id)
        role.name = cleaned
        role.updated_at = utcnow()
        self._log("rename_role", {"role_id": role_id, "name": cleaned})
        return role

    def add_permission(self, role_id: str, permission: Permission) -> Role:
        role = self.get_role(role_id)
        role.permissions.add(clean_permission(permission.resource, permission.action))
        role.updated_at = utcnow()
        self._invalidate_cache()  # any holder of this role is affected
        self._log("add_permission", {"role_id": role_id, "permission": [permission.resource, permission.action]})
        return role

    def remove_permission(self, role_id: str, permission: Permission) -> Role:
        role = self.get_role(role_id)
        role.permissions.discard(clean_permission(permission.resource, permission.action))
        role.updated_at = utcnow()
        self._invalidate_cache()
        self._log("remove_permission", {"role_id": role_id, "permission": [permission.resource, permission.action]})
        return role

    def replace_role_permissions(self, role_id: str, permissions: list[Permission]) -> Role:
        role = self.get_role(role_id)
        role.permissions = {clean_permission(p.resource, p.action) for p in permissions}
        role.updated_at = utcnow()
        self._invalidate_cache()
        self._log("replace_role_permissions", {"role_id": role_id, "count": len(role.permissions)})
        return role

    def delete_role(self, role_id: str) -> None:
        self.get_role(role_id)  # 404 if missing
        del self.store.roles[role_id]
        for user in self.store.users.values():
            user.role_ids.discard(role_id)  # cascade: drop dangling references
        self._invalidate_cache()
        self._log("delete_role", {"role_id": role_id})

    def list_users_with_role(self, role_id: str) -> list[User]:
        self.get_role(role_id)  # 404 if the role does not exist
        return [u for u in self.store.users.values() if role_id in u.role_ids]

    # ---- Users ------------------------------------------------------------
    def create_user(self, name: str, role_ids: list[str] | None = None) -> User:
        cleaned = clean_name(name)
        self._assert_unique_user_name(cleaned)
        role_ids = role_ids or []
        for role_id in role_ids:
            self.get_role(role_id)  # validate each role exists
        user = User(id=str(uuid4()), name=cleaned, role_ids=set(role_ids))
        self.store.users[user.id] = user
        self._invalidate_cache(user.id)
        self._log("create_user", {"user_id": user.id, "name": cleaned})
        return user

    def list_users(self) -> list[User]:
        return list(self.store.users.values())

    def search_users(self, name: str | None) -> list[User]:
        users = self.list_users()
        if name and name.strip():
            query = name.strip().lower()
            users = [u for u in users if query in u.name.lower()]
        return users

    def get_user(self, user_id: str) -> User:
        user = self.store.users.get(user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        return user

    def rename_user(self, user_id: str, new_name: str) -> User:
        user = self.get_user(user_id)
        cleaned = clean_name(new_name)
        self._assert_unique_user_name(cleaned, exclude_id=user_id)
        user.name = cleaned
        user.updated_at = utcnow()
        self._log("rename_user", {"user_id": user_id, "name": cleaned})
        return user

    def assign_role(self, user_id: str, role_id: str) -> User:
        user = self.get_user(user_id)
        self.get_role(role_id)  # validate the role exists
        user.role_ids.add(role_id)  # idempotent
        user.updated_at = utcnow()
        self._invalidate_cache(user_id)
        self._log("assign_role", {"user_id": user_id, "role_id": role_id})
        return user

    def remove_role(self, user_id: str, role_id: str) -> User:
        user = self.get_user(user_id)
        user.role_ids.discard(role_id)  # idempotent
        user.updated_at = utcnow()
        self._invalidate_cache(user_id)
        self._log("remove_role", {"user_id": user_id, "role_id": role_id})
        return user

    def replace_user_roles(self, user_id: str, role_ids: list[str]) -> User:
        user = self.get_user(user_id)
        for role_id in role_ids:
            self.get_role(role_id)  # validate all before replacing (all-or-nothing)
        user.role_ids = set(role_ids)
        user.updated_at = utcnow()
        self._invalidate_cache(user_id)
        self._log("replace_user_roles", {"user_id": user_id, "role_ids": sorted(set(role_ids))})
        return user

    def delete_user(self, user_id: str) -> None:
        self.get_user(user_id)  # 404 if missing
        del self.store.users[user_id]
        self._invalidate_cache(user_id)
        self._log("delete_user", {"user_id": user_id})

    # ---- Permissions & checking ------------------------------------------
    def get_effective_permissions(self, user_id: str) -> set[Permission]:
        """Union of all permissions across a user's roles, memoized per user."""
        if user_id in self.store.permission_cache:
            return self.store.permission_cache[user_id]
        user = self.get_user(user_id)  # 404 if missing
        permissions: set[Permission] = set()
        for role_id in user.role_ids:
            role = self.store.roles.get(role_id)
            if role is not None:
                permissions |= role.permissions
        self.store.permission_cache[user_id] = permissions
        return permissions

    def can_user_perform_action(self, user_id: str, resource: str, action: str) -> bool:
        if user_id not in self.store.users:
            return False
        required = Permission(resource=(resource or "").strip().lower(), action=(action or "").strip().lower())
        return required in self.get_effective_permissions(user_id)

    # ---- Stats & audit ----------------------------------------------------
    def count_users(self) -> int:
        return len(self.store.users)

    def count_roles(self) -> int:
        return len(self.store.roles)

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        return self.store.audit_log[-limit:]
