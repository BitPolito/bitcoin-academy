"""Authentication middleware for protecting routes."""
from functools import wraps
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import TokenPayload, validate_access_token
from app.db.models import UserRole


# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


class AuthenticationError(HTTPException):
    """Exception raised when authentication fails."""

    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(HTTPException):
    """Exception raised when authorization fails."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


async def get_token_from_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """
    Extract the JWT token from the Authorization header.

    Args:
        credentials: The HTTP Bearer credentials from the request.

    Returns:
        The token string if present, None otherwise.
    """
    if credentials is None:
        return None
    return credentials.credentials


async def get_current_user(
    token: Optional[str] = Depends(get_token_from_header),
) -> TokenPayload:
    """
    Validate the JWT token and return the current user's token payload.

    Args:
        token: The JWT token from the Authorization header.

    Returns:
        The validated TokenPayload containing user information.

    Raises:
        AuthenticationError: If the token is missing, invalid, or expired.
    """
    if token is None:
        raise AuthenticationError("Missing authentication token")

    payload = validate_access_token(token)
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    return payload


async def get_current_user_optional(
    token: Optional[str] = Depends(get_token_from_header),
) -> Optional[TokenPayload]:
    """
    Optionally validate the JWT token. Returns None if no token is provided.

    Args:
        token: The JWT token from the Authorization header.

    Returns:
        The validated TokenPayload if token is valid, None if no token.

    Raises:
        AuthenticationError: If the token is present but invalid.
    """
    if token is None:
        return None

    payload = validate_access_token(token)
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    return payload


def require_roles(allowed_roles: List[UserRole]) -> Callable:
    """
    Dependency factory that creates a role-based access control check.

    Args:
        allowed_roles: List of roles that are allowed to access the resource.

    Returns:
        A dependency function that validates the user's role.
    """
    async def role_checker(
        current_user: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        """
        Check if the current user has one of the allowed roles.

        Args:
            current_user: The current authenticated user's token payload.

        Returns:
            The validated TokenPayload if the user has an allowed role.

        Raises:
            AuthorizationError: If the user doesn't have an allowed role.
        """
        try:
            user_role = UserRole(current_user.role)
        except ValueError:
            raise AuthorizationError("Invalid user role")

        if user_role not in allowed_roles:
            raise AuthorizationError(
                f"Role '{current_user.role}' is not authorized for this resource"
            )

        return current_user

    return role_checker


# Pre-configured role dependencies
require_admin = require_roles([UserRole.ADMIN])
require_instructor = require_roles([UserRole.ADMIN, UserRole.INSTRUCTOR])
require_student = require_roles(
    [UserRole.ADMIN, UserRole.INSTRUCTOR, UserRole.STUDENT])


class CurrentUser:
    """
    Dependency class for getting the current user with role validation.

    Usage:
        @router.get("/protected")
        async def protected_route(
            user: TokenPayload = Depends(CurrentUser())
        ):
            return {"user_id": user.sub}

        @router.get("/admin-only")
        async def admin_route(
            user: TokenPayload = Depends(CurrentUser(roles=[UserRole.ADMIN]))
        ):
            return {"admin_id": user.sub}
    """

    def __init__(
        self,
        roles: Optional[List[UserRole]] = None,
        optional: bool = False
    ):
        """
        Initialize the CurrentUser dependency.

        Args:
            roles: Optional list of allowed roles. If None, any authenticated user is allowed.
            optional: If True, returns None for unauthenticated requests instead of raising.
        """
        self.roles = roles
        self.optional = optional

    async def __call__(
        self,
        token: Optional[str] = Depends(get_token_from_header),
    ) -> Optional[TokenPayload]:
        """
        Validate the token and check role permissions.

        Args:
            token: The JWT token from the Authorization header.

        Returns:
            The validated TokenPayload, or None if optional and no token.

        Raises:
            AuthenticationError: If authentication fails.
            AuthorizationError: If the user doesn't have an allowed role.
        """
        if token is None:
            if self.optional:
                return None
            raise AuthenticationError("Missing authentication token")

        payload = validate_access_token(token)
        if payload is None:
            if self.optional:
                raise AuthenticationError("Invalid or expired token")
            raise AuthenticationError("Invalid or expired token")

        # Check role permissions if roles are specified
        if self.roles is not None:
            try:
                user_role = UserRole(payload.role)
            except ValueError:
                raise AuthorizationError("Invalid user role")

            if user_role not in self.roles:
                raise AuthorizationError(
                    f"Role '{payload.role}' is not authorized for this resource"
                )

        return payload
