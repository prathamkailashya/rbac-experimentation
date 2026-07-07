"""Dependency wiring.

A single seeded ``RBACService`` is built when this module is first imported and
handed to the routes through FastAPI's dependency injection (``Depends``).
Using a dependency rather than a bare global means tests can swap in a fresh
service via ``app.dependency_overrides``.
"""

from app.seed import build_seeded_service
from app.services import RBACService

service: RBACService = build_seeded_service()


def get_service() -> RBACService:
    return service
