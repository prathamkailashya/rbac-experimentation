"""Seed data: two tenants, showing hierarchy and isolation.

Tenant 'acme':
    viewer  -> documents:read
    editor  -> documents:write        (inherits viewer)
    admin   -> roles:write, users:write (inherits editor)
    alice = admin,  bob = editor        (passwords below)

Tenant 'globex':
    gviewer -> documents:read
    carol   = gviewer

Because of the hierarchy, Alice (admin) effectively has documents:read too, even
though it is only listed on viewer.
"""

from advanced.app.models import Permission
from advanced.app.services import RBACService
from advanced.app.storage import InMemoryStore

# Demo credentials (username -> password).
CREDENTIALS = {"alice": "alice-pw", "bob": "bob-pw", "carol": "carol-pw"}


def build_seeded_service() -> RBACService:
    service = RBACService(InMemoryStore())

    # --- Tenant: acme (with a role hierarchy) ---
    viewer = service.create_role("acme", "viewer", [Permission("documents", "read")])
    editor = service.create_role(
        "acme", "editor", [Permission("documents", "write")], parent_ids=[viewer.id]
    )
    admin = service.create_role(
        "acme",
        "admin",
        [Permission("roles", "write"), Permission("users", "write")],
        parent_ids=[editor.id],
    )
    service.create_user("acme", "alice", "alice-pw", [admin.id])
    service.create_user("acme", "bob", "bob-pw", [editor.id])

    # --- Tenant: globex (isolated from acme) ---
    gviewer = service.create_role("globex", "gviewer", [Permission("documents", "read")])
    service.create_user("globex", "carol", "carol-pw", [gviewer.id])

    return service
