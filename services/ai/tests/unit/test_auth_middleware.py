"""Unit tests for authentication middleware."""
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.core.config import create_access_token, create_refresh_token
from app.db.models import UserRole
from app.middleware.auth import (
    AuthenticationError,
    AuthorizationError,
    CurrentUser,
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_instructor,
    require_student,
)

# Create a test FastAPI app
app = FastAPI()


@app.get("/protected")
async def protected_route(user=Depends(get_current_user)):
    return {"user_id": user.sub, "email": user.email, "role": user.role}


@app.get("/optional")
async def optional_route(user=Depends(get_current_user_optional)):
    if user:
        return {"user_id": user.sub, "authenticated": True}
    return {"authenticated": False}


@app.get("/admin-only")
async def admin_route(user=Depends(require_admin)):
    return {"user_id": user.sub, "role": user.role}


@app.get("/instructor-only")
async def instructor_route(user=Depends(require_instructor)):
    return {"user_id": user.sub, "role": user.role}


@app.get("/student-only")
async def student_route(user=Depends(require_student)):
    return {"user_id": user.sub, "role": user.role}


@app.get("/custom-role")
async def custom_role_route(user=Depends(CurrentUser(roles=[UserRole.ADMIN, UserRole.INSTRUCTOR]))):
    return {"user_id": user.sub, "role": user.role}


client = TestClient(app)


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    def test_valid_token(self):
        """Test that valid token returns user info."""
        token = create_access_token(
            "test-user-id", "test@example.com", "student")

        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-id"
        assert data["email"] == "test@example.com"
        assert data["role"] == "student"

    def test_missing_token(self):
        """Test that missing token returns 401."""
        response = client.get("/protected")

        assert response.status_code == 401
        assert "Missing authentication token" in response.json()["detail"]

    def test_invalid_token(self):
        """Test that invalid token returns 401."""
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == 401
        assert "Invalid or expired token" in response.json()["detail"]

    def test_refresh_token_not_valid_for_access(self):
        """Test that refresh token is not valid for access."""
        token = create_refresh_token(
            "test-user-id", "test@example.com", "student")

        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401

    def test_malformed_authorization_header(self):
        """Test that malformed Authorization header returns 401."""
        response = client.get(
            "/protected",
            headers={"Authorization": "NotBearer token"}
        )

        assert response.status_code == 401


class TestGetCurrentUserOptional:
    """Tests for get_current_user_optional dependency."""

    def test_valid_token(self):
        """Test that valid token returns user info."""
        token = create_access_token(
            "test-user-id", "test@example.com", "student")

        response = client.get(
            "/optional",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-id"
        assert data["authenticated"] is True

    def test_missing_token(self):
        """Test that missing token returns unauthenticated response."""
        response = client.get("/optional")

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False

    def test_invalid_token(self):
        """Test that invalid token returns 401 even for optional auth."""
        response = client.get(
            "/optional",
            headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == 401


class TestRoleBasedAccess:
    """Tests for role-based access control."""

    def test_admin_can_access_admin_route(self):
        """Test that admin can access admin-only route."""
        token = create_access_token("admin-id", "admin@example.com", "admin")

        response = client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_student_cannot_access_admin_route(self):
        """Test that student cannot access admin-only route."""
        token = create_access_token(
            "student-id", "student@example.com", "student")

        response = client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    def test_instructor_cannot_access_admin_route(self):
        """Test that instructor cannot access admin-only route."""
        token = create_access_token(
            "instructor-id", "instructor@example.com", "instructor")

        response = client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    def test_admin_can_access_instructor_route(self):
        """Test that admin can access instructor route."""
        token = create_access_token("admin-id", "admin@example.com", "admin")

        response = client.get(
            "/instructor-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_instructor_can_access_instructor_route(self):
        """Test that instructor can access instructor route."""
        token = create_access_token(
            "instructor-id", "instructor@example.com", "instructor")

        response = client.get(
            "/instructor-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_student_cannot_access_instructor_route(self):
        """Test that student cannot access instructor route."""
        token = create_access_token(
            "student-id", "student@example.com", "student")

        response = client.get(
            "/instructor-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    def test_all_roles_can_access_student_route(self):
        """Test that all roles can access student route."""
        for role in ["student", "instructor", "admin"]:
            token = create_access_token(
                f"{role}-id", f"{role}@example.com", role)

            response = client.get(
                "/student-only",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200


class TestCurrentUserDependency:
    """Tests for CurrentUser dependency class."""

    def test_custom_role_restriction(self):
        """Test CurrentUser with custom role list."""
        admin_token = create_access_token(
            "admin-id", "admin@example.com", "admin")
        instructor_token = create_access_token(
            "instructor-id", "instructor@example.com", "instructor")
        student_token = create_access_token(
            "student-id", "student@example.com", "student")

        # Admin should have access
        response = client.get(
            "/custom-role",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

        # Instructor should have access
        response = client.get(
            "/custom-role",
            headers={"Authorization": f"Bearer {instructor_token}"}
        )
        assert response.status_code == 200

        # Student should not have access
        response = client.get(
            "/custom-role",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert response.status_code == 403
