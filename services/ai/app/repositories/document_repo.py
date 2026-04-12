"""Document repository - data access for course documents."""
import json
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import CourseDocument


def list_by_course(db: Session, course_id: str) -> List[CourseDocument]:
    return (
        db.query(CourseDocument)
        .filter(CourseDocument.course_id == course_id)
        .order_by(CourseDocument.created_at.desc())
        .all()
    )


def get_by_id(db: Session, document_id: str) -> Optional[CourseDocument]:
    return db.query(CourseDocument).filter(CourseDocument.id == document_id).first()


def create(db: Session, doc: CourseDocument) -> CourseDocument:
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def delete(db: Session, doc: CourseDocument) -> None:
    db.delete(doc)
    db.commit()
