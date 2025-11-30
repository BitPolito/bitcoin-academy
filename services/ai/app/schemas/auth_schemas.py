"""Pydantic schemas for authentication DTOs."""
import re
from typing import Optional, Any

import bleach
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from zxcvbn import zxcvbn

# Common passwords that should always be rejected
COMMON_PASSWORDS = {
    "password", "password123", "123456", "12345678", "qwerty", "abc123",
    "monkey", "master", "dragon", "111111", "baseball", "iloveyou",
    "trustno1", "sunshine", "ashley", "football", "shadow", "123123",
    "654321", "superman", "qazwsx", "michael", "password1", "admin",
    "letmein", "welcome", "login", "princess", "qwerty123", "solo",
    "passw0rd", "starwars", "bitcoin", "blockchain", "satoshi", "nakamoto",
}

# Sequential patterns to detect
SEQUENTIAL_PATTERNS = [
    "123456789", "987654321", "abcdefgh", "hgfedcba",
    "qwertyuiop", "asdfghjkl", "zxcvbnm",
]


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """
    Sanitize a string input to prevent XSS and injection attacks.

    Args:
        value: The string to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    if not value:
        return value
    # Truncate to max length
    value = value[:max_length]
    # Remove HTML tags and dangerous characters
    value = bleach.clean(value, tags=[], strip=True)
    # Remove null bytes and other control characters
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
    return value.strip()


class LoginRequest(BaseModel):
    """Request schema for user login."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, max_length=128,
                          description="User password")

    @field_validator("password")
    @classmethod
    def sanitize_password_input(cls, v: str) -> str:
        """Basic sanitization for password - no HTML allowed."""
        # Remove null bytes
        return re.sub(r'[\x00]', '', v)


class RegisterRequest(BaseModel):
    """Request schema for user registration."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ...,
        min_length=12,  # NIST recommends 12+ characters
        max_length=128,
        description="User password (min 12 characters, must be strong)"
    )
    display_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100,
        description="User display name"
    )

    @field_validator("display_name")
    @classmethod
    def sanitize_display_name(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize display name to prevent XSS."""
        if v is None:
            return v
        return sanitize_string(v, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Validate password meets strength requirements.

        Implements NIST SP 800-63B guidelines:
        - Minimum 12 characters (increased from 8)
        - Check against common passwords
        - Check for sequential patterns
        - Use zxcvbn for entropy analysis
        """
        # Basic length check (NIST recommends 12+)
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")

        # Check for uppercase
        if not re.search(r"[A-Z]", v):
            raise ValueError(
                "Password must contain at least one uppercase letter")

        # Check for lowercase
        if not re.search(r"[a-z]", v):
            raise ValueError(
                "Password must contain at least one lowercase letter")

        # Check for digit
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")

        # Check for special character
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", v):
            raise ValueError(
                "Password must contain at least one special character")

        # Check against common passwords (case-insensitive)
        if v.lower() in COMMON_PASSWORDS:
            raise ValueError(
                "This password is too common. Please choose a more unique password")

        # Check for sequential patterns
        v_lower = v.lower()
        for pattern in SEQUENTIAL_PATTERNS:
            if pattern in v_lower or pattern[::-1] in v_lower:
                raise ValueError(
                    "Password contains sequential characters. Please choose a more complex password")

        # Check for repeated characters (e.g., "aaa", "111")
        if re.search(r'(.)\1{2,}', v):
            raise ValueError(
                "Password contains too many repeated characters")

        # Use zxcvbn for entropy analysis
        result = zxcvbn(v)
        if result['score'] < 2:  # Score 0-4, require at least 2 (fair)
            feedback = result.get('feedback', {})
            suggestions = feedback.get('suggestions', [])
            warning = feedback.get('warning', '')

            error_msg = "Password is too weak"
            if warning:
                error_msg += f": {warning}"
            elif suggestions:
                error_msg += f". {suggestions[0]}"

            raise ValueError(error_msg)

        return v

    @model_validator(mode='after')
    def check_password_not_contains_email(self) -> 'RegisterRequest':
        """Ensure password doesn't contain parts of the email."""
        email_local = self.email.split('@')[0].lower()
        password_lower = self.password.lower()

        # Check if significant part of email is in password
        if len(email_local) >= 3 and email_local in password_lower:
            raise ValueError(
                "Password should not contain your email address")

        return self


class TokenResponse(BaseModel):
    """Response schema for authentication tokens."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(...,
                            description="Access token expiration in seconds")


class UserResponse(BaseModel):
    """Response schema for user information."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    display_name: Optional[str] = Field(None, description="User display name")
    role: str = Field(..., description="User role")

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Response schema for successful authentication."""

    user: UserResponse
    tokens: TokenResponse


class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh."""

    refresh_token: str = Field(..., description="JWT refresh token")


class ErrorResponse(BaseModel):
    """Response schema for error messages."""

    detail: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")


class MessageResponse(BaseModel):
    """Response schema for simple messages."""

    message: str = Field(..., description="Response message")
