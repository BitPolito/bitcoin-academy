"""Integration tests for POST /api/courses/{course_id}/chat/feedback.

Covers the turn_id link added for issue #136: feedback on a study answer can
now be traced back to the persisted turn it was about, not just a free-form
client session_id.
"""
import pytest

from app.core.config import create_access_token
from app.db.models import AnswerFeedback
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
def test_feedback_requires_auth(client, db):
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/chat/feedback",
        json={"session_id": "s1", "question": "q", "answer": "a", "rating": 1},
    )
    assert resp.status_code == 401


@pytest.mark.integration
def test_feedback_rejects_invalid_rating(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/chat/feedback",
        json={"session_id": "s1", "question": "q", "answer": "a", "rating": 0},
        headers=_auth(user.id),
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_feedback_without_turn_id_is_still_recorded(client, db):
    """turn_id is optional — the pre-existing chat feedback path has none."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/chat/feedback",
        json={"session_id": "s1", "question": "q", "answer": "a", "rating": 1},
        headers=_auth(user.id),
    )
    assert resp.status_code == 200

    db.expire_all()
    record = db.query(AnswerFeedback).filter_by(id=resp.json()["id"]).first()
    assert record.turn_id is None


@pytest.mark.integration
def test_feedback_with_turn_id_links_back_to_the_turn(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    headers = _auth(user.id)

    session_id = client.post(
        f"/api/courses/{course.id}/sessions", json={}, headers=headers
    ).json()["id"]

    from app.services import study_session_service

    turn = study_session_service.append_turn(
        db, user.id, session_id, action="explain", query="q", answer="a", citations=[]
    )
    assert turn is not None

    resp = client.post(
        f"/api/courses/{course.id}/chat/feedback",
        json={
            "session_id": "client-chat-session",
            "question": "q",
            "answer": "a",
            "rating": 1,
            "turn_id": turn.id,
        },
        headers=headers,
    )
    assert resp.status_code == 200

    db.expire_all()
    record = db.query(AnswerFeedback).filter_by(id=resp.json()["id"]).first()
    assert record.turn_id == turn.id
