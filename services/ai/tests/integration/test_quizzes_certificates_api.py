"""Integration tests for quiz and certificate endpoints.

Quizzes are fully DB-backed (course builder + study-page ad-hoc generation
share the same persistence path via quiz_generation.py, see P1 in
docs/next-features-plan.md). LLM calls are mocked.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import create_access_token
from app.db.models import Quiz, QuizScope
from app.services.quiz_generation import persist_quiz
from app.services.study_service import DispatchResult, SourceChunk
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


_QUESTIONS = [
    {
        "prompt": "What is a UTXO?",
        "options": [
            {"key": "A", "text": "An unspent transaction output"},
            {"key": "B", "text": "A mining reward"},
            {"key": "C", "text": "A block header"},
            {"key": "D", "text": "A wallet address"},
        ],
        "correct_key": "A",
        "concept_tag": "utxo-model",
        "difficulty": "beginner",
    }
]

_RETRIEVE_RESULT = DispatchResult(
    answer="",
    citations=[SourceChunk(snippet="A UTXO is an unspent transaction output.", score=0.9, label="p1")],
    retrieval_used=True,
)


# ===========================================================================
# Quizzes — generation (course-scoped, ad-hoc topic)
# ===========================================================================

class TestGenerateQuiz:
    @pytest.mark.integration
    def test_generate_quiz_requires_auth(self, client, db):
        course, _ = make_course_with_lessons(db)
        resp = client.post(
            f"/api/courses/{course.id}/quizzes/generate", json={"query": "UTXO model basics"}
        )
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_generate_quiz_persists_to_db(self, client, db):
        user = make_user(db)
        course, _ = make_course_with_lessons(db)

        with patch(
            "app.services.study_service.dispatch", new_callable=AsyncMock
        ) as mock_dispatch, patch(
            "app.services.quiz_generation.generate_json", new_callable=AsyncMock
        ) as mock_gj:
            mock_dispatch.return_value = _RETRIEVE_RESULT
            mock_gj.return_value = {"questions": _QUESTIONS}

            resp = client.post(
                f"/api/courses/{course.id}/quizzes/generate",
                json={"query": "UTXO model basics"},
                headers=_auth(user.id),
            )

        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["scope"] == QuizScope.COURSE
        assert len(body["questions"]) == 1
        # No is_correct leak to the student-facing generate response
        for opt in body["questions"][0]["options"]:
            assert "is_correct" not in opt

        quiz = db.query(Quiz).filter(Quiz.id == body["id"]).first()
        assert quiz is not None
        assert quiz.course_id == course.id

    @pytest.mark.integration
    def test_generate_quiz_422_when_no_source_material(self, client, db):
        user = make_user(db)
        course, _ = make_course_with_lessons(db)

        with patch(
            "app.services.study_service.dispatch", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = DispatchResult(answer="", citations=[], retrieval_used=False)

            resp = client.post(
                f"/api/courses/{course.id}/quizzes/generate",
                json={"query": "Something totally uncovered"},
                headers=_auth(user.id),
            )

        assert resp.status_code == 422


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
    def test_list_quizzes_returns_only_this_course(self, client, db):
        user = make_user(db)
        course, _ = make_course_with_lessons(db)
        other_course, _ = make_course_with_lessons(db)

        persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="Q1", course_id=course.id)
        persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="Q2", course_id=other_course.id)

        resp = client.get(
            f"/api/courses/{course.id}/quizzes",
            headers=_auth(user.id),
        )
        body = resp.json()
        assert len(body) == 1
        assert body[0]["title"] == "Q1"


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
        assert "error" in body or "detail" in body

    @pytest.mark.integration
    def test_get_quiz_never_exposes_is_correct(self, client, db):
        user = make_user(db)
        course, _ = make_course_with_lessons(db)
        quiz = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="Q", course_id=course.id)

        resp = client.get(f"/api/quizzes/{quiz.id}", headers=_auth(user.id))
        assert resp.status_code == 200
        for question in resp.json()["questions"]:
            for opt in question["options"]:
                assert "is_correct" not in opt


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

    @pytest.mark.integration
    def test_submit_quiz_persists_attempt_and_scores_correctly(self, client, db):
        from app.db.models import OptionChoice, Question, QuizAttempt

        user = make_user(db)
        course, _ = make_course_with_lessons(db)
        quiz = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="Q", course_id=course.id)

        question = db.query(Question).filter(Question.quiz_id == quiz.id).first()
        correct_opt = db.query(OptionChoice).filter(
            OptionChoice.question_id == question.id, OptionChoice.is_correct == True  # noqa: E712
        ).first()

        resp = client.post(
            f"/api/quizzes/{quiz.id}/attempts",
            json={"answers": {question.id: correct_opt.id}},
            headers=_auth(user.id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["score_pct"] == 100
        assert body["passed"] is True
        assert body["correct_count"] == 1
        assert body["corrections"][0]["is_correct"] is True

        attempt = db.query(QuizAttempt).filter(QuizAttempt.id == body["attempt_id"]).first()
        assert attempt is not None
        assert attempt.user_id == user.id
        assert attempt.score_pct == 100

    @pytest.mark.integration
    def test_submit_quiz_wrong_answer_scores_zero(self, client, db):
        from app.db.models import OptionChoice, Question

        user = make_user(db)
        course, _ = make_course_with_lessons(db)
        quiz = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="Q", course_id=course.id)

        question = db.query(Question).filter(Question.quiz_id == quiz.id).first()
        wrong_opt = db.query(OptionChoice).filter(
            OptionChoice.question_id == question.id, OptionChoice.is_correct == False  # noqa: E712
        ).first()

        resp = client.post(
            f"/api/quizzes/{quiz.id}/attempts",
            json={"answers": {question.id: wrong_opt.id}},
            headers=_auth(user.id),
        )
        body = resp.json()
        assert body["score_pct"] == 0
        assert body["passed"] is False


class TestMyQuizAttempts:
    @pytest.mark.integration
    def test_list_my_attempts_requires_auth(self, client, db):
        resp = client.get("/api/users/me/quiz-attempts")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_list_my_attempts_returns_persisted_attempt(self, client, db):
        from app.db.models import OptionChoice, Question

        user = make_user(db)
        course, _ = make_course_with_lessons(db)
        quiz = persist_quiz(db, _QUESTIONS, scope=QuizScope.COURSE, title="Q", course_id=course.id)
        question = db.query(Question).filter(Question.quiz_id == quiz.id).first()
        opt = db.query(OptionChoice).filter(OptionChoice.question_id == question.id).first()

        client.post(
            f"/api/quizzes/{quiz.id}/attempts",
            json={"answers": {question.id: opt.id}},
            headers=_auth(user.id),
        )

        resp = client.get(
            f"/api/users/me/quiz-attempts?course_id={course.id}",
            headers=_auth(user.id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["quiz_id"] == quiz.id


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
        assert resp.json() == {"items": []}

    @pytest.mark.integration
    def test_list_certificates_response_has_items_list(self, client, db):
        user = make_user(db)
        resp = client.get(
            "/api/users/me/certificates",
            headers=_auth(user.id),
        )
        assert isinstance(resp.json()["items"], list)


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
        assert "course_name" in data
        assert "issued_at" in data
        assert "revoked" in data
