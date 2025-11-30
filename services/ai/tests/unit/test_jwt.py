"""Unit tests for JWT token generation and validation."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    settings,
    validate_access_token,
    validate_refresh_token,
    verify_password,
)


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password(self):
        """Test password hashing creates a valid hash."""
        password = "TestPassword123"
        hashed = get_password_hash(password)

        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 0

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "TestPassword123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "TestPassword123"
        wrong_password = "WrongPassword456"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_different_passwords_different_hashes(self):
        """Test that different passwords produce different hashes."""
        password1 = "TestPassword123"
        password2 = "DifferentPassword456"

        hash1 = get_password_hash(password1)
        hash2 = get_password_hash(password2)

        assert hash1 != hash2


class TestAccessToken:
    """Tests for access token generation and validation."""

    def test_create_access_token(self):
        """Test access token creation."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        token = create_access_token(user_id, email, role)

        assert token is not None
        assert len(token) > 0

    def test_validate_access_token(self):
        """Test access token validation returns correct payload."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        token = create_access_token(user_id, email, role)
        payload = validate_access_token(token)

        assert payload is not None
        assert payload.sub == user_id
        assert payload.email == email
        assert payload.role == role
        assert payload.type == "access"

    def test_validate_access_token_expired(self):
        """Test that expired access tokens are rejected."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        # Create token that expires immediately
        token = create_access_token(
            user_id, email, role,
            expires_delta=timedelta(seconds=-1)
        )
        payload = validate_access_token(token)

        assert payload is None

    def test_validate_access_token_invalid(self):
        """Test that invalid tokens are rejected."""
        payload = validate_access_token("invalid-token")

        assert payload is None

    def test_access_token_with_custom_expiry(self):
        """Test access token with custom expiration time."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        token = create_access_token(
            user_id, email, role,
            expires_delta=timedelta(hours=1)
        )
        payload = validate_access_token(token)

        assert payload is not None
        assert payload.exp > datetime.now(timezone.utc)


class TestRefreshToken:
    """Tests for refresh token generation and validation."""

    def test_create_refresh_token(self):
        """Test refresh token creation."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        token = create_refresh_token(user_id, email, role)

        assert token is not None
        assert len(token) > 0

    def test_validate_refresh_token(self):
        """Test refresh token validation returns correct payload."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        token = create_refresh_token(user_id, email, role)
        payload = validate_refresh_token(token)

        assert payload is not None
        assert payload.sub == user_id
        assert payload.email == email
        assert payload.role == role
        assert payload.type == "refresh"

    def test_validate_refresh_token_expired(self):
        """Test that expired refresh tokens are rejected."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        token = create_refresh_token(
            user_id, email, role,
            expires_delta=timedelta(seconds=-1)
        )
        payload = validate_refresh_token(token)

        assert payload is None

    def test_access_token_not_valid_as_refresh(self):
        """Test that access tokens are not valid as refresh tokens."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        access_token = create_access_token(user_id, email, role)
        payload = validate_refresh_token(access_token)

        assert payload is None

    def test_refresh_token_not_valid_as_access(self):
        """Test that refresh tokens are not valid as access tokens."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        refresh_token = create_refresh_token(user_id, email, role)
        payload = validate_access_token(refresh_token)

        assert payload is None


class TestDecodeToken:
    """Tests for generic token decoding."""

    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        token = create_access_token(user_id, email, role)
        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["email"] == email
        assert payload["role"] == role

    def test_decode_invalid_token(self):
        """Test decoding an invalid token returns None."""
        payload = decode_token("invalid-token")

        assert payload is None

    def test_decode_tampered_token(self):
        """Test decoding a tampered token returns None."""
        user_id = "test-user-id"
        email = "test@example.com"
        role = "student"

        token = create_access_token(user_id, email, role)
        # Tamper with the token
        tampered_token = token[:-5] + "XXXXX"

        payload = decode_token(tampered_token)

        assert payload is None
