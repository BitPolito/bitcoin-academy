"""Authorization matrix — every API endpoint is checked for authentication.

The endpoint list is derived from the live OpenAPI schema rather than hardcoded,
so a newly added endpoint is covered the moment it exists. A new route that
forgets authentication fails `test_every_endpoint_requires_authentication`
without anyone having to remember to add a test.

Endpoints that are deliberately public are listed in PUBLIC_ENDPOINTS. Adding a
route there is an explicit decision that shows up in review, which is the point.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import create_access_token
from app.main import app
from tests.conftest import make_course_with_lessons, make_user

# ---------------------------------------------------------------------------
# Endpoints that are intentionally reachable without a token.
# ---------------------------------------------------------------------------

PUBLIC_ENDPOINTS: set[tuple[str, str]] = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    # Refresh carries its own credential (the refresh token) in the body.
    ("POST", "/api/auth/refresh"),
    # Public certificate verification: a third party checks a code without an account.
    ("GET", "/api/certificates/verify/{code}"),
    # Static action metadata that drives the UI; contains no user data.
    ("GET", "/api/study/actions"),
    # Badge *definitions* only — a static catalogue. The per-user variant
    # (/api/badges/user) is protected and is covered by the matrix below.
    ("GET", "/api/badges"),
}

# Placeholder values substituted into path parameters.
_PATH_VALUES = {
    "course_id": str(uuid.uuid4()),
    "document_id": str(uuid.uuid4()),
    "lesson_id": str(uuid.uuid4()),
    "quiz_id": str(uuid.uuid4()),
    "code": "SOME-CERTIFICATE-CODE",
    "chapter_id": "00000000-0000-0000-0000-000000000000",
    "run_id": "00000000-0000-0000-0000-000000000000",
}

# Status codes that count as "authentication was enforced".
_AUTH_REJECTED = {401, 403}


def _api_endpoints() -> list[tuple[str, str]]:
    """Every /api endpoint in the OpenAPI schema, as (method, path) pairs."""
    spec = app.openapi()
    endpoints = []
    for path, operations in spec["paths"].items():
        if not path.startswith("/api"):
            continue
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                endpoints.append((method.upper(), path))
    return sorted(endpoints)


def _concrete(path: str) -> str:
    """Substitute placeholder values for path parameters."""
    for name, value in _PATH_VALUES.items():
        path = path.replace("{" + name + "}", value)
    return path


def _call(client: TestClient, method: str, path: str, **kwargs):
    return client.request(method, _concrete(path), **kwargs)


PROTECTED_ENDPOINTS = [e for e in _api_endpoints() if e not in PUBLIC_ENDPOINTS]


def test_endpoint_discovery_is_not_empty():
    """Guard against the matrix silently testing nothing.

    If route registration changes shape and discovery returns an empty list,
    every parametrised test below would vacuously pass. This asserts the
    matrix actually found endpoints.
    """
    assert len(PROTECTED_ENDPOINTS) > 20, (
        f"Expected the API to expose many protected endpoints, discovered "
        f"{len(PROTECTED_ENDPOINTS)}. Route discovery is probably broken."
    )


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_every_endpoint_requires_authentication(client: TestClient, method: str, path: str):
    """No protected endpoint may serve an unauthenticated request.

    A 404/422 here would mean the request was processed far enough to look up
    a resource or validate a body, which means authentication did not gate it.
    """
    response = _call(client, method, path, json={})
    assert response.status_code in _AUTH_REJECTED, (
        f"{method} {path} returned {response.status_code} without a token; "
        f"expected 401 or 403. Endpoints must authenticate before doing any work."
    )


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_every_endpoint_rejects_a_malformed_token(client: TestClient, method: str, path: str):
    """A garbage bearer token must be rejected, not ignored."""
    response = _call(
        client, method, path,
        headers={"Authorization": "Bearer not-a-real-jwt"},
        json={},
    )
    assert response.status_code in _AUTH_REJECTED, (
        f"{method} {path} returned {response.status_code} with a malformed token; "
        f"expected 401 or 403."
    )


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_every_endpoint_rejects_a_token_signed_with_the_wrong_key(
    client: TestClient, method: str, path: str
):
    """A token signed by an attacker's key must not be accepted."""
    import jwt as pyjwt

    forged = pyjwt.encode(
        {"sub": str(uuid.uuid4()), "email": "attacker@example.com", "role": "admin"},
        "an-attacker-controlled-signing-key-that-is-long-enough",
        algorithm="HS256",
    )
    response = _call(
        client, method, path,
        headers={"Authorization": f"Bearer {forged}"},
        json={},
    )
    assert response.status_code in _AUTH_REJECTED, (
        f"{method} {path} accepted a token signed with the wrong key "
        f"(status {response.status_code}). Signature verification is not enforced."
    )


def test_public_endpoints_are_reachable_without_a_token(client: TestClient):
    """The public allowlist must actually be public.

    Guards the opposite failure: an endpoint listed as public that in fact
    requires a token means the allowlist is lying about the security model.
    """
    for method, path in sorted(PUBLIC_ENDPOINTS):
        response = _call(client, method, path, json={})
        assert response.status_code not in _AUTH_REJECTED, (
            f"{method} {path} is listed in PUBLIC_ENDPOINTS but returned "
            f"{response.status_code} without a token."
        )


# ---------------------------------------------------------------------------
# Cross-user access — authentication is not enough; ownership must be checked.
# ---------------------------------------------------------------------------

def _auth_header(user) -> dict:
    # role may come back as the enum or as its string value depending on the
    # SQLAlchemy type resolution, so normalise before signing.
    role = getattr(user.role, "value", user.role)
    token = create_access_token(user.id, user.email, role)
    return {"Authorization": f"Bearer {token}"}


def test_progress_of_another_user_is_not_readable(client: TestClient, db):
    """User B must not read User A's course progress."""
    user_a = make_user(db)
    user_b = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    # User A completes a lesson.
    recorded = client.post(
        "/api/progress/update",
        headers=_auth_header(user_a),
        json={
            "lesson_id": lessons[0].id,
            "course_id": course.id,
            "status": "completed",
        },
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["course_progress"]["completed_count"] == 1

    # User B reads the same course's progress and must not see A's completion.
    response = client.get(f"/api/progress/{course.id}", headers=_auth_header(user_b))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["completed_count"] == 0, (
        f"User B sees {body['completed_count']} completed lessons in a course where "
        f"only User A recorded progress. Progress is leaking across users: {body}"
    )
    assert body["completed_lesson_ids"] == []


def test_certificates_endpoint_is_scoped_to_the_caller(client: TestClient, db):
    """The certificate list must be derived from the token, not from a parameter.

    Accepts either a bare list or a paginated `{"items": [...]}` envelope: the
    property under test is caller scoping, not the response shape, which is
    pinned separately in the contract tests.
    """
    user = make_user(db)
    response = client.get("/api/users/me/certificates", headers=_auth_header(user))
    assert response.status_code == 200, response.text

    body = response.json()
    items = body["items"] if isinstance(body, dict) else body
    assert isinstance(items, list)
    assert items == [], "A newly created user must not already hold certificates"


def test_auth_me_returns_the_token_subject(client: TestClient, db):
    """/api/auth/me must describe the token holder, not an arbitrary user."""
    user_a = make_user(db)
    user_b = make_user(db)

    response = client.get("/api/auth/me", headers=_auth_header(user_a))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body.get("email") == user_a.email
    assert body.get("email") != user_b.email


def test_student_does_not_see_draft_lesson_content(client: TestClient, db):
    """A draft/needs_review lesson must stay invisible to students.

    GET /api/courses/{id}/lessons and GET /api/lessons/{id} both filter on
    review status (course_service.get_course_lessons/courses_api.get_lesson),
    but neither was covered by a dedicated test: the generic "requires auth"
    checks elsewhere in this file only assert that *a* token is required, not
    that its role is respected, so a regression here would pass unnoticed.
    """
    from app.db.models import UserRole

    student = make_user(db, role=UserRole.STUDENT)
    instructor = make_user(db, role=UserRole.INSTRUCTOR)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    published_lesson, draft_lesson = lessons
    draft_lesson.status = "draft"
    db.commit()

    # GET /api/courses/{id}/lessons — the draft must be filtered out for a
    # student but still visible to an instructor reviewing the course.
    student_list = client.get(
        f"/api/courses/{course.id}/lessons", headers=_auth_header(student)
    )
    assert student_list.status_code == 200, student_list.text
    student_ids = {l["id"] for l in student_list.json()}
    assert draft_lesson.id not in student_ids, (
        "A draft lesson was returned to a student by GET /courses/{id}/lessons"
    )
    assert published_lesson.id in student_ids

    instructor_list = client.get(
        f"/api/courses/{course.id}/lessons", headers=_auth_header(instructor)
    )
    assert instructor_list.status_code == 200, instructor_list.text
    instructor_ids = {l["id"] for l in instructor_list.json()}
    assert draft_lesson.id in instructor_ids, (
        "An instructor must still see draft lessons in order to review them"
    )

    # GET /api/lessons/{id} — a student fetching the draft lesson directly
    # must get the same 404 as a non-existent lesson, not its content.
    student_direct = client.get(
        f"/api/lessons/{draft_lesson.id}", headers=_auth_header(student)
    )
    assert student_direct.status_code == 404, (
        f"A student fetched a draft lesson directly via GET /lessons/{{id}} "
        f"(status {student_direct.status_code}): {student_direct.text}"
    )

    instructor_direct = client.get(
        f"/api/lessons/{draft_lesson.id}", headers=_auth_header(instructor)
    )
    assert instructor_direct.status_code == 200, instructor_direct.text
