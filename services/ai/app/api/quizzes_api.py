"""Quizzes API controller - HTTP + error mapping."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel

from app.middleware.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["Quizzes"])


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
    response_model=List[QuizSummary],
    summary="List quizzes for a course",
    status_code=status.HTTP_200_OK,
)
def list_quizzes(
    course_id: str = Path(..., description="Course ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> List[QuizSummary]:
    # TODO: implement quiz listing once quiz_service is built
    return []


@router.get(
    "/quizzes/{quiz_id}",
    response_model=QuizDetail,
    summary="Get quiz questions",
)
def get_quiz(
    quiz_id: str = Path(..., description="Quiz ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> QuizDetail:
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Quiz", identifier=quiz_id)


@router.post(
    "/quizzes/{quiz_id}/attempts",
    response_model=QuizAttemptResult,
    status_code=status.HTTP_201_CREATED,
    summary="Submit quiz answers",
)
def submit_quiz(
    body: SubmitAnswersRequest,
    quiz_id: str = Path(..., description="Quiz ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> QuizAttemptResult:
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Quiz", identifier=quiz_id)
