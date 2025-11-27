
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.mark.unit
def test_get_courses():
    response = client.get("/api/courses")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(course["title"] == "Python Basics" for course in data)


@pytest.mark.unit
def test_get_course_by_id():
    response = client.get("/api/courses/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Python Basics"


@pytest.mark.unit
def test_get_course_by_id_not_found():
    response = client.get("/api/courses/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Course not found"


@pytest.mark.unit
def test_get_course_lessons():
    response = client.get("/api/courses/1/lessons")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(lesson["title"] == "Variables and Types" for lesson in data)


@pytest.mark.unit
def test_get_lesson_by_id():
    response = client.get("/api/lessons/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Variables and Types"


@pytest.mark.unit
def test_get_lesson_by_id_not_found():
    response = client.get("/api/lessons/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Lesson not found"
