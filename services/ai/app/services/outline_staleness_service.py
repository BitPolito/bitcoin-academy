"""Precise outline invalidation driven by persisted source snapshots."""
import hashlib
import json
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Chapter, ChunkParent, Course, CourseDocument, Lesson


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_snapshot(db: Session, chunk_ids: list[str]) -> list[dict[str, str]]:
    rows = {row.id: row for row in db.query(ChunkParent).filter(ChunkParent.id.in_(chunk_ids)).all()}
    return [
        {"chunk_id": chunk_id, "document_id": rows[chunk_id].doc_id,
         "content_hash": hashlib.sha256(rows[chunk_id].text.encode()).hexdigest()}
        for chunk_id in chunk_ids if chunk_id in rows
    ]


def mark_new_document(db: Session, course_id: str, filename: str) -> None:
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None or not db.query(Chapter).filter(Chapter.course_id == course_id).first():
        return
    course.outline_stale = True
    course.outline_stale_reason = f'New source "{filename}" is ready for outline review.'
    course.outline_stale_at = _now()


def mark_document_changed(db: Session, document_id: str, reason: str) -> int:
    document = db.query(CourseDocument).filter(CourseDocument.id == document_id).first()
    if document is not None:
        course = db.query(Course).filter(Course.id == document.course_id).first()
        if course is not None:
            course.outline_stale = True
            course.outline_stale_reason = reason
            course.outline_stale_at = _now()
    direct_ids = {row.id for row in db.query(ChunkParent.id).filter(ChunkParent.doc_id == document_id).all()}
    lessons = db.query(Lesson).join(Chapter).all()
    affected: list[Lesson] = []
    for lesson in lessons:
        snapshot = json.loads(lesson.source_snapshot_json or "[]")
        refs = set(json.loads(lesson.source_refs_json or "[]"))
        if any(item.get("document_id") == document_id for item in snapshot) or refs.intersection(direct_ids):
            affected.append(lesson)
    stamp = _now()
    chapter_ids = set()
    for lesson in affected:
        lesson.is_stale = True
        lesson.stale_reason = reason
        lesson.stale_at = stamp
        chapter_ids.add(lesson.chapter_id)
    for chapter in db.query(Chapter).filter(Chapter.id.in_(chapter_ids)).all():
        chapter.is_stale = True
        chapter.stale_reason = reason
        chapter.stale_at = stamp
        chapter.course.outline_stale = True
        chapter.course.outline_stale_reason = reason
        chapter.course.outline_stale_at = stamp
    return len(affected)


def mark_overlapping_new_source(db: Session, document_id: str) -> int:
    """Flag existing lessons whose titles substantially overlap a newly ingested source."""
    document = db.query(CourseDocument).filter(CourseDocument.id == document_id).first()
    if document is None:
        return 0
    text = " ".join(
        row.text for row in db.query(ChunkParent).filter(ChunkParent.doc_id == document_id).all()
    ).lower()
    source_terms = set(re.findall(r"[a-z0-9]{4,}", text))
    affected = 0
    stamp = _now()
    lessons = db.query(Lesson).join(Chapter).filter(Chapter.course_id == document.course_id).all()
    for lesson in lessons:
        title_terms = set(re.findall(r"[a-z0-9]{4,}", f"{lesson.title} {lesson.description or ''}".lower()))
        if title_terms and len(title_terms.intersection(source_terms)) / len(title_terms) >= 0.5:
            lesson.is_stale = True
            lesson.stale_reason = f'New source "{document.filename}" overlaps this lesson.'
            lesson.stale_at = stamp
            lesson.chapter.is_stale = True
            lesson.chapter.stale_reason = lesson.stale_reason
            lesson.chapter.stale_at = stamp
            affected += 1
    return affected


def accept_item(item: Chapter | Lesson) -> None:
    item.is_stale = False
    item.stale_reason = None
    item.stale_at = None
