"""Integration tests for /api/courses/{course_id}/sessions — issue #136.

Covers CRUD, authorization (no auth, wrong user), and course isolation (a
session created under one course must not be reachable or deletable from
another course's path, even for the same user).
"""
import pytest

from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_sessions_require_auth(client, db):
    course, _ = make_course_with_lessons(db)
    resp = client.get(f"/api/courses/{course.id}/sessions")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_create_list_get_delete_round_trip(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    headers = _auth(user.id)

    created = client.post(
        f"/api/courses/{course.id}/sessions", json={"title": "UTXO model"}, headers=headers
    )
    assert created.status_code == 200
    session_id = created.json()["id"]
    assert created.json()["title"] == "UTXO model"
    assert created.json()["turn_count"] == 0

    listed = client.get(f"/api/courses/{course.id}/sessions", headers=headers)
    assert listed.status_code == 200
    assert [s["id"] for s in listed.json()] == [session_id]

    detail = client.get(f"/api/courses/{course.id}/sessions/{session_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["turns"] == []

    deleted = client.delete(f"/api/courses/{course.id}/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 200

    gone = client.get(f"/api/courses/{course.id}/sessions/{session_id}", headers=headers)
    assert gone.status_code == 404


@pytest.mark.integration
def test_get_unknown_session_returns_404(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    resp = client.get(f"/api/courses/{course.id}/sessions/does-not-exist", headers=_auth(user.id))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_session_not_visible_to_another_user(client, db):
    owner = make_user(db)
    intruder = make_user(db)
    course, _ = make_course_with_lessons(db)

    created = client.post(
        f"/api/courses/{course.id}/sessions", json={}, headers=_auth(owner.id)
    )
    session_id = created.json()["id"]

    resp = client.get(
        f"/api/courses/{course.id}/sessions/{session_id}", headers=_auth(intruder.id)
    )
    assert resp.status_code == 404

    listed = client.get(f"/api/courses/{course.id}/sessions", headers=_auth(intruder.id))
    assert listed.json() == []


@pytest.mark.integration
def test_another_user_cannot_delete_session(client, db):
    owner = make_user(db)
    intruder = make_user(db)
    course, _ = make_course_with_lessons(db)

    created = client.post(
        f"/api/courses/{course.id}/sessions", json={}, headers=_auth(owner.id)
    )
    session_id = created.json()["id"]

    resp = client.delete(
        f"/api/courses/{course.id}/sessions/{session_id}", headers=_auth(intruder.id)
    )
    assert resp.status_code == 404

    still_there = client.get(
        f"/api/courses/{course.id}/sessions/{session_id}", headers=_auth(owner.id)
    )
    assert still_there.status_code == 200


# ---------------------------------------------------------------------------
# Course isolation
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_session_not_reachable_from_a_different_course_path(client, db):
    user = make_user(db)
    course_a, _ = make_course_with_lessons(db)
    course_b, _ = make_course_with_lessons(db)

    created = client.post(
        f"/api/courses/{course_a.id}/sessions", json={}, headers=_auth(user.id)
    )
    session_id = created.json()["id"]

    resp = client.get(
        f"/api/courses/{course_b.id}/sessions/{session_id}", headers=_auth(user.id)
    )
    assert resp.status_code == 404

    deleted = client.delete(
        f"/api/courses/{course_b.id}/sessions/{session_id}", headers=_auth(user.id)
    )
    assert deleted.status_code == 404

    still_there = client.get(
        f"/api/courses/{course_a.id}/sessions/{session_id}", headers=_auth(user.id)
    )
    assert still_there.status_code == 200


# ---------------------------------------------------------------------------
# Historical turn import (localStorage migration)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_import_turn_appends_to_own_session(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    headers = _auth(user.id)

    session_id = client.post(
        f"/api/courses/{course.id}/sessions", json={}, headers=headers
    ).json()["id"]

    resp = client.post(
        f"/api/courses/{course.id}/sessions/{session_id}/turns",
        json={
            "action": "explain",
            "query": "What is a UTXO?",
            "answer": "A UTXO is an unspent transaction output.",
            "citations": [{"doc_id": "d1", "doc_name": "intro.pdf", "snippet": "..."}],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["query"] == "What is a UTXO?"

    detail = client.get(f"/api/courses/{course.id}/sessions/{session_id}", headers=headers)
    assert len(detail.json()["turns"]) == 1


@pytest.mark.integration
def test_import_turn_rejects_foreign_session(client, db):
    owner = make_user(db)
    intruder = make_user(db)
    course, _ = make_course_with_lessons(db)

    session_id = client.post(
        f"/api/courses/{course.id}/sessions", json={}, headers=_auth(owner.id)
    ).json()["id"]

    resp = client.post(
        f"/api/courses/{course.id}/sessions/{session_id}/turns",
        json={"action": "explain", "query": "q", "answer": "a", "citations": []},
        headers=_auth(intruder.id),
    )
    assert resp.status_code == 404
