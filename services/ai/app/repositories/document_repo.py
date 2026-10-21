"""Document repository - data access for course documents."""
import json
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db.models import CourseDocument


def list_by_course(db: Session, course_id: str) -> List[CourseDocument]:
    return (
        db.query(CourseDocument)
        .filter(CourseDocument.course_id == course_id)
        .order_by(CourseDocument.created_at.desc())
        .all()
    )


def list_page_by_course(
    db: Session,
    course_id: str,
    *,
    after: tuple[str, str] | None,
    limit: int,
) -> tuple[List[CourseDocument], bool]:
    query = db.query(CourseDocument).filter(CourseDocument.course_id == course_id)
    if after is not None:
        created_at, document_id = after
        query = query.filter(
            or_(
                CourseDocument.created_at < created_at,
                and_(CourseDocument.created_at == created_at, CourseDocument.id < document_id),
            )
        )
    rows = (
        query.order_by(CourseDocument.created_at.desc(), CourseDocument.id.desc())
        .limit(limit + 1)
        .all()
    )
    return rows[:limit], len(rows) > limit


def get_by_id(db: Session, document_id: str) -> Optional[CourseDocument]:
    return db.query(CourseDocument).filter(CourseDocument.id == document_id).first()


def create(db: Session, doc: CourseDocument) -> CourseDocument:
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def delete(db: Session, doc: CourseDocument, commit: bool = True) -> None:
    db.delete(doc)
    if commit:
        db.commit()
