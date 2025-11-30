"""Integration tests for authentication API endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.db.session import engine, init_db, SessionLocal
from app.db.models import Base, User
from app.main import app

# Create test client
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Set up a fresh database for each test."""
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield
    # Clean up after test
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestRegistration:
    """Tests for user registration endpoint."""

    def test_register_success(self):
        """Test successful user registration."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123",
                "display_name": "New User"
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Check user data
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["display_name"] == "New User"
        assert data["user"]["role"] == "student"
        assert "id" in data["user"]

        # Check tokens
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]
        assert data["tokens"]["token_type"] == "bearer"
        assert data["tokens"]["expires_in"] > 0

    def test_register_without_display_name(self):
        """Test registration without optional display name."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "noname@example.com",
                "password": "SecurePass123"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "noname@example.com"
        assert data["user"]["display_name"] is None

    def test_register_duplicate_email(self):
        """Test registration with duplicate email returns 409."""
        # First registration
        client.post(
            "/api/auth/register",
            json={
                "email": "duplicate@example.com",
                "password": "SecurePass123"
            }
        )

        # Second registration with same email
        response = client.post(
            "/api/auth/register",
            json={
                "email": "duplicate@example.com",
                "password": "DifferentPass456"
            }
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_register_invalid_email(self):
        """Test registration with invalid email returns 400."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "SecurePass123"
            }
        )

        assert response.status_code == 422  # Pydantic validation error

    def test_register_weak_password_too_short(self):
        """Test registration with short password returns 400."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "weak@example.com",
                "password": "Short1"
            }
        )

        assert response.status_code == 422

    def test_register_weak_password_no_uppercase(self):
        """Test registration with password missing uppercase returns 400."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "weak@example.com",
                "password": "nouppercase123"
            }
        )

        assert response.status_code == 422

    def test_register_weak_password_no_lowercase(self):
        """Test registration with password missing lowercase returns 400."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "weak@example.com",
                "password": "NOLOWERCASE123"
            }
        )

        assert response.status_code == 422

    def test_register_weak_password_no_digit(self):
        """Test registration with password missing digit returns 400."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "weak@example.com",
                "password": "NoDigitsHere"
            }
        )

        assert response.status_code == 422


class TestLogin:
    """Tests for user login endpoint."""

    def test_login_success(self):
        """Test successful login."""
        # First register a user
        client.post(
            "/api/auth/register",
            json={
                "email": "login@example.com",
                "password": "SecurePass123",
                "display_name": "Login User"
            }
        )

        # Then login
        response = client.post(
            "/api/auth/login",
            json={
                "email": "login@example.com",
                "password": "SecurePass123"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Check user data
        assert data["user"]["email"] == "login@example.com"
        assert data["user"]["display_name"] == "Login User"

        # Check tokens
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]

    def test_login_wrong_password(self):
        """Test login with wrong password returns 401."""
        # Register a user
        client.post(
            "/api/auth/register",
            json={
                "email": "wrongpass@example.com",
                "password": "SecurePass123"
            }
        )

        # Try to login with wrong password
        response = client.post(
            "/api/auth/login",
            json={
                "email": "wrongpass@example.com",
                "password": "WrongPassword456"
            }
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_nonexistent_user(self):
        """Test login with non-existent user returns 401."""
        response = client.post(
            "/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "SomePassword123"
            }
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_missing_email(self):
        """Test login with missing email returns 422."""
        response = client.post(
            "/api/auth/login",
            json={
                "password": "SomePassword123"
            }
        )

        assert response.status_code == 422

    def test_login_missing_password(self):
        """Test login with missing password returns 422."""
        response = client.post(
            "/api/auth/login",
            json={
                "email": "user@example.com"
            }
        )

        assert response.status_code == 422


class TestTokenRefresh:
    """Tests for token refresh endpoint."""

    def test_refresh_success(self):
        """Test successful token refresh."""
        # Register and get tokens
        register_response = client.post(
            "/api/auth/register",
            json={
                "email": "refresh@example.com",
                "password": "SecurePass123"
            }
        )
        tokens = register_response.json()["tokens"]

        # Refresh tokens
        response = client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": tokens["refresh_token"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_invalid_token(self):
        """Test refresh with invalid token returns 401."""
        response = client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": "invalid-token"
            }
        )

        assert response.status_code == 401

    def test_refresh_with_access_token(self):
        """Test refresh with access token returns 401."""
        # Register and get tokens
        register_response = client.post(
            "/api/auth/register",
            json={
                "email": "refresh2@example.com",
                "password": "SecurePass123"
            }
        )
        tokens = register_response.json()["tokens"]

        # Try to refresh with access token
        response = client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": tokens["access_token"]
            }
        )

        assert response.status_code == 401


class TestGetCurrentUser:
    """Tests for get current user endpoint."""

    def test_get_me_success(self):
        """Test getting current user info with valid token."""
        # Register and get tokens
        register_response = client.post(
            "/api/auth/register",
            json={
                "email": "me@example.com",
                "password": "SecurePass123",
                "display_name": "Current User"
            }
        )
        tokens = register_response.json()["tokens"]

        # Get current user
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@example.com"
        assert data["display_name"] == "Current User"
        assert data["role"] == "student"

    def test_get_me_no_token(self):
        """Test getting current user without token returns 401."""
        response = client.get("/api/auth/me")

        assert response.status_code == 401

    def test_get_me_invalid_token(self):
        """Test getting current user with invalid token returns 401."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == 401


class TestLogout:
    """Tests for logout endpoint."""

    def test_logout_success(self):
        """Test successful logout."""
        response = client.post("/api/auth/logout")

        assert response.status_code == 200
        assert "logged out" in response.json()["message"].lower()


class TestProtectedRoutes:
    """Tests for accessing protected routes with auth tokens."""

    def test_access_protected_with_valid_token(self):
        """Test accessing protected route with valid token."""
        # Register and get tokens
        register_response = client.post(
            "/api/auth/register",
            json={
                "email": "protected@example.com",
                "password": "SecurePass123"
            }
        )
        tokens = register_response.json()["tokens"]

        # Access protected route (e.g., /api/auth/me)
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )

        assert response.status_code == 200

    def test_access_protected_without_token(self):
        """Test accessing protected route without token returns 401."""
        response = client.get("/api/auth/me")

        assert response.status_code == 401

    def test_access_protected_with_expired_token(self):
        """Test accessing protected route with expired token returns 401."""
        from app.core.config import create_access_token
        from datetime import timedelta

        # Create expired token
        expired_token = create_access_token(
            "test-id", "test@example.com", "student",
            expires_delta=timedelta(seconds=-10)
        )

        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401
