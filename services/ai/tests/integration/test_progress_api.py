"""Integration tests for progress and badge API endpoints.

Uses TestClient with an in-memory SQLite DB and a real JWT token so the full
request → service → DB → response path is exercised.
"""
import pytest

from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user


def _auth_headers(user_id: str, email: str = "u@test.com", role: str = "student") -> dict:
    token = create_access_token(user_id, email, role)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /api/badges  (public, no auth required)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_list_badges_returns_defaults(client):
    resp = client.get("/api/badges")
    assert resp.status_code == 200
    slugs = {b["slug"] for b in resp.json()}
    assert "lesson_complete" in slugs
    assert "course_complete" in slugs


# ---------------------------------------------------------------------------
# GET /api/badges/user  (auth required)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_user_badges_requires_auth(client):
    resp = client.get("/api/badges/user")
    assert resp.status_code == 401


@pytest.mark.integration
def test_get_user_badges_empty_for_new_user(client, db):
    user = make_user(db)
    resp = client.get("/api/badges/user", headers=_auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/progress/{course_id}  (auth required)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_course_progress_requires_auth(client, db):
    _, _ = make_course_with_lessons(db)
    resp = client.get("/api/progress/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 401


@pytest.mark.integration
def test_get_course_progress_default(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db, n_lessons=3)

    resp = client.get(
        f"/api/progress/{course.id}", headers=_auth_headers(user.id)
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["percent"] == 0
    assert data["status"] == "not_started"
    assert data["lesson_count"] == 3
    assert data["completed_count"] == 0


@pytest.mark.integration
def test_get_course_progress_invalid_uuid(client, db):
    user = make_user(db)
    resp = client.get("/api/progress/not-a-uuid", headers=_auth_headers(user.id))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/progress/update
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_update_progress_requires_auth(client, db):
    course, lessons = make_course_with_lessons(db)
    resp = client.post("/api/progress/update", json={
        "lesson_id": lessons[0].id,
        "course_id": course.id,
        "status": "in_progress",
    })
    assert resp.status_code == 401


@pytest.mark.integration
def test_update_progress_in_progress(client, db):
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    resp = client.post(
        "/api/progress/update",
        json={"lesson_id": lessons[0].id, "course_id": course.id, "status": "in_progress"},
        headers=_auth_headers(user.id),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["lesson_progress"]["status"] == "in_progress"
    assert data["course_progress"]["status"] == "in_progress"
    assert data["new_badges"] == []


@pytest.mark.integration
def test_update_progress_completed_awards_badge(client, db):
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    resp = client.post(
        "/api/progress/update",
        json={"lesson_id": lessons[0].id, "course_id": course.id, "status": "completed"},
        headers=_auth_headers(user.id),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["lesson_progress"]["status"] == "completed"
    assert data["course_progress"]["percent"] == 50
    badge_slugs = [b["slug"] for b in data["new_badges"]]
    assert "lesson_complete" in badge_slugs


@pytest.mark.integration
def test_update_progress_full_course_completion(client, db):
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    client.post(
        "/api/progress/update",
        json={"lesson_id": lessons[0].id, "course_id": course.id, "status": "completed"},
        headers=_auth_headers(user.id),
    )
    resp = client.post(
        "/api/progress/update",
        json={"lesson_id": lessons[1].id, "course_id": course.id, "status": "completed"},
        headers=_auth_headers(user.id),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["course_progress"]["percent"] == 100
    assert data["course_progress"]["status"] == "completed"
    badge_slugs = [b["slug"] for b in data["new_badges"]]
    assert "course_complete" in badge_slugs


@pytest.mark.integration
def test_update_progress_with_score(client, db):
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=1)

    resp = client.post(
        "/api/progress/update",
        json={
            "lesson_id": lessons[0].id,
            "course_id": course.id,
            "status": "completed",
            "score": 92,
        },
        headers=_auth_headers(user.id),
    )

    assert resp.status_code == 200
    assert resp.json()["lesson_progress"]["last_score"] == 92


@pytest.mark.integration
def test_update_progress_invalid_status(client, db):
    user = make_user(db)
    course, lessons = make_course_with_lessons(db)

    resp = client.post(
        "/api/progress/update",
        json={
            "lesson_id": lessons[0].id,
            "course_id": course.id,
            "status": "flying",
        },
        headers=_auth_headers(user.id),
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_badges_appear_in_user_badges_after_completion(client, db):
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=1)

    client.post(
        "/api/progress/update",
        json={"lesson_id": lessons[0].id, "course_id": course.id, "status": "completed"},
        headers=_auth_headers(user.id),
    )

    resp = client.get("/api/badges/user", headers=_auth_headers(user.id))
    assert resp.status_code == 200
    slugs = {b["badge"]["slug"] for b in resp.json()}
    assert "lesson_complete" in slugs
    assert "course_complete" in slugs
