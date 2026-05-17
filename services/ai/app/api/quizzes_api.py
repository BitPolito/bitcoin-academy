"""Quizzes API — generate and evaluate quizzes via the study pipeline."""
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.rate_limit import limiter
from app.middleware.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["Quizzes"])

# In-memory store: quiz_id → quiz dict. Cleared on restart; fine for demo.
_quiz_store: Dict[str, Dict[str, Any]] = {}

_NOT_FOUND = JSONResponse(
    status_code=status.HTTP_404_NOT_FOUND,
    content={"error": {"code": "quiz_not_found", "message": "Quiz not found"}},
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateQuizRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=500, description="Topic to quiz on")


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
    answers: Dict[str, str]  # question_id → chosen key (A/B/C/D)


class QuizAttemptResult(BaseModel):
    attempt_id: str
    score_pct: int
    passed: bool
    correct_count: int
    total_count: int


# ---------------------------------------------------------------------------
# LLM output parser
# ---------------------------------------------------------------------------

def _parse_quiz_text(raw: str) -> tuple[list[dict], dict[str, str]]:
    """Parse LLM quiz output into (questions, correct_answers).

    Expected format per question:
        Q: <question text>
        A) <option>
        B) <option>
        C) <option>
        D) <option>
        Answer: <letter> [ref_N]
    """
    questions: list[dict] = []
    correct_answers: dict[str, str] = {}  # question_id → "A"|"B"|"C"|"D"

    blocks = re.split(r'(?:^|\n)(?=Q:)', raw.strip())

    for order_idx, block in enumerate(blocks):
        block = block.strip()
        if not block.upper().startswith("Q:"):
            continue

        q_id = str(uuid.uuid4())
        lines = block.splitlines()
        i = 0

        # Question text (may span multiple lines until first option)
        prompt_parts: list[str] = [re.sub(r'^Q:\s*', '', lines[0], flags=re.I).strip()]
        i = 1
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r'^[A-D]\)', line) or re.match(r'^Answer:', line, re.I):
                break
            if line:
                prompt_parts.append(line)
            i += 1

        prompt = ' '.join(prompt_parts).strip()

        # Options (A–D) and Answer line
        options: list[dict] = []
        correct_key: str | None = None

        while i < len(lines):
            line = lines[i].strip()
            opt_m = re.match(r'^([A-D])\)\s*(.+)', line)
            ans_m = re.match(r'^Answer:\s*([A-D])', line, re.I)

            if opt_m:
                key, text_parts = opt_m.group(1), [opt_m.group(2)]
                i += 1
                while i < len(lines):
                    nxt = lines[i].strip()
                    if re.match(r'^[A-D]\)', nxt) or re.match(r'^Answer:', nxt, re.I) or not nxt:
                        break
                    text_parts.append(nxt)
                    i += 1
                options.append({"key": key, "text": ' '.join(text_parts)})
            elif ans_m:
                correct_key = ans_m.group(1).upper()
                i += 1
            else:
                i += 1

        if prompt and len(options) >= 2:
            questions.append({
                "id": q_id,
                "prompt": prompt,
                "qtype": "mcq",
                "order_index": order_idx,
                "options": options,
            })
            if correct_key:
                correct_answers[q_id] = correct_key

    return questions, correct_answers


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/quizzes/generate",
    summary="Generate a quiz from course material",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def generate_quiz(
    request: Request,
    body: GenerateQuizRequest,
    course_id: str = Path(..., description="Course to generate quiz from"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    from app.schemas.study_schemas import StudyAction  # noqa: PLC0415
    from app.services import study_service  # noqa: PLC0415

    result = await study_service.dispatch(
        question=body.query,
        course_id=course_id,
        action=StudyAction.QUIZ,
    )

    questions, correct_answers = _parse_quiz_text(result.answer)
    if not questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not parse quiz questions from the generated content. Try a more specific topic.",
        )

    quiz_id = str(uuid.uuid4())
    title = f"Quiz: {body.query[:60]}"

    _quiz_store[quiz_id] = {
        "id": quiz_id,
        "title": title,
        "scope": course_id,
        "passing_score": 75,
        "questions": questions,
        "correct_answers": correct_answers,
    }

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=QuizDetail(
            id=quiz_id,
            title=title,
            scope=course_id,
            passing_score=75,
            questions=[QuestionOut(**q) for q in questions],
        ).model_dump(),
    )


@router.get(
    "/courses/{course_id}/quizzes",
    summary="List generated quizzes for a course",
)
def list_quizzes(
    course_id: str = Path(..., description="Course ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    summaries = [
        QuizSummary(
            id=q["id"],
            title=q["title"],
            scope=q["scope"],
            passing_score=q["passing_score"],
            question_count=len(q["questions"]),
        ).model_dump()
        for q in _quiz_store.values()
        if q["scope"] == course_id
    ]
    return JSONResponse(status_code=status.HTTP_200_OK, content=summaries)


@router.get(
    "/quizzes/{quiz_id}",
    summary="Get quiz questions",
)
def get_quiz(
    quiz_id: str = Path(..., description="Quiz ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    quiz = _quiz_store.get(quiz_id)
    if not quiz:
        return _NOT_FOUND

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=QuizDetail(
            id=quiz["id"],
            title=quiz["title"],
            scope=quiz["scope"],
            passing_score=quiz["passing_score"],
            questions=[QuestionOut(**q) for q in quiz["questions"]],
        ).model_dump(),
    )


@router.post(
    "/quizzes/{quiz_id}/attempts",
    summary="Submit quiz answers and receive score",
)
def submit_quiz(
    body: SubmitAnswersRequest,
    quiz_id: str = Path(..., description="Quiz ID"),
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    quiz = _quiz_store.get(quiz_id)
    if not quiz:
        return _NOT_FOUND

    correct_answers = quiz["correct_answers"]
    total = len(correct_answers)
    correct_count = sum(
        1
        for q_id, submitted_key in body.answers.items()
        if correct_answers.get(q_id, "").upper() == submitted_key.upper()
    )
    score_pct = round(correct_count / total * 100) if total > 0 else 0

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=QuizAttemptResult(
            attempt_id=str(uuid.uuid4()),
            score_pct=score_pct,
            passed=score_pct >= quiz["passing_score"],
            correct_count=correct_count,
            total_count=total,
        ).model_dump(),
    )
