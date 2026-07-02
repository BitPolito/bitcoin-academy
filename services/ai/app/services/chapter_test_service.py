"""Chapter tests — P5 of the course builder roadmap.

Design: zero LLM calls at runtime. A chapter test is a *selection* of
questions already generated for the chapter's lessons (by the course
builder's lesson-quiz generation, see lesson_service.py / quiz_generation.py),
copied into a standalone Quiz(scope=CHAPTER_TEST) so it survives independent
of any later regeneration of the source lesson quizzes.

This keeps chapter tests on the cheapest rung of the inference ladder
described in docs/agent-memory-plan.md: a DB read + a few inserts, no model
call, no latency, no cost.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import (
    Chapter,
    ChapterTest,
    ChapterTestQuiz,
    Lesson,
    OptionChoice,
    Question,
    Quiz,
    QuizScope,
)

MAX_QUESTIONS_PER_TEST = 10
MAX_QUESTIONS_PER_LESSON = 2


def _select_questions(db: Session, lessons: List[Lesson]) -> List[Question]:
    """Round-robin across lessons, capped per lesson, preferring unseen
    concept_tag when a lesson offers more than one candidate on its turn."""
    lesson_ids = [ls.id for ls in lessons]
    quizzes = (
        db.query(Quiz)
        .filter(Quiz.lesson_id.in_(lesson_ids), Quiz.scope == QuizScope.LESSON)
        # A lesson can have more than one Quiz row now that persist_quiz
        # keeps an attempted quiz in place and versions alongside it
        # instead of deleting it (see quiz_generation.persist_quiz) —
        # ascending created_at means the dict below keeps the newest.
        .order_by(Quiz.created_at.asc())
        .all()
    )
    quiz_by_lesson = {q.lesson_id: q for q in quizzes}

    pools: Dict[str, List[Question]] = {}
    for lesson_id, quiz in quiz_by_lesson.items():
        pools[lesson_id] = (
            db.query(Question)
            .filter(Question.quiz_id == quiz.id)
            .order_by(Question.order_index)
            .all()
        )

    selected: List[Question] = []
    seen_tags: set = set()
    taken_per_lesson: Dict[str, int] = {lid: 0 for lid in pools}

    # Each lesson's pool is consumed independently: a pick removes the
    # question from that lesson's own list, so one lesson's turn can never
    # advance or skip past another lesson's remaining candidates (the
    # earlier shared round_idx pointer caused exactly that cross-lesson
    # skipping — see docs/next-features-plan.md P5 test coverage).
    made_progress = True
    while len(selected) < MAX_QUESTIONS_PER_TEST and made_progress:
        made_progress = False
        for lesson_id in lesson_ids:
            if len(selected) >= MAX_QUESTIONS_PER_TEST:
                break
            if taken_per_lesson.get(lesson_id, 0) >= MAX_QUESTIONS_PER_LESSON:
                continue
            pool = pools.get(lesson_id, [])
            if not pool:
                continue

            # Prefer a not-yet-used concept_tag among the lesson's remaining
            # candidates; fall back to the earliest-ordered one otherwise.
            candidate = next(
                (q for q in pool if q.concept_tag and q.concept_tag not in seen_tags),
                pool[0],
            )
            pool.remove(candidate)
            selected.append(candidate)
            if candidate.concept_tag:
                seen_tags.add(candidate.concept_tag)
            taken_per_lesson[lesson_id] += 1
            made_progress = True

    return selected


def _copy_questions_into_quiz(db: Session, quiz_id: str, questions: List[Question]) -> None:
    for order_idx, src_q in enumerate(questions):
        new_q = Question(
            id=str(uuid.uuid4()),
            quiz_id=quiz_id,
            qtype=src_q.qtype,
            prompt=src_q.prompt,
            order_index=order_idx,
            concept_tag=src_q.concept_tag,
            difficulty=src_q.difficulty,
        )
        db.add(new_q)
        db.flush()

        for opt in db.query(OptionChoice).filter(OptionChoice.question_id == src_q.id).all():
            db.add(OptionChoice(
                id=str(uuid.uuid4()),
                question_id=new_q.id,
                label=opt.label,
                is_correct=opt.is_correct,
            ))


def get_current_chapter_test(db: Session, chapter_id: str) -> Optional[ChapterTest]:
    """Most recent test for a chapter — 'most recent' = its quiz's created_at,
    since ChapterTest itself has no timestamp column."""
    return (
        db.query(ChapterTest)
        .join(ChapterTestQuiz, ChapterTestQuiz.chapter_test_id == ChapterTest.id)
        .join(Quiz, Quiz.id == ChapterTestQuiz.quiz_id)
        .filter(ChapterTest.chapter_id == chapter_id)
        .order_by(Quiz.created_at.desc())
        .first()
    )


def build_chapter_test(db: Session, chapter_id: str) -> Optional[ChapterTest]:
    """Build (or version) a chapter test from the chapter's published lesson quizzes.

    If a previous test exists and its quiz has no recorded attempts, it is
    replaced in place (deleted + rebuilt) — no value in keeping an
    unattempted draft around. If it has attempts, a new ChapterTest/Quiz pair
    is created alongside it, preserving the old one (and its attempt history)
    untouched; get_current_chapter_test always returns the newest.

    Returns None if the chapter doesn't exist or has no published lessons
    with a generated quiz.
    """
    from app.db.models import QuizAttempt  # local import avoids a cycle at module load

    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if chapter is None:
        return None

    lessons = (
        db.query(Lesson)
        .filter(Lesson.chapter_id == chapter_id, Lesson.status == "published")
        .order_by(Lesson.order_index)
        .all()
    )
    if not lessons:
        return None

    questions = _select_questions(db, lessons)
    if not questions:
        return None

    previous = get_current_chapter_test(db, chapter_id)
    if previous is not None:
        prev_link = db.query(ChapterTestQuiz).filter(
            ChapterTestQuiz.chapter_test_id == previous.id
        ).first()
        prev_quiz_id = prev_link.quiz_id if prev_link else None
        has_attempts = bool(
            prev_quiz_id
            and db.query(QuizAttempt).filter(QuizAttempt.quiz_id == prev_quiz_id).first()
        )
        if not has_attempts and prev_quiz_id:
            for q in db.query(Question).filter(Question.quiz_id == prev_quiz_id).all():
                db.query(OptionChoice).filter(OptionChoice.question_id == q.id).delete()
                db.delete(q)
            db.query(ChapterTestQuiz).filter(ChapterTestQuiz.chapter_test_id == previous.id).delete()
            db.delete(previous)
            db.query(Quiz).filter(Quiz.id == prev_quiz_id).delete()
            db.flush()

    quiz = Quiz(
        id=str(uuid.uuid4()),
        scope=QuizScope.CHAPTER_TEST,
        title=f"Chapter Test: {chapter.title[:80]}",
        # Explicit microsecond-precision timestamp, not the func.now() column
        # default: SQLite's now() has 1-second resolution, which makes
        # get_current_chapter_test's "most recent" ordering ambiguous when
        # two versions are built within the same second.
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(quiz)
    db.flush()

    _copy_questions_into_quiz(db, quiz.id, questions)

    chapter_test = ChapterTest(
        id=str(uuid.uuid4()),
        chapter_id=chapter_id,
        title=f"Test: {chapter.title[:80]}",
    )
    db.add(chapter_test)
    db.flush()

    db.add(ChapterTestQuiz(chapter_test_id=chapter_test.id, quiz_id=quiz.id, order_index=0))
    db.commit()
    db.refresh(chapter_test)
    return chapter_test


def get_chapter_test_quiz(db: Session, chapter_test: ChapterTest) -> Optional[Quiz]:
    link = db.query(ChapterTestQuiz).filter(
        ChapterTestQuiz.chapter_test_id == chapter_test.id
    ).order_by(ChapterTestQuiz.order_index).first()
    if link is None:
        return None
    return db.query(Quiz).filter(Quiz.id == link.quiz_id).first()
