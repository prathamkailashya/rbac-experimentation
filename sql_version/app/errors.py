"""Centralized error types for the SQL version.

Identical in spirit to the in-memory version's ``app/errors.py``: every
expected failure carries an HTTP ``status_code`` and a short ``code``, and
``main.py`` renders them in one consistent JSON shape.
"""


class AppError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"

    def __init__(self, entity: str, entity_id: str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} '{entity_id}' not found")
