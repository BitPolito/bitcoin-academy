"""Integration tests for quiz and certificate placeholder endpoints.

These endpoints are functional stubs: correct HTTP shape, correct status codes,
and correct empty/404 responses until the service layer is implemented.
"""
import pytest

from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Quizzes
# ===========================================================================

class TestListQuizzes:
    @pytest.mark.integration
    def test_list_quizzes_requires_auth(self, client, db):
        course, _ = make_course_with_lessons(db)
        resp = client.get(f"/api/courses/{course.id}/quizzes")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_list_quizzes_returns_empty_list(self, client, db):
        user = make_user(db)
        course, _ = make_course_with_lessons(db)
        resp = client.get(
            f"/api/courses/{course.id}/quizzes",
            headers=_auth(user.id),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.integration
    def test_list_quizzes_response_is_list(self, client, db):
        user = make_user(db)
        course, _ = make_course_with_lessons(db)
        resp = client.get(
            f"/api/courses/{course.id}/quizzes",
            headers=_auth(user.id),
        )
        assert isinstance(resp.json(), list)


class TestGetQuiz:
    @pytest.mark.integration
    def test_get_quiz_requires_auth(self, client, db):
        resp = client.get("/api/quizzes/some-quiz-id")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_get_quiz_returns_404(self, client, db):
        user = make_user(db)
        resp = client.get(
            "/api/quizzes/nonexistent-quiz-id",
            headers=_auth(user.id),
        )
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_get_quiz_404_body_has_error(self, client, db):
        user = make_user(db)
        resp = client.get(
            "/api/quizzes/nonexistent-quiz-id",
            headers=_auth(user.id),
        )
        body = resp.json()
        # Custom error handler wraps errors in {"error": {"code": ..., "message": ...}}
        assert "error" in body or "detail" in body


class TestSubmitQuiz:
    @pytest.mark.integration
    def test_submit_quiz_requires_auth(self, client, db):
        resp = client.post(
            "/api/quizzes/some-quiz-id/attempts",
            json={"answers": {"q1": "a"}},
        )
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_submit_quiz_returns_404_for_unknown_quiz(self, client, db):
        user = make_user(db)
        resp = client.post(
            "/api/quizzes/nonexistent-quiz-id/attempts",
            json={"answers": {"q1": "a"}},
            headers=_auth(user.id),
        )
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_submit_quiz_rejects_missing_answers(self, client, db):
        user = make_user(db)
        resp = client.post(
            "/api/quizzes/some-quiz-id/attempts",
            json={},
            headers=_auth(user.id),
        )
        assert resp.status_code == 422


# ===========================================================================
# Certificates
# ===========================================================================

class TestListCertificates:
    @pytest.mark.integration
    def test_list_certificates_requires_auth(self, client, db):
        resp = client.get("/api/users/me/certificates")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_list_certificates_returns_empty_list(self, client, db):
        user = make_user(db)
        resp = client.get(
            "/api/users/me/certificates",
            headers=_auth(user.id),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.integration
    def test_list_certificates_response_is_list(self, client, db):
        user = make_user(db)
        resp = client.get(
            "/api/users/me/certificates",
            headers=_auth(user.id),
        )
        assert isinstance(resp.json(), list)


class TestVerifyCertificate:
    @pytest.mark.integration
    def test_verify_certificate_is_public(self, client, db):
        """Verify endpoint does not require auth."""
        resp = client.get("/api/certificates/verify/SOME-CODE-123")
        assert resp.status_code == 200

    @pytest.mark.integration
    def test_verify_certificate_returns_invalid(self, client, db):
        resp = client.get("/api/certificates/verify/FAKE-CODE-000")
        data = resp.json()
        assert data["valid"] is False

    @pytest.mark.integration
    def test_verify_certificate_echoes_code(self, client, db):
        code = "TEST-CERT-CODE-42"
        resp = client.get(f"/api/certificates/verify/{code}")
        assert resp.json()["code"] == code

    @pytest.mark.integration
    def test_verify_certificate_response_schema(self, client, db):
        resp = client.get("/api/certificates/verify/SOME-CODE")
        data = resp.json()
        assert "valid" in data
        assert "code" in data
        assert "course_id" in data
        assert "issued_at" in data
