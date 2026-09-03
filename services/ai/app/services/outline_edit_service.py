"""Transactional manual editing operations for generated course outlines."""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError_
from app.db.models import (
    AttemptAnswer,
    Chapter,
    Lesson,
    OptionChoice,
    Question,
    Quiz,
    QuizAttempt,
    UserLessonProgress,
)
from app.schemas.outline_schemas import OutlineActionBody


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark(item: Chapter | Lesson) -> None:
    item.is_human_modified = True
    item.human_modified_at = _now()


def _chapters(db: Session, course_id: str) -> list[Chapter]:
    return db.query(Chapter).filter(Chapter.course_id == course_id).order_by(Chapter.order_index).all()


def _chapter(db: Session, course_id: str, chapter_id: str | None) -> Chapter:
    row = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.course_id == course_id).first()
    if row is None:
        raise NotFoundError("Chapter", chapter_id)
    return row


def _lesson(db: Session, course_id: str, lesson_id: str | None) -> Lesson:
    row = (db.query(Lesson).join(Chapter).filter(
        Lesson.id == lesson_id, Chapter.course_id == course_id
    ).first())
    if row is None:
        raise NotFoundError("Lesson", lesson_id)
    return row


def _normalize_chapters(db: Session, course_id: str) -> None:
    for index, chapter in enumerate(_chapters(db, course_id)):
        chapter.order_index = index


def _normalize_lessons(db: Session, chapter_id: str) -> None:
    rows = db.query(Lesson).filter(Lesson.chapter_id == chapter_id).order_by(Lesson.order_index).all()
    for index, lesson in enumerate(rows):
        lesson.order_index = index


def _delete_lessons(db: Session, lesson_ids: list[str]) -> None:
    """Delete lesson-owned generated data and progress without leaving orphans."""
    quiz_ids = [row.id for row in db.query(Quiz.id).filter(Quiz.lesson_id.in_(lesson_ids)).all()]
    question_ids = [row.id for row in db.query(Question.id).filter(Question.quiz_id.in_(quiz_ids)).all()]
    attempt_ids = [row.id for row in db.query(QuizAttempt.id).filter(QuizAttempt.quiz_id.in_(quiz_ids)).all()]
    if attempt_ids:
        db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id.in_(attempt_ids)).delete(synchronize_session=False)
        db.query(QuizAttempt).filter(QuizAttempt.id.in_(attempt_ids)).delete(synchronize_session=False)
    if question_ids:
        db.query(OptionChoice).filter(OptionChoice.question_id.in_(question_ids)).delete(synchronize_session=False)
        db.query(Question).filter(Question.id.in_(question_ids)).delete(synchronize_session=False)
    if quiz_ids:
        db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)
    db.query(UserLessonProgress).filter(UserLessonProgress.lesson_id.in_(lesson_ids)).delete(synchronize_session=False)
    db.query(Lesson).filter(Lesson.id.in_(lesson_ids)).delete(synchronize_session=False)


def apply_action(db: Session, course_id: str, body: OutlineActionBody) -> None:
    """Apply one edit atomically. Moving rows preserves their content, quizzes and provenance."""
    action = body.action
    if action == "create_chapter":
        chapter = Chapter(id=str(uuid.uuid4()), course_id=course_id, title=body.title or "New chapter",
                          description=body.description, status="draft", order_index=len(_chapters(db, course_id)))
        _mark(chapter)
        db.add(chapter)
    elif action == "create_lesson":
        chapter = _chapter(db, course_id, body.chapter_id)
        count = db.query(Lesson).filter(Lesson.chapter_id == chapter.id).count()
        lesson = Lesson(id=str(uuid.uuid4()), chapter_id=chapter.id, title=body.title or "New lesson",
                        description=body.description, content="", status="draft", order_index=count)
        _mark(lesson)
        _mark(chapter)
        db.add(lesson)
    elif action == "rename_chapter":
        chapter = _chapter(db, course_id, body.chapter_id)
        chapter.title = body.title or chapter.title
        if body.description is not None:
            chapter.description = body.description
        _mark(chapter)
    elif action == "rename_lesson":
        lesson = _lesson(db, course_id, body.lesson_id)
        lesson.title = body.title or lesson.title
        if body.description is not None:
            lesson.description = body.description
        _mark(lesson)
    elif action == "reorder_chapters":
        chapter_rows = _chapters(db, course_id)
        if set(body.ordered_ids) != {row.id for row in chapter_rows}:
            raise ValidationError_("ordered_ids must contain every chapter exactly once.")
        chapters_by_id = {row.id: row for row in chapter_rows}
        for index, row_id in enumerate(body.ordered_ids):
            chapters_by_id[row_id].order_index = index
            _mark(chapters_by_id[row_id])
    elif action == "reorder_lessons":
        chapter = _chapter(db, course_id, body.chapter_id)
        lesson_rows = db.query(Lesson).filter(Lesson.chapter_id == chapter.id).all()
        if set(body.ordered_ids) != {row.id for row in lesson_rows}:
            raise ValidationError_("ordered_ids must contain every lesson in the chapter exactly once.")
        lessons_by_id = {row.id: row for row in lesson_rows}
        for index, row_id in enumerate(body.ordered_ids):
            lessons_by_id[row_id].order_index = index
            _mark(lessons_by_id[row_id])
        _mark(chapter)
    elif action == "move_lesson":
        lesson = _lesson(db, course_id, body.lesson_id)
        source_id = lesson.chapter_id
        target = _chapter(db, course_id, body.target_chapter_id)
        lesson.chapter = target
        lesson.order_index = db.query(Lesson).filter(Lesson.chapter_id == target.id).count()
        _mark(lesson)
        _mark(target)
        _normalize_lessons(db, source_id)
    elif action == "merge_chapters":
        source = _chapter(db, course_id, body.chapter_id)
        target = _chapter(db, course_id, body.target_chapter_id)
        if source.id == target.id:
            raise ValidationError_("A chapter cannot be merged into itself.")
        next_index = db.query(Lesson).filter(Lesson.chapter_id == target.id).count()
        for lesson in sorted(source.lessons, key=lambda item: item.order_index):
            lesson.chapter = target
            lesson.order_index = next_index
            next_index += 1
            _mark(lesson)
        _mark(target)
        db.delete(source)
        db.flush()
        _normalize_chapters(db, course_id)
    elif action == "split_chapter":
        source = _chapter(db, course_id, body.chapter_id)
        selected = [row for row in source.lessons if row.id in set(body.lesson_ids)]
        if not selected or len(selected) == len(source.lessons):
            raise ValidationError_("Select some, but not all, lessons to split into a new chapter.")
        new = Chapter(id=str(uuid.uuid4()), course_id=course_id, title=body.title or f"{source.title} (split)",
                      description=body.description, status="draft", order_index=source.order_index + 1)
        _mark(source)
        _mark(new)
        db.add(new)
        db.flush()
        for index, lesson in enumerate(sorted(selected, key=lambda item: item.order_index)):
            lesson.chapter = new
            lesson.order_index = index
            _mark(lesson)
        _normalize_lessons(db, source.id)
        _normalize_chapters(db, course_id)
    elif action == "delete_lesson":
        lesson = _lesson(db, course_id, body.lesson_id)
        chapter_id = lesson.chapter_id
        _delete_lessons(db, [lesson.id])
        db.flush()
        _normalize_lessons(db, chapter_id)
    elif action == "delete_chapter":
        chapter = _chapter(db, course_id, body.chapter_id)
        if chapter.lessons and not body.delete_lessons and not body.target_chapter_id:
            raise ValidationError_("Chapter has lessons; confirm deletion or provide target_chapter_id.")
        if body.target_chapter_id:
            target = _chapter(db, course_id, body.target_chapter_id)
            if target.id == chapter.id:
                raise ValidationError_("Target chapter must be different.")
            next_index = len(target.lessons)
            for lesson in sorted(chapter.lessons, key=lambda item: item.order_index):
                lesson.chapter = target
                lesson.order_index = next_index
                next_index += 1
                _mark(lesson)
            _mark(target)
        else:
            _delete_lessons(db, [lesson.id for lesson in chapter.lessons])
        db.query(Chapter).filter(Chapter.id == chapter.id).delete(synchronize_session=False)
        db.flush()
        _normalize_chapters(db, course_id)
    elif action == "accept_stale":
        from app.services.outline_staleness_service import accept_item
        if body.lesson_id:
            accept_item(_lesson(db, course_id, body.lesson_id))
        elif body.chapter_id:
            chapter = _chapter(db, course_id, body.chapter_id)
            accept_item(chapter)
            for lesson in chapter.lessons:
                accept_item(lesson)
        else:
            raise ValidationError_("chapter_id or lesson_id is required.")
        db.flush()
        if not db.query(Lesson).join(Chapter).filter(
            Chapter.course_id == course_id, Lesson.is_stale == True
        ).first():
            course = _chapters(db, course_id)[0].course if _chapters(db, course_id) else None
            if course:
                course.outline_stale = False
                course.outline_stale_reason = None
                course.outline_stale_at = None
    db.commit()
