"""Study session repository - data access for persisted study history."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import StudySession, StudyTurn


def create_session(
    db: Session, user_id: str, course_id: str, title: Optional[str] = None
) -> StudySession:
    now = datetime.now().isoformat()
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


def list_sessions(db: Session, user_id: str, course_id: str) -> List[StudySession]:
    return (
        db.query(StudySession)
        .filter_by(user_id=user_id, course_id=course_id)
        .order_by(StudySession.last_active_at.desc())
        .all()
    )


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
        {"last_active_at": datetime.now().isoformat()}
    )


def append_turn(
    db: Session,
    session_id: str,
    action: str,
    query: str,
    answer: str,
    citations_json: str,
    duration_ms: Optional[int] = None,
    model_tier: Optional[str] = None,
) -> StudyTurn:
    record = StudyTurn(
        session_id=session_id,
        action=action,
        query=query,
        answer=answer,
        citations_json=citations_json,
        duration_ms=duration_ms,
        model_tier=model_tier,
        created_at=datetime.now().isoformat(),
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
