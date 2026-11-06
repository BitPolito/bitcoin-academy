"""Course service - business logic for course and lesson retrieval."""
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models import Course, Lesson
from app.repositories import course_repo
from app.schemas.pagination import encode_cursor


def list_courses_page(
    db: Session, cursor: Optional[Tuple[str, str]], limit: int,
) -> Tuple[List[Course], Optional[str], bool]:
    """Returns (items, next_cursor, has_more) for one page of the course list.

    *cursor* is an already-decoded (created_at, id) pair — decoding (and
    its ValueError-on-malformed-input contract) is the controller's job,
    so this function's own errors are never mistaken for a bad cursor.
    """
    rows = course_repo.get_courses_page(db, cursor, limit)

    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        # created_at is Optional in the type only because it's a nullable
        # column at the DB level for migration-compatibility reasons; every
        # row reaching this point was either created with an explicit
        # timestamp (course_repo.create_course) or backfilled by migration
        # 0009 — it is never actually None in practice. Checked explicitly
        # rather than via `assert`, which disappears under `python -O` and
        # would otherwise let a None silently become the literal string
        # "None" in the cursor, producing a wrong (not failing) next page.
        if last.created_at is None:
            raise RuntimeError(f"Course {last.id} has no created_at — backfill migration 0009 gap")
        next_cursor = encode_cursor(last.created_at, last.id)
    return items, next_cursor, has_more


def get_course(db: Session, course_id: str) -> Optional[Course]:
    return course_repo.get_course_by_id(db, course_id)


def get_course_lessons(db: Session, course_id: str) -> List[Lesson]:
    return course_repo.get_lessons_by_course_id(db, course_id)


def get_lesson(db: Session, lesson_id: str) -> Optional[Lesson]:
    return course_repo.get_lesson_by_id(db, lesson_id)


def create_course(db: Session, title: str, description: Optional[str] = None) -> Course:
    return course_repo.create_course(db, title=title, description=description)


def update_course(db: Session, course_id: str, **fields: object) -> Optional[Course]:
    """Forward only the fields the caller actually provided (partial update)."""
    return course_repo.update_course(db, course_id=course_id, **fields)


def delete_course(db: Session, course_id: str) -> Optional[Dict[str, int]]:
    """Delete a course and every entity it owns.

    Order: documents first (each carries its own file/QVAC/chunk_parent
    cleanup via document_service), then the DB-level cascade (quizzes,
    lessons, chapters, generation runs, progress — course_repo), then
    certificate revocation and semantic-cache invalidation.

    Everything DB-side is committed exactly once, at the end. Document
    deletions and the cascade no longer commit individually — a mid-delete
    exception (e.g. deleting document 3 of 5) now rolls back everything
    instead of leaving some documents permanently gone while the course
    stays is_active=True with its chapters/lessons/quizzes still intact.
    File/QVAC side effects (physical file removal, best-effort vector
    cleanup) happen before the commit and are not themselves transactional —
    that residual gap is a known, separate limitation (see
    document_service._qvac_delete_workspace_chunks).

    Returns None if the course doesn't exist, otherwise a counts dict
    (document_count, plus every key from course_repo.delete_course_cascade,
    plus certificates_revoked and cache_keys_invalidated).
    """
    from app.db.models import Certificate
    from app.repositories import document_repo
    from app.services import cache_service, document_service

    course = course_repo.get_course_by_id(db, course_id)
    if course is None:
        return None

    documents = document_repo.list_by_course(db, course_id)
    for doc in documents:
        document_service.delete_document(db, doc.id, commit=False)

    counts = course_repo.delete_course_cascade(db, course_id)
    if counts is None:
        return None
    counts["documents"] = len(documents)

    certs = db.query(Certificate).filter(
        Certificate.course_id == course_id, Certificate.revoked == False  # noqa: E712
    ).all()
    for cert in certs:
        cert.revoked = True
    counts["certificates_revoked"] = len(certs)

    db.commit()

    counts["cache_keys_invalidated"] = cache_service.invalidate_course(course_id)

    return counts
