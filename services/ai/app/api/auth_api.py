"""Authentication API controller - HTTP endpoints for auth operations."""
from fastapi import APIRouter, Depends, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.core.config import TokenPayload
from app.core.errors import (
    AuthenticationError,
    NotFoundError,
    ConflictError,
)
from app.schemas.auth_schemas import (
    AuthResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService, get_auth_service

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Rate limiter for auth endpoints
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "User successfully registered"},
        400: {"description": "Invalid input data"},
        409: {"description": "User with this email already exists"},
        429: {"description": "Too many registration attempts"},
    },
)
@limiter.limit("5/minute")  # Rate limit: 5 registrations per minute per IP
def register(
    request: Request,
    data: RegisterRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """
    Register a new user account.

    Creates a new user with the provided email, password, and optional display name.
    Returns the user information along with access and refresh tokens.

    - **email**: Valid email address (must be unique)
    - **password**: Strong password (min 12 chars, must contain uppercase, lowercase, digit, and special character)
    - **display_name**: Optional display name (sanitized for security)

    Rate limited to 5 attempts per minute per IP address.
    """
    auth_service = get_auth_service(db)
    return auth_service.register(data)


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Login successful"},
        400: {"description": "Invalid input data"},
        401: {"description": "Invalid email or password"},
        429: {"description": "Too many login attempts"},
    },
)
@limiter.limit("10/minute")  # Rate limit: 10 login attempts per minute per IP
def login(
    request: Request,
    data: LoginRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """
    Authenticate a user and obtain tokens.

    Validates the user's email and password, then returns user information
    along with access and refresh tokens.

    - **email**: Registered email address
    - **password**: User's password

    Rate limited to 10 attempts per minute per IP address.
    """
    auth_service = get_auth_service(db)
    return auth_service.login(data)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Tokens refreshed successfully"},
        401: {"description": "Invalid or expired refresh token"},
        429: {"description": "Too many refresh attempts"},
    },
)
@limiter.limit("30/minute")  # Rate limit: 30 refreshes per minute per IP
def refresh_tokens(
    request: Request,
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Refresh access and refresh tokens.

    Uses a valid refresh token to obtain new access and refresh tokens.
    The old refresh token should be discarded after this call.

    - **refresh_token**: Valid refresh token

    Rate limited to 30 attempts per minute per IP address.
    """
    auth_service = get_auth_service(db)
    return auth_service.refresh_tokens(data.refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Current user information"},
        401: {"description": "Not authenticated"},
    },
)
def get_current_user_info(
    current_user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Get the current authenticated user's information.

    Requires a valid access token in the Authorization header.
    """
    auth_service = get_auth_service(db)
    user = auth_service.get_user_by_id(current_user.sub)

    if user is None:
        raise NotFoundError(resource="User", identifier=current_user.sub)

    from app.db.models import UserRole
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value if isinstance(user.role, UserRole) else user.role,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Logout successful"},
    },
)
def logout() -> dict:
    """
    Logout the current user.

    Note: Since JWTs are stateless, this endpoint serves as a signal for
    the client to discard their tokens. For more robust logout, consider
    implementing a token blacklist.
    """
    return {"message": "Successfully logged out"}
