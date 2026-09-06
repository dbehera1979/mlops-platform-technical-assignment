"""Domain exceptions and a single consistent JSON error envelope.

Every error response has the same shape:
    {"error": {"code": "...", "message": "...", "details": {...}}}
so the Angular client can branch on `error.code` instead of parsing
prose, and so error handling is uniform across every endpoint.
"""
from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code: int = 400
    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(DomainError):
    """Used for idempotency collisions, optimistic-concurrency losses,
    and 'environment busy' serialization (architecture.md Q2)."""

    status_code = 409
    code = "CONFLICT"


class ValidationFailedError(DomainError):
    status_code = 422
    code = "VALIDATION_FAILED"


class PromotionGateError(DomainError):
    """Raised when a deployment/promotion violates a governance gate,
    e.g. deploying an unapproved version to PRODUCTION."""

    status_code = 409
    code = "PROMOTION_GATE_VIOLATION"


class AuthorizationError(DomainError):
    status_code = 403
    code = "FORBIDDEN"


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )
