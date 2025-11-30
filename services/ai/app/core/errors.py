"""Domain and infrastructure exceptions with secure error handling."""
import logging
import traceback
from typing import Any, Dict, Optional, Union

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# Custom Exception Classes
# =============================================================================

class BaseAppException(Exception):
    """Base exception for all application exceptions."""

    def __init__(
        self,
        message: str,
        code: str = "APP_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(BaseAppException):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str = "Authentication failed",
        code: str = "AUTH_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class AuthorizationError(BaseAppException):
    """Raised when user lacks permission for an action."""

    def __init__(
        self,
        message: str = "You don't have permission to perform this action",
        code: str = "FORBIDDEN",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class NotFoundError(BaseAppException):
    """Raised when a resource is not found."""

    def __init__(
        self,
        resource: str = "Resource",
        identifier: Optional[str] = None,
        code: str = "NOT_FOUND",
    ):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with identifier '{identifier}' not found"
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictError(BaseAppException):
    """Raised when there's a conflict (e.g., duplicate resource)."""

    def __init__(
        self,
        message: str = "Resource already exists",
        code: str = "CONFLICT",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ValidationError_(BaseAppException):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "VALIDATION_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class RateLimitError(BaseAppException):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
        code: str = "RATE_LIMIT_EXCEEDED",
        retry_after: Optional[int] = None,
    ):
        details = {"retry_after": retry_after} if retry_after else {}
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class DatabaseError(BaseAppException):
    """Raised when a database operation fails."""

    def __init__(
        self,
        message: str = "A database error occurred",
        code: str = "DATABASE_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class ExternalServiceError(BaseAppException):
    """Raised when an external service call fails."""

    def __init__(
        self,
        service: str = "External service",
        message: Optional[str] = None,
        code: str = "EXTERNAL_SERVICE_ERROR",
    ):
        msg = message or f"{service} is currently unavailable"
        super().__init__(
            message=msg,
            code=code,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# =============================================================================
# Error Response Builder
# =============================================================================

def build_error_response(
    message: str,
    code: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    include_details: bool = False,
) -> JSONResponse:
    """
    Build a standardized error response.

    Args:
        message: User-friendly error message
        code: Error code for client handling
        status_code: HTTP status code
        details: Additional error details (only included in non-production)
        request_id: Optional request ID for tracking
        include_details: Whether to include detailed info

    Returns:
        JSONResponse with error information
    """
    content: Dict[str, Any] = {
        "error": {
            "message": message,
            "code": code,
        }
    }

    if request_id:
        content["error"]["request_id"] = request_id

    if include_details and details:
        content["error"]["details"] = details

    return JSONResponse(
        status_code=status_code,
        content=content,
    )


# =============================================================================
# Exception Handlers
# =============================================================================

def get_request_id(request: Request) -> Optional[str]:
    """Extract request ID from headers if present."""
    return request.headers.get("X-Request-ID")


def is_production() -> bool:
    """Check if running in production environment."""
    import os
    return os.getenv("ENVIRONMENT", "development") == "production"


async def base_app_exception_handler(
    request: Request,
    exc: BaseAppException,
) -> JSONResponse:
    """Handle all BaseAppException and subclasses."""
    request_id = get_request_id(request)

    # Log the error
    logger.warning(
        f"Application error: {exc.code} - {exc.message}",
        extra={
            "request_id": request_id,
            "error_code": exc.code,
            "path": request.url.path,
        }
    )

    return build_error_response(
        message=exc.message,
        code=exc.code,
        status_code=exc.status_code,
        details=exc.details,
        request_id=request_id,
        include_details=not is_production(),
    )


async def validation_exception_handler(
    request: Request,
    exc: ValidationError,
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    request_id = get_request_id(request)

    # Extract validation errors in a safe format
    errors = []
    for error in exc.errors():
        # Sanitize error messages - don't expose internal details
        field = ".".join(str(loc) for loc in error.get("loc", []))
        message = error.get("msg", "Validation error")
        errors.append({"field": field, "message": message})

    logger.info(
        f"Validation error on {request.url.path}",
        extra={"request_id": request_id, "errors": errors}
    )

    # In production, return generic message
    if is_production():
        return build_error_response(
            message="Invalid input data",
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            request_id=request_id,
        )

    return build_error_response(
        message="Validation failed",
        code="VALIDATION_ERROR",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors},
        request_id=request_id,
        include_details=True,
    )


async def sqlalchemy_exception_handler(
    request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    """Handle SQLAlchemy database errors."""
    request_id = get_request_id(request)

    # Log the full error for debugging (never expose to user)
    logger.error(
        f"Database error: {type(exc).__name__}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "error_type": type(exc).__name__,
        },
        exc_info=True,  # Include traceback in logs
    )

    # Always return generic message to user
    return build_error_response(
        message="A database error occurred. Please try again later.",
        code="DATABASE_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=request_id,
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle all unhandled exceptions."""
    request_id = get_request_id(request)

    # Log the full error with traceback (never expose to user)
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
        },
        exc_info=True,  # Include full traceback in logs
    )

    # In production, return generic error
    if is_production():
        return build_error_response(
            message="An unexpected error occurred. Please try again later.",
            code="INTERNAL_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request_id=request_id,
        )

    # In development, include more details for debugging
    return build_error_response(
        message="An unexpected error occurred",
        code="INTERNAL_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        },
        request_id=request_id,
        include_details=True,
    )


async def http_exception_handler(
    request: Request,
    exc: Any,  # HTTPException
) -> JSONResponse:
    """Handle FastAPI HTTPException."""
    from fastapi import HTTPException

    if not isinstance(exc, HTTPException):
        return await generic_exception_handler(request, exc)

    request_id = get_request_id(request)

    # Map common status codes to error codes
    code_mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }

    error_code = code_mapping.get(exc.status_code, "HTTP_ERROR")

    return build_error_response(
        message=str(exc.detail) if not is_production() or exc.status_code < 500
        else "An error occurred",
        code=error_code,
        status_code=exc.status_code,
        request_id=request_id,
    )


# =============================================================================
# Register Exception Handlers Function
# =============================================================================

def register_exception_handlers(app: Any) -> None:
    """
    Register all exception handlers with the FastAPI app.

    Args:
        app: FastAPI application instance
    """
    from fastapi import HTTPException

    # Custom application exceptions
    app.add_exception_handler(BaseAppException, base_app_exception_handler)

    # Pydantic validation errors
    app.add_exception_handler(ValidationError, validation_exception_handler)

    # SQLAlchemy database errors
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)

    # FastAPI HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Generic catch-all for unhandled exceptions
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Exception handlers registered successfully")
