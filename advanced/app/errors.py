"""Domain error types (same pattern as the other versions).

Auth failures (401/403) are raised as FastAPI ``HTTPException`` in the auth
layer; these classes cover the RBAC domain (404/409/422).
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
        super().__init__(f"{entity} '{entity_id}' not found")
