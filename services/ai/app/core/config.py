import os
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


class Settings:
    """Application settings and configuration with security validation."""

    # Database Configuration - MUST be provided via environment
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    if not DATABASE_URL:
        raise ValueError(
            "❌ CRITICAL: DATABASE_URL environment variable must be set. "
            "Set it before starting the application."
        )

    # Mask sensitive data in logs
    _DATABASE_URL_DISPLAY = (
        DATABASE_URL.split("//")[0] + "//***:***@" + DATABASE_URL.split("@")[1]
        if "@" in DATABASE_URL
        else DATABASE_URL
    )
    logger.info(f"Database connected: {_DATABASE_URL_DISPLAY}")

    # JWT Configuration - MUST be provided via environment
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    if not SECRET_KEY:
        raise ValueError(
            "❌ CRITICAL: SECRET_KEY environment variable must be set. "
            'Generate a secure key with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    if len(SECRET_KEY) < 32:
        raise ValueError(
            f"❌ CRITICAL: SECRET_KEY must be at least 32 characters long. "
            f"Current length: {len(SECRET_KEY)} characters"
        )

    # Security: Reject obviously insecure SECRET_KEY values
    INSECURE_KEY_PATTERNS = [
        "change_me", "changeme", "secret", "password", "123456",
        "your-secret", "your_secret", "example", "test", "demo",
        "development", "placeholder", "fixme", "todo"
    ]
    SECRET_KEY_LOWER = SECRET_KEY.lower()
    for pattern in INSECURE_KEY_PATTERNS:
        if pattern in SECRET_KEY_LOWER:
            raise ValueError(
                f"❌ CRITICAL: SECRET_KEY contains insecure pattern '{pattern}'. "
                'Generate a secure key with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )

    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(
        os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # Environment validation
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    if ENVIRONMENT not in ["development", "staging", "production"]:
        raise ValueError(
            f"❌ INVALID: ENVIRONMENT must be one of: development, staging, production. "
            f"Got: {ENVIRONMENT}"
        )


settings = Settings()


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: str  # User ID
    email: str
    role: str
    exp: datetime
    iat: datetime
    type: str  # 'access' or 'refresh'


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: The plain text password to verify.
        hashed_password: The hashed password to compare against.

    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: The plain text password to hash.

    Returns:
        The hashed password.
    """
    return pwd_context.hash(password)


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: The user's unique identifier.
        email: The user's email address.
        role: The user's role (student, instructor, admin).
        expires_delta: Optional custom expiration time.

    Returns:
        The encoded JWT access token.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": now,
        "type": "access"
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: str,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT refresh token.

    Args:
        user_id: The user's unique identifier.
        email: The user's email address.
        role: The user's role.
        expires_delta: Optional custom expiration time.

    Returns:
        The encoded JWT refresh token.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": now,
        "type": "refresh"
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token to decode.

    Returns:
        The decoded payload if valid, None otherwise.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def validate_access_token(token: str) -> Optional[TokenPayload]:
    """
    Validate an access token and return the payload.

    Args:
        token: The JWT access token to validate.

    Returns:
        TokenPayload if valid access token, None otherwise.
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # Verify it's an access token
    if payload.get("type") != "access":
        return None

    try:
        return TokenPayload(
            sub=payload["sub"],
            email=payload["email"],
            role=payload["role"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
            type=payload["type"]
        )
    except (KeyError, ValueError):
        return None


def validate_refresh_token(token: str) -> Optional[TokenPayload]:
    """
    Validate a refresh token and return the payload.

    Args:
        token: The JWT refresh token to validate.

    Returns:
        TokenPayload if valid refresh token, None otherwise.
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # Verify it's a refresh token
    if payload.get("type") != "refresh":
        return None

    try:
        return TokenPayload(
            sub=payload["sub"],
            email=payload["email"],
            role=payload["role"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
            type=payload["type"]
        )
    except (KeyError, ValueError):
        return None
