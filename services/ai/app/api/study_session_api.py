"""Study session API controller — server-side persistence of study history (issue #136).

A session belongs to exactly one user and one course. Every lookup below is
scoped to the requesting user; a session that exists but belongs to someone
else is reported as not found rather than forbidden, so its existence is
never confirmed to a user who doesn't own it.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import TokenPayload
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.study_session_schemas import (
    StudySessionDetailOut,
    StudySessionOut,
    StudyTurnOut,
    TurnCitationOut,
)
from app.services import study_session_service

router = APIRouter(prefix="/api", tags=["Study sessions"])


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


@router.post(
    "/courses/{course_id}/sessions",
    response_model=StudySessionOut,
    summary="Create a study session",
)
def create_session(
    body: CreateSessionRequest,
    course_id: str = Path(..., description="Course this session belongs to"),
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudySessionOut:
    return study_session_service.create_session(db, current_user.sub, course_id, body.title)


@router.get(
    "/courses/{course_id}/sessions",
    response_model=List[StudySessionOut],
    summary="List the current user's study sessions for a course",
)
def list_sessions(
    course_id: str = Path(...),
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> List[StudySessionOut]:
    return study_session_service.list_sessions(db, current_user.sub, course_id)


@router.get(
    "/courses/{course_id}/sessions/{session_id}",
    response_model=StudySessionDetailOut,
    summary="Get a study session with its turns",
)
def get_session(
    course_id: str = Path(...),
    session_id: str = Path(...),
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudySessionDetailOut:
    detail = study_session_service.get_session(db, current_user.sub, session_id)
    if detail is None or detail.course_id != course_id:
        raise NotFoundError(resource="Study session", identifier=session_id)
    return detail


class ImportTurnRequest(BaseModel):
    """One historical turn, verbatim — used only to migrate pre-existing
    localStorage study history into a session on first load (issue #136).
    The live dispatch path (POST .../study[/stream]) persists turns itself;
    this endpoint exists solely for that one-time, client-initiated import,
    not for general turn creation.
    """

    action: str = Field(..., max_length=50)
    query: str = Field(..., max_length=2000)
    answer: str = Field(..., max_length=20000)
    citations: List[TurnCitationOut] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    model_tier: Optional[str] = Field(default=None, max_length=50)


@router.post(
    "/courses/{course_id}/sessions/{session_id}/turns",
    response_model=StudyTurnOut,
    summary="Import a historical turn into a session (localStorage migration only)",
)
def import_turn(
    body: ImportTurnRequest,
    course_id: str = Path(...),
    session_id: str = Path(...),
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyTurnOut:
    detail = study_session_service.get_session(db, current_user.sub, session_id)
    if detail is None or detail.course_id != course_id:
        raise NotFoundError(resource="Study session", identifier=session_id)
    turn = study_session_service.append_turn(
        db,
        current_user.sub,
        session_id,
        action=body.action,
        query=body.query,
        answer=body.answer,
        citations=body.citations,
        duration_ms=body.duration_ms,
        model_tier=body.model_tier,
    )
    # append_turn only returns None for a session that doesn't exist/isn't
    # owned by the caller — already ruled out by the get_session check above.
    assert turn is not None
    return turn


@router.delete(
    "/courses/{course_id}/sessions/{session_id}",
    summary="Delete a study session and its turns",
)
def delete_session(
    course_id: str = Path(...),
    session_id: str = Path(...),
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    # Scope the existence check to this course before deleting, same as get_session,
    # so a session_id guessed/reused across courses can't be deleted cross-course.
    detail = study_session_service.get_session(db, current_user.sub, session_id)
    if detail is None or detail.course_id != course_id:
        raise NotFoundError(resource="Study session", identifier=session_id)
    study_session_service.delete_session(db, current_user.sub, session_id)
    return {"status": "deleted"}
