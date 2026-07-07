"""Dependency wiring: the service, the current user, and permission guards.

  * get_service       -> the seeded singleton (overridable in tests)
  * get_current_user  -> decodes the Bearer token into the User (401 if bad)
  * require_permission -> a guard that also checks the user HAS a permission (403)

The token carries the tenant, so once we resolve the current user every request
is automatically scoped to that user's tenant.
"""

from fastapi import Depends, HTTPException, status

from advanced.app.auth import decode_token, oauth2_scheme
from advanced.app.models import User
from advanced.app.seed import build_seeded_service
from advanced.app.services import RBACService

service: RBACService = build_seeded_service()


def get_service() -> RBACService:
    return service


def get_current_user(
    token: str = Depends(oauth2_scheme),
    service: RBACService = Depends(get_service),
) -> User:
    payload = decode_token(token)
    user = service.store.users.get(payload.get("sub"))
    # Reject if the user vanished or the token's tenant no longer matches.
    if user is None or user.tenant_id != payload.get("tenant"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user


def require_permission(resource: str, action: str):
    """Build a dependency that requires the caller to hold (resource, action)."""

    def guard(
        user: User = Depends(get_current_user),
        service: RBACService = Depends(get_service),
    ) -> User:
        if not service.can_user_perform_action(user.tenant_id, user.id, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission {resource}:{action}",
            )
        return user

    return guard
