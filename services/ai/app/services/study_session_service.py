"""Study session service - business logic for persisted study history (issue #136)."""
import json
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import StudySession, StudyTurn
from app.repositories import study_session_repo
from app.schemas.study_session_schemas import (
    StudySessionDetailOut,
    StudySessionOut,
    StudyTurnOut,
    TurnCitationOut,
)


def _to_session_response(record: StudySession, turn_count: int) -> StudySessionOut:
    return StudySessionOut(
        id=record.id,
        course_id=record.course_id,
        title=record.title,
        started_at=str(record.started_at),
        last_active_at=str(record.last_active_at),
        turn_count=turn_count,
    )


def _to_turn_response(record: StudyTurn) -> StudyTurnOut:
    raw_citations = json.loads(record.citations_json or "[]")
    return StudyTurnOut(
        id=record.id,
        action=record.action,
        query=record.query,
        answer=record.answer,
        citations=[TurnCitationOut(**c) for c in raw_citations],
        duration_ms=record.duration_ms,
        model_tier=record.model_tier,
        created_at=str(record.created_at),
    )


def create_session(
    db: Session, user_id: str, course_id: str, title: Optional[str] = None
) -> StudySessionOut:
    record = study_session_repo.create_session(db, user_id, course_id, title)
    return _to_session_response(record, turn_count=0)


def list_sessions(db: Session, user_id: str, course_id: str) -> List[StudySessionOut]:
    records = study_session_repo.list_sessions(db, user_id, course_id)
    return [
        _to_session_response(r, study_session_repo.count_turns(db, r.id))
        for r in records
    ]


def get_session(
    db: Session, user_id: str, session_id: str
) -> Optional[StudySessionDetailOut]:
    """Return a session with its turns, scoped to the requesting user.

    Returns None both when the session does not exist and when it belongs to
    another user — the two cases are indistinguishable to the caller, which
    is what keeps this a cross-user leak-proof lookup rather than a 403 that
    confirms the session's existence to someone who doesn't own it.
    """
    record = study_session_repo.get_session(db, user_id, session_id)
    if record is None:
        return None
    turns = study_session_repo.list_turns(db, session_id)
    base = _to_session_response(record, turn_count=len(turns))
    return StudySessionDetailOut(
        **base.model_dump(),
        turns=[_to_turn_response(t) for t in turns],
    )


def delete_session(db: Session, user_id: str, session_id: str) -> bool:
    return study_session_repo.delete_session(db, user_id, session_id)


def append_turn(
    db: Session,
    session_id: str,
    action: str,
    query: str,
    answer: str,
    citations: List[TurnCitationOut],
    duration_ms: Optional[int] = None,
    model_tier: Optional[str] = None,
) -> StudyTurnOut:
    citations_json = json.dumps([c.model_dump() for c in citations])
    record = study_session_repo.append_turn(
        db,
        session_id,
        action,
        query,
        answer,
        citations_json,
        duration_ms,
        model_tier,
    )
    return _to_turn_response(record)
