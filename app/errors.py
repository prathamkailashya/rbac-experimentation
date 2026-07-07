"""Centralized error types.

Every expected failure is an ``AppError`` subclass carrying an HTTP
``status_code`` and a short machine-readable ``code``. ``main.py`` registers a
single handler that turns any ``AppError`` into a consistent JSON body:

    {"error": {"code": "not_found", "message": "User 'x' not found"}}

This keeps error handling in one place instead of scattered try/except blocks.
"""


class AppError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ValidationError(AppError):
    """Input is malformed (blank name, empty permission, ...)."""

    status_code = 422
    code = "validation_error"


class ConflictError(AppError):
    """The request conflicts with existing state (duplicate name)."""

    status_code = 409
    code = "conflict"


class NotFoundError(AppError):
    """A referenced user or role does not exist.

    Keeps the ``(entity, entity_id)`` constructor of the original project so the
    copied tests and service code continue to work unchanged.
    """

    status_code = 404
    code = "not_found"

    def __init__(self, entity: str, entity_id: str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} '{entity_id}' not found")
