"""Unit tests for courses and lessons API endpoints."""
import uuid

import pytest


@pytest.mark.unit
def test_get_courses_returns_list(client):
    """GET /api/courses returns a JSON array (empty when no data is seeded)."""
    response = client.get("/api/courses")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.unit
def test_get_course_by_id_not_found(client):
    """GET /api/courses/{valid_uuid} returns 404 when course does not exist."""
    missing_id = str(uuid.uuid4())
    response = client.get(f"/api/courses/{missing_id}")
    assert response.status_code == 404


@pytest.mark.unit
def test_get_course_invalid_id_format(client):
    """GET /api/courses/{non-uuid} returns 422."""
    response = client.get("/api/courses/not-a-uuid")
    assert response.status_code == 422


@pytest.mark.unit
def test_get_course_lessons_not_found(client):
    """GET /api/courses/{valid_uuid}/lessons returns 404 when course does not exist."""
    missing_id = str(uuid.uuid4())
    response = client.get(f"/api/courses/{missing_id}/lessons")
    assert response.status_code == 404


@pytest.mark.unit
def test_get_course_lessons_invalid_id_format(client):
    """GET /api/courses/{non-uuid}/lessons returns 422."""
    response = client.get("/api/courses/not-a-uuid/lessons")
    assert response.status_code == 422


@pytest.mark.unit
def test_get_lesson_by_id_not_found(client):
    """GET /api/lessons/{valid_uuid} returns 404 when lesson does not exist."""
    missing_id = str(uuid.uuid4())
    response = client.get(f"/api/lessons/{missing_id}")
    assert response.status_code == 404


@pytest.mark.unit
def test_get_lesson_invalid_id_format(client):
    """GET /api/lessons/{non-uuid} returns 422."""
    response = client.get("/api/lessons/not-a-uuid")
    assert response.status_code == 422
