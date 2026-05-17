"""Quizzes API controller - HTTP + error mapping."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Path, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.middleware.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["Quizzes"])

_NOT_FOUND = JSONResponse(
    status_code=status.HTTP_404_NOT_FOUND,
    content={"error": {"code": "quiz_not_found", "message": "Quiz not found"}},
)


class QuizSummary(BaseModel):
    id: str
    title: Optional[str]
    scope: str
    passing_score: int
    question_count: int


class QuestionOut(BaseModel):
    id: str
    prompt: str
    qtype: str
    order_index: int
    options: List[Dict[str, Any]]


class QuizDetail(BaseModel):
    id: str
    title: Optional[str]
    scope: str
    passing_score: int
    questions: List[QuestionOut]


class SubmitAnswersRequest(BaseModel):
    answers: Dict[str, str]


class QuizAttemptResult(BaseModel):
    attempt_id: str
    score_pct: int
    passed: bool
    correct_count: int
    total_count: int


@router.get(
    "/courses/{course_id}/quizzes",
    summary="List quizzes for a course",
)
def list_quizzes(
    course_id: str = Path(..., description="Course ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_200_OK, content=[])


@router.get(
    "/quizzes/{quiz_id}",
    summary="Get quiz questions",
)
def get_quiz(
    quiz_id: str = Path(..., description="Quiz ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    return _NOT_FOUND


@router.post(
    "/quizzes/{quiz_id}/attempts",
    summary="Submit quiz answers",
)
def submit_quiz(
    body: SubmitAnswersRequest,
    quiz_id: str = Path(..., description="Quiz ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    return _NOT_FOUND
