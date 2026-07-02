"""Course repository - data access for course aggregate."""
from typing import Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Chapter, Course, Lesson, Section

_DEFAULT_SECTION_TITLE = "User Courses"


def _get_or_create_default_section(db: Session) -> str:
    section = db.query(Section).filter(Section.title == _DEFAULT_SECTION_TITLE).first()
    if section is None:
        section = Section(title=_DEFAULT_SECTION_TITLE)
        db.add(section)
        db.flush()
    return section.id


def create_course(db: Session, title: str, description: Optional[str] = None) -> Course:
    section_id = _get_or_create_default_section(db)
    course = Course(title=title, description=description, section_id=section_id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def get_all_courses(db: Session, skip: int = 0, limit: int = 100) -> List[Course]:
    return db.query(Course).filter(Course.is_active == True).offset(skip).limit(limit).all()


def get_course_by_id(db: Session, course_id: str) -> Optional[Course]:
    return db.query(Course).filter(Course.id == course_id, Course.is_active == True).first()


def get_lessons_by_course_id(db: Session, course_id: str) -> List[Lesson]:
    return (
        db.query(Lesson)
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(Chapter.course_id == course_id)
        .order_by(Chapter.order_index, Lesson.order_index)
        .all()
    )


def get_lesson_by_id(db: Session, lesson_id: str) -> Optional[Lesson]:
    return db.query(Lesson).filter(Lesson.id == lesson_id).first()


def update_course(
    db: Session, course_id: str, title: str, description: Optional[str] = None
) -> Optional[Course]:
    course = get_course_by_id(db, course_id)
    if course is None:
        return None
    course.title = title
    course.description = description
    db.commit()
    db.refresh(course)
    return course


def delete_course_cascade(db: Session, course_id: str) -> Optional[Dict[str, int]]:
    """Delete every DB-owned child of a course, then soft-delete the course row.

    The course row itself stays soft-deleted (is_active=False) rather than
    hard-deleted: Certificate.course_id is a FK to course.id and certificates
    are revoked, not removed, so verification stays honest for anyone who
    kept a link — a hard course delete would either violate that FK or force
    nulling course_id on historical certificates, losing provenance.

    Documents are NOT deleted here — document_service.delete_document handles
    their file/QVAC/chunk_parent side effects and is called per-document by
    the caller (course_service.delete_course) before this runs.

    Does NOT commit — the caller commits once, after this cascade, the
    document deletions, and certificate revocation all succeed, so a
    mid-operation failure rolls back the whole delete instead of leaving a
    course partially deleted (documents gone, chapters/lessons/quizzes
    still there, course still is_active=True).

    Returns None if the course doesn't exist, otherwise a dict of row counts
    deleted per entity, for the caller to report back to the client.
    """
    from app.db.models import (
        AttemptAnswer,
        ChapterTest,
        ChapterTestQuiz,
        GenerationRun,
        OptionChoice,
        Question,
        Quiz,
        QuizAttempt,
        UserCourseProgress,
        UserLessonProgress,
    )

    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        return None

    chapter_ids = [c.id for c in db.query(Chapter.id).filter(Chapter.course_id == course_id).all()]
    lesson_ids = [
        row.id for row in db.query(Lesson.id).filter(Lesson.chapter_id.in_(chapter_ids)).all()
    ] if chapter_ids else []

    # Quizzes attached to this course at any scope: per-lesson, per-course
    # ad-hoc, and chapter tests (via the chapter_test_quiz join).
    chapter_test_ids = [
        row.id for row in db.query(ChapterTest.id).filter(ChapterTest.chapter_id.in_(chapter_ids)).all()
    ] if chapter_ids else []
    quiz_id_subq = (
        db.query(Quiz.id)
        .outerjoin(ChapterTestQuiz, ChapterTestQuiz.quiz_id == Quiz.id)
        .filter(
            or_(
                Quiz.course_id == course_id,
                Quiz.lesson_id.in_(lesson_ids),
                ChapterTestQuiz.chapter_test_id.in_(chapter_test_ids),
            )
        )
    )
    quiz_ids = [row.id for row in quiz_id_subq.all()]

    question_ids = [
        row.id for row in db.query(Question.id).filter(Question.quiz_id.in_(quiz_ids)).all()
    ] if quiz_ids else []
    attempt_ids = [
        row.id for row in db.query(QuizAttempt.id).filter(QuizAttempt.quiz_id.in_(quiz_ids)).all()
    ] if quiz_ids else []

    counts: Dict[str, int] = {}

    if attempt_ids:
        counts["attempt_answers"] = (
            db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id.in_(attempt_ids)).delete(synchronize_session=False)
        )
        counts["quiz_attempts"] = (
            db.query(QuizAttempt).filter(QuizAttempt.id.in_(attempt_ids)).delete(synchronize_session=False)
        )
    if question_ids:
        counts["option_choices"] = (
            db.query(OptionChoice).filter(OptionChoice.question_id.in_(question_ids)).delete(synchronize_session=False)
        )
        counts["questions"] = (
            db.query(Question).filter(Question.id.in_(question_ids)).delete(synchronize_session=False)
        )
    if chapter_test_ids:
        counts["chapter_test_quiz_links"] = (
            db.query(ChapterTestQuiz).filter(ChapterTestQuiz.chapter_test_id.in_(chapter_test_ids)).delete(synchronize_session=False)
        )
        counts["chapter_tests"] = (
            db.query(ChapterTest).filter(ChapterTest.id.in_(chapter_test_ids)).delete(synchronize_session=False)
        )
    if quiz_ids:
        counts["quizzes"] = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)

    if lesson_ids:
        counts["lesson_progress"] = (
            db.query(UserLessonProgress).filter(UserLessonProgress.lesson_id.in_(lesson_ids)).delete(synchronize_session=False)
        )
        counts["lessons"] = db.query(Lesson).filter(Lesson.id.in_(lesson_ids)).delete(synchronize_session=False)
    if chapter_ids:
        counts["chapters"] = db.query(Chapter).filter(Chapter.id.in_(chapter_ids)).delete(synchronize_session=False)

    counts["course_progress"] = (
        db.query(UserCourseProgress).filter(UserCourseProgress.course_id == course_id).delete(synchronize_session=False)
    )
    counts["generation_runs"] = (
        db.query(GenerationRun).filter(GenerationRun.course_id == course_id).delete(synchronize_session=False)
    )

    course.is_active = False
    return counts
