"""Authentication service - business logic for user authentication."""
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    settings,
    validate_refresh_token,
    verify_password,
)
from app.db.models import User, UserRole
from app.repositories.user_repo import UserRepository
from app.schemas.auth_schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)


class AuthService:
    """Service for handling user authentication operations."""

    def __init__(self, db: Session):
        """
        Initialize the auth service with a database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db
        self.user_repo = UserRepository(db)

    def register(self, request: RegisterRequest) -> AuthResponse:
        """
        Register a new user.

        Args:
            request: The registration request containing email, password, and optional display name.

        Returns:
            AuthResponse containing user info and tokens.

        Raises:
            HTTPException: 409 if email already exists, 400 for invalid input.
        """
        # Check if email already exists
        if self.user_repo.email_exists(request.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )

        # Hash the password
        hashed_password = get_password_hash(request.password)

        # Create the user
        user = self.user_repo.create(
            email=request.email,
            hashed_password=hashed_password,
            display_name=request.display_name,
            role=UserRole.STUDENT,
        )

        # Generate tokens
        tokens = self._create_tokens(user)

        return AuthResponse(
            user=UserResponse(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=user.role.value if isinstance(
                    user.role, UserRole) else user.role,
            ),
            tokens=tokens,
        )

    def login(self, request: LoginRequest) -> AuthResponse:
        """
        Authenticate a user and return tokens.

        Args:
            request: The login request containing email and password.

        Returns:
            AuthResponse containing user info and tokens.

        Raises:
            HTTPException: 401 if credentials are invalid.
        """
        # Find user by email
        user = self.user_repo.get_by_email(request.email)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Verify password
        if not verify_password(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Generate tokens
        tokens = self._create_tokens(user)

        return AuthResponse(
            user=UserResponse(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=user.role.value if isinstance(
                    user.role, UserRole) else user.role,
            ),
            tokens=tokens,
        )

    def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """
        Refresh access and refresh tokens using a valid refresh token.

        Args:
            refresh_token: The refresh token to validate.

        Returns:
            New TokenResponse with fresh tokens.

        Raises:
            HTTPException: 401 if refresh token is invalid.
        """
        # Validate the refresh token
        payload = validate_refresh_token(refresh_token)

        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Verify the user still exists
        user = self.user_repo.get_by_id(payload.sub)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Generate new tokens
        return self._create_tokens(user)

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get a user by their ID.

        Args:
            user_id: The user's unique identifier.

        Returns:
            The User if found, None otherwise.
        """
        return self.user_repo.get_by_id(user_id)

    def _create_tokens(self, user: User) -> TokenResponse:
        """
        Create access and refresh tokens for a user.

        Args:
            user: The user to create tokens for.

        Returns:
            TokenResponse with access and refresh tokens.
        """
        role = user.role.value if isinstance(
            user.role, UserRole) else user.role

        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            role=role,
        )

        refresh_token = create_refresh_token(
            user_id=user.id,
            email=user.email,
            role=role,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


def get_auth_service(db: Session) -> AuthService:
    """
    Factory function to create an AuthService instance.

    Args:
        db: SQLAlchemy database session.

    Returns:
        A new AuthService instance.
    """
    return AuthService(db)
