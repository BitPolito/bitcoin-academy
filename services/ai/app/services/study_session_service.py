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


def _to_citation(raw: dict) -> Optional[TurnCitationOut]:
    """Build a citation anchor from stored JSON, degrading gracefully.

    A citation stored without a doc_id (e.g. imported from a client payload
    that never carried one, as the planned localStorage import will) must
    not blow up the whole turn — it is dropped rather than raised.
    """
    try:
        return TurnCitationOut(**raw)
    except (TypeError, ValueError):
        return None


def _to_turn_response(record: StudyTurn) -> StudyTurnOut:
    raw_citations = json.loads(record.citations_json or "[]")
    citations = [_to_citation(c) for c in raw_citations]
    return StudyTurnOut(
        id=record.id,
        action=record.action,
        query=record.query,
        answer=record.answer,
        citations=[c for c in citations if c is not None],
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
    rows = study_session_repo.list_sessions_with_turn_counts(db, user_id, course_id)
    return [_to_session_response(record, turn_count) for record, turn_count in rows]


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
    user_id: str,
    session_id: str,
    action: str,
    query: str,
    answer: str,
    citations: List[TurnCitationOut],
    duration_ms: Optional[int] = None,
    model_tier: Optional[str] = None,
) -> Optional[StudyTurnOut]:
    """Append a turn to a session owned by user_id.

    Returns None — matching get_session's pattern — if the session does not
    exist or belongs to another user, instead of writing the turn against an
    arbitrary session_id.
    """
    citations_json = json.dumps([c.model_dump() for c in citations])
    record = study_session_repo.append_turn(
        db,
        user_id,
        session_id,
        action,
        query,
        answer,
        citations_json,
        duration_ms,
        model_tier,
    )
    if record is None:
        return None
    return _to_turn_response(record)
