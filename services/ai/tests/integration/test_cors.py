"""Cross-origin editing must pass preflight without bypassing authorization."""
import pytest

from app.core.config import create_access_token
from app.db.models import UserRole
from app.main import CORS_ORIGINS
from tests.conftest import make_course_with_lessons, make_user


def test_patch_preflight_allows_configured_origin(client):
    origin = CORS_ORIGINS[0]
    response = client.options(
        "/api/lessons/00000000-0000-0000-0000-000000000000",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "PATCH" in response.headers["access-control-allow-methods"].split(", ")
    assert response.headers["access-control-allow-credentials"] == "true"


def test_patch_preflight_rejects_unconfigured_origin(client):
    response = client.options(
        "/api/courses/00000000-0000-0000-0000-000000000000",
        headers={
            "Origin": "https://untrusted.invalid",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("resource", ["course", "lesson"])
@pytest.mark.parametrize("role", [None, UserRole.STUDENT, UserRole.ADMIN])
def test_cross_origin_edits_enforce_roles_and_persist(client, db, resource, role):
    course, lessons = make_course_with_lessons(db, n_lessons=1)
    if resource == "course":
        path = f"/api/courses/{course.id}"
        read_path = path
        change = {"title": "Updated course title"}
    else:
        path = f"/api/lessons/{lessons[0].id}"
        read_path = path + "/content"
        change = {"content": "Updated lesson content."}

    headers = {"Origin": CORS_ORIGINS[0]}
    if role is not None:
        user = make_user(db, role)
        token = create_access_token(user.id, user.email, role.value)
        headers["Authorization"] = f"Bearer {token}"

    response = client.patch(path, headers=headers, json=change)
    assert response.headers["access-control-allow-origin"] == CORS_ORIGINS[0]
    if role is None:
        assert response.status_code == 401
    elif role == UserRole.STUDENT:
        assert response.status_code == 403
    else:
        assert response.status_code == 200
        saved = client.get(read_path, headers=headers)
        assert saved.status_code == 200
        for key, value in change.items():
            assert saved.json()[key] == value
