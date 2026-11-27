"""Study session repository - data access for persisted study history."""
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import StudySession, StudyTurn


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(
    db: Session, user_id: str, course_id: str, title: Optional[str] = None
) -> StudySession:
    now = _utcnow()
    record = StudySession(
        user_id=user_id,
        course_id=course_id,
        title=title,
        started_at=now,
        last_active_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_sessions_with_turn_counts(
    db: Session, user_id: str, course_id: str
) -> List[Tuple[StudySession, int]]:
    """List sessions with their turn count in a single query (no N+1 COUNT per row)."""
    rows = (
        db.query(StudySession, func.count(StudyTurn.id))
        .outerjoin(StudyTurn, StudyTurn.session_id == StudySession.id)
        .filter(
            StudySession.user_id == user_id, StudySession.course_id == course_id
        )
        .group_by(StudySession.id)
        .order_by(StudySession.last_active_at.desc())
        .all()
    )
    return [(session, int(count)) for session, count in rows]


def get_session(db: Session, user_id: str, session_id: str) -> Optional[StudySession]:
    return (
        db.query(StudySession)
        .filter_by(id=session_id, user_id=user_id)
        .first()
    )


def delete_session(db: Session, user_id: str, session_id: str) -> bool:
    record = get_session(db, user_id, session_id)
    if record is None:
        return False
    db.delete(record)
    db.commit()
    return True


def touch_session(db: Session, session_id: str) -> None:
    """Bump last_active_at. Does not commit — callers batch it with their own write."""
    db.query(StudySession).filter_by(id=session_id).update(
        {"last_active_at": _utcnow()}
    )


def append_turn(
    db: Session,
    user_id: str,
    session_id: str,
    action: str,
    query: str,
    answer: str,
    citations_json: str,
    duration_ms: Optional[int] = None,
    model_tier: Optional[str] = None,
) -> Optional[StudyTurn]:
    """Append a turn to a session owned by user_id.

    Returns None — mirroring get_session's pattern — both when the session
    does not exist and when it belongs to another user, instead of writing a
    turn against an arbitrary session_id (which would orphan the row on
    SQLite or raise IntegrityError on Postgres) or raising in a way that
    reveals whether the session exists to someone who doesn't own it.
    """
    owned = get_session(db, user_id, session_id)
    if owned is None:
        return None

    record = StudyTurn(
        session_id=session_id,
        action=action,
        query=query,
        answer=answer,
        citations_json=citations_json,
        duration_ms=duration_ms,
        model_tier=model_tier,
        created_at=_utcnow(),
    )
    db.add(record)
    touch_session(db, session_id)
    db.commit()
    db.refresh(record)
    return record


def list_turns(db: Session, session_id: str) -> List[StudyTurn]:
    return (
        db.query(StudyTurn)
        .filter_by(session_id=session_id)
        .order_by(StudyTurn.created_at)
        .all()
    )


def count_turns(db: Session, session_id: str) -> int:
    return db.query(StudyTurn).filter_by(session_id=session_id).count()
