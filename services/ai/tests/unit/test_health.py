"""Unit tests for courses and lessons API endpoints."""
import uuid

import pytest

from app.core.config import create_access_token
from tests.conftest import make_user


@pytest.fixture
def auth_headers(db) -> dict:
    """Course and lesson endpoints require authentication."""
    user = make_user(db)
    role = getattr(user.role, "value", user.role)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, role)}"}


@pytest.mark.unit
def test_get_courses_returns_cursor_page(client, db, auth_headers):
    """GET /api/courses returns an empty cursor page when no data is seeded."""
    response = client.get("/api/courses", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None, "has_more": False}


@pytest.mark.unit
def test_get_course_by_id_not_found(client, db, auth_headers):
    """GET /api/courses/{valid_uuid} returns 404 when course does not exist."""
    missing_id = str(uuid.uuid4())
    response = client.get(f"/api/courses/{missing_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.unit
def test_get_course_invalid_id_format(client, db, auth_headers):
    """GET /api/courses/{non-uuid} returns 422."""
    response = client.get("/api/courses/not-a-uuid", headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.unit
def test_get_course_lessons_not_found(client, db, auth_headers):
    """GET /api/courses/{valid_uuid}/lessons returns 404 when course does not exist."""
    missing_id = str(uuid.uuid4())
    response = client.get(f"/api/courses/{missing_id}/lessons", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.unit
def test_get_course_lessons_invalid_id_format(client, db, auth_headers):
    """GET /api/courses/{non-uuid}/lessons returns 422."""
    response = client.get("/api/courses/not-a-uuid/lessons", headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.unit
def test_get_lesson_by_id_not_found(client, db, auth_headers):
    """GET /api/lessons/{valid_uuid} returns 404 when lesson does not exist."""
    missing_id = str(uuid.uuid4())
    response = client.get(f"/api/lessons/{missing_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.unit
def test_get_lesson_invalid_id_format(client, db, auth_headers):
    """GET /api/lessons/{non-uuid} returns 422."""
    response = client.get("/api/lessons/not-a-uuid", headers=auth_headers)
    assert response.status_code == 422
