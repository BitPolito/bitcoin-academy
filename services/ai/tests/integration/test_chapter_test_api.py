"""Integration tests for chapter_test_api.py — P5."""
import uuid

import pytest

from app.core.config import create_access_token
from app.db.models import (
    OptionChoice,
    Question,
    QuestionType,
    Quiz,
    QuizScope,
)
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str, role: str = "instructor") -> dict:
    token = create_access_token(user_id, "u@test.com", role)
    return {"Authorization": f"Bearer {token}"}


def _seed_lesson_quiz(db, lesson_id, n_questions=2):
    quiz = Quiz(id=str(uuid.uuid4()), scope=QuizScope.LESSON, title="LQ", lesson_id=lesson_id)
    db.add(quiz)
    db.flush()
    for i in range(n_questions):
        q = Question(
            id=str(uuid.uuid4()), quiz_id=quiz.id, qtype=QuestionType.MCQ,
            prompt=f"Q{i}?", order_index=i, concept_tag=f"tag-{i}", difficulty="beginner",
        )
        db.add(q)
        db.flush()
        for k, key in enumerate(["A", "B", "C", "D"]):
            db.add(OptionChoice(
                id=str(uuid.uuid4()), question_id=q.id, label=f"{key}) opt", is_correct=(k == 0),
            ))
    db.commit()
    return quiz


class TestGenerateChapterTest:
    @pytest.mark.integration
    def test_requires_auth(self, client, db):
        course, lessons = make_course_with_lessons(db, n_lessons=1)
        from app.db.models import Chapter
        chapter = db.query(Chapter).filter(Chapter.id == lessons[0].chapter_id).first()

        resp = client.post(f"/api/chapters/{chapter.id}/test/generate")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_rejects_student_role(self, client, db):
        user = make_user(db)
        course, lessons = make_course_with_lessons(db, n_lessons=1)
        from app.db.models import Chapter
        chapter = db.query(Chapter).filter(Chapter.id == lessons[0].chapter_id).first()

        resp = client.post(
            f"/api/chapters/{chapter.id}/test/generate", headers=_auth(user.id, "student"),
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_generates_test_from_published_lesson_quizzes(self, client, db):
        from app.db.models import Chapter

        user = make_user(db)
        course, lessons = make_course_with_lessons(db, n_lessons=2)
        chapter = db.query(Chapter).filter(Chapter.id == lessons[0].chapter_id).first()
        for lesson in lessons:
            lesson.status = "published"
            _seed_lesson_quiz(db, lesson.id, n_questions=2)
        db.commit()

        resp = client.post(
            f"/api/chapters/{chapter.id}/test/generate", headers=_auth(user.id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["chapter_id"] == chapter.id
        assert len(body["questions"]) > 0
        # Student-safe: no is_correct anywhere
        for q in body["questions"]:
            for opt in q["options"]:
                assert "is_correct" not in opt

    @pytest.mark.integration
    def test_422_when_no_published_lessons_have_quizzes(self, client, db):
        from app.db.models import Chapter

        user = make_user(db)
        course, lessons = make_course_with_lessons(db, n_lessons=1)
        chapter = db.query(Chapter).filter(Chapter.id == lessons[0].chapter_id).first()

        resp = client.post(
            f"/api/chapters/{chapter.id}/test/generate", headers=_auth(user.id),
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_404_for_unknown_chapter(self, client, db):
        user = make_user(db)
        resp = client.post(
            "/api/chapters/nonexistent-chapter/test/generate", headers=_auth(user.id),
        )
        assert resp.status_code == 404


class TestGetChapterTest:
    @pytest.mark.integration
    def test_get_requires_auth(self, client, db):
        from app.db.models import Chapter

        user = make_user(db)
        course, lessons = make_course_with_lessons(db, n_lessons=1)
        chapter = db.query(Chapter).filter(Chapter.id == lessons[0].chapter_id).first()
        lessons[0].status = "published"
        _seed_lesson_quiz(db, lessons[0].id, n_questions=2)
        db.commit()

        client.post(f"/api/chapters/{chapter.id}/test/generate", headers=_auth(user.id))

        assert client.get(f"/api/chapters/{chapter.id}/test").status_code == 401

        resp = client.get(
            f"/api/chapters/{chapter.id}/test", headers=_auth(user.id, "student")
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["chapter_id"] == chapter.id
        for q in body["questions"]:
            for opt in q["options"]:
                assert "is_correct" not in opt

    @pytest.mark.integration
    def test_404_when_no_test_built_yet(self, client, db):
        from app.db.models import Chapter

        course, lessons = make_course_with_lessons(db, n_lessons=1)
        chapter = db.query(Chapter).filter(Chapter.id == lessons[0].chapter_id).first()
        user = make_user(db)

        resp = client.get(f"/api/chapters/{chapter.id}/test", headers=_auth(user.id))
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_404_for_unknown_chapter(self, client, db):
        user = make_user(db)
        resp = client.get(
            "/api/chapters/nonexistent-chapter/test", headers=_auth(user.id)
        )
        assert resp.status_code == 404


class TestChapterTestSubmission:
    @pytest.mark.integration
    def test_submit_answers_via_shared_quiz_attempts_endpoint(self, client, db):
        from app.db.models import Chapter

        instructor = make_user(db)
        student = make_user(db)
        course, lessons = make_course_with_lessons(db, n_lessons=1)
        chapter = db.query(Chapter).filter(Chapter.id == lessons[0].chapter_id).first()
        lessons[0].status = "published"
        _seed_lesson_quiz(db, lessons[0].id, n_questions=2)
        db.commit()

        gen_resp = client.post(
            f"/api/chapters/{chapter.id}/test/generate", headers=_auth(instructor.id),
        )
        quiz_id = gen_resp.json()["quiz_id"]
        first_question = gen_resp.json()["questions"][0]
        first_option_id = first_question["options"][0]["id"]

        submit_resp = client.post(
            f"/api/quizzes/{quiz_id}/attempts",
            json={"answers": {first_question["id"]: first_option_id}},
            headers=_auth(student.id, "student"),
        )
        assert submit_resp.status_code == 200
        assert "score_pct" in submit_resp.json()
