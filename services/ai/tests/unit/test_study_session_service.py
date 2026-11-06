"""Unit tests for study_session_service — no HTTP, direct service calls."""
import pytest

from app.schemas.study_session_schemas import TurnCitationOut
from app.services import study_session_service
from tests.conftest import make_course_with_lessons, make_user


@pytest.mark.unit
def test_create_session_starts_empty(db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db, n_lessons=1)

    session = study_session_service.create_session(db, user.id, course.id)

    assert session.course_id == course.id
    assert session.turn_count == 0
    assert session.started_at == session.last_active_at


@pytest.mark.unit
def test_list_sessions_scoped_to_user_and_course(db):
    user_a = make_user(db)
    user_b = make_user(db)
    course, _ = make_course_with_lessons(db, n_lessons=1)
    other_course, _ = make_course_with_lessons(db, n_lessons=1)

    study_session_service.create_session(db, user_a.id, course.id)
    study_session_service.create_session(db, user_a.id, other_course.id)
    study_session_service.create_session(db, user_b.id, course.id)

    sessions = study_session_service.list_sessions(db, user_a.id, course.id)

    assert len(sessions) == 1
    assert sessions[0].course_id == course.id


@pytest.mark.unit
def test_append_turn_updates_turn_count_and_last_active(db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db, n_lessons=1)
    session = study_session_service.create_session(db, user.id, course.id)

    citation = TurnCitationOut(
        doc_id="doc-1",
        doc_name="Intro to Bitcoin",
        page=3,
        chunk_id="chunk-1",
        chunk_type="text",
        snippet="A UTXO is...",
    )
    turn = study_session_service.append_turn(
        db,
        session.id,
        action="explain",
        query="What is a UTXO?",
        answer="A UTXO is an unspent transaction output.",
        citations=[citation],
    )

    assert turn.citations[0].chunk_id == "chunk-1"
    assert turn.citations[0].doc_id == "doc-1"

    detail = study_session_service.get_session(db, user.id, session.id)
    assert detail is not None
    assert detail.turn_count == 1
    assert detail.turns[0].answer == turn.answer
    assert detail.last_active_at >= detail.started_at


@pytest.mark.unit
def test_get_session_returns_none_for_other_user(db):
    owner = make_user(db)
    intruder = make_user(db)
    course, _ = make_course_with_lessons(db, n_lessons=1)
    session = study_session_service.create_session(db, owner.id, course.id)

    assert study_session_service.get_session(db, intruder.id, session.id) is None


@pytest.mark.unit
def test_get_session_returns_none_for_unknown_id(db):
    user = make_user(db)
    assert study_session_service.get_session(db, user.id, "does-not-exist") is None


@pytest.mark.unit
def test_delete_session_is_scoped_to_owner(db):
    owner = make_user(db)
    intruder = make_user(db)
    course, _ = make_course_with_lessons(db, n_lessons=1)
    session = study_session_service.create_session(db, owner.id, course.id)

    assert study_session_service.delete_session(db, intruder.id, session.id) is False
    assert study_session_service.get_session(db, owner.id, session.id) is not None

    assert study_session_service.delete_session(db, owner.id, session.id) is True
    assert study_session_service.get_session(db, owner.id, session.id) is None


@pytest.mark.unit
def test_deleting_session_cascades_turns(db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db, n_lessons=1)
    session = study_session_service.create_session(db, user.id, course.id)
    study_session_service.append_turn(
        db, session.id, action="explain", query="q", answer="a", citations=[]
    )

    study_session_service.delete_session(db, user.id, session.id)

    from app.repositories import study_session_repo
    assert study_session_repo.list_turns(db, session.id) == []
