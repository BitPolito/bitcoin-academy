"""Topic taxonomy repository — data access for canonical topics, aliases,
occurrences and relations (#139, foundational data layer).

This is a read-side index. Nothing here is imported by app/rag/* or by
study_service's retrieval/evidence-pack path — see
docs/design/topic-taxonomy-isolation.md for why that boundary is load-bearing.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import (
    Topic,
    TopicAlias,
    TopicOccurrence,
    TopicRelation,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

def get_topic(db: Session, topic_id: str) -> Optional[Topic]:
    return db.query(Topic).filter(Topic.id == topic_id).first()


def get_topic_by_canonical_name(db: Session, canonical_name: str) -> Optional[Topic]:
    return (
        db.query(Topic)
        .filter(Topic.canonical_name == canonical_name)
        .first()
    )


def list_topics(db: Session) -> List[Topic]:
    return db.query(Topic).order_by(Topic.canonical_name).all()


def create_topic(
    db: Session,
    canonical_name: str,
    description: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Topic:
    topic = Topic(
        id=str(uuid.uuid4()),
        canonical_name=canonical_name,
        description=description,
        created_at=_now_iso(),
        created_by=created_by,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

def get_alias(db: Session, alias: str) -> Optional[TopicAlias]:
    """Lookup is case-insensitive; alias text itself is stored as given."""
    return (
        db.query(TopicAlias)
        .filter(TopicAlias.alias.ilike(alias))
        .first()
    )


def list_aliases_for_topic(db: Session, topic_id: str) -> List[TopicAlias]:
    return db.query(TopicAlias).filter(TopicAlias.topic_id == topic_id).all()


def add_alias(
    db: Session,
    topic_id: str,
    alias: str,
    created_by: Optional[str] = None,
) -> TopicAlias:
    row = TopicAlias(
        id=str(uuid.uuid4()),
        topic_id=topic_id,
        alias=alias,
        created_at=_now_iso(),
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_alias(db: Session, alias_id: str) -> bool:
    row = db.query(TopicAlias).filter(TopicAlias.id == alias_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Occurrences
# ---------------------------------------------------------------------------

def list_occurrences_for_topic(
    db: Session, topic_id: str, course_id: Optional[str] = None
) -> List[TopicOccurrence]:
    query = db.query(TopicOccurrence).filter(TopicOccurrence.topic_id == topic_id)
    if course_id is not None:
        query = query.filter(TopicOccurrence.course_id == course_id)
    return query.all()


def list_occurrences_for_course(db: Session, course_id: str) -> List[TopicOccurrence]:
    return (
        db.query(TopicOccurrence)
        .filter(TopicOccurrence.course_id == course_id)
        .all()
    )


def get_occurrence(
    db: Session, topic_id: str, lesson_id: str, chunk_id: Optional[str]
) -> Optional[TopicOccurrence]:
    return (
        db.query(TopicOccurrence)
        .filter(
            TopicOccurrence.topic_id == topic_id,
            TopicOccurrence.lesson_id == lesson_id,
            TopicOccurrence.chunk_id == chunk_id,
        )
        .first()
    )


def add_occurrence(
    db: Session,
    topic_id: str,
    course_id: str,
    lesson_id: str,
    matched_term: str,
    role: str,
    chunk_id: Optional[str] = None,
) -> TopicOccurrence:
    existing = get_occurrence(db, topic_id, lesson_id, chunk_id)
    if existing is not None:
        return existing

    row = TopicOccurrence(
        id=str(uuid.uuid4()),
        topic_id=topic_id,
        course_id=course_id,
        lesson_id=lesson_id,
        chunk_id=chunk_id,
        role=role,
        matched_term=matched_term,
        created_at=_now_iso(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_occurrences_for_course(db: Session, course_id: str) -> int:
    """Used when re-populating occurrences for a course after an outline
    regeneration, so stale occurrences from the previous draft don't linger."""
    rows = (
        db.query(TopicOccurrence)
        .filter(TopicOccurrence.course_id == course_id)
        .all()
    )
    count = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()
    return count


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------

def get_relation(
    db: Session, topic_id: str, related_topic_id: str, relation_type: str
) -> Optional[TopicRelation]:
    return (
        db.query(TopicRelation)
        .filter(
            TopicRelation.topic_id == topic_id,
            TopicRelation.related_topic_id == related_topic_id,
            TopicRelation.relation_type == relation_type,
        )
        .first()
    )


def relation_exists_either_direction(
    db: Session, topic_a: str, topic_b: str, relation_type: str
) -> bool:
    return (
        db.query(TopicRelation)
        .filter(
            TopicRelation.relation_type == relation_type,
            (
                (TopicRelation.topic_id == topic_a)
                & (TopicRelation.related_topic_id == topic_b)
            )
            | (
                (TopicRelation.topic_id == topic_b)
                & (TopicRelation.related_topic_id == topic_a)
            ),
        )
        .first()
        is not None
    )


def list_relations_for_topic(db: Session, topic_id: str) -> List[TopicRelation]:
    return (
        db.query(TopicRelation)
        .filter(TopicRelation.topic_id == topic_id)
        .all()
    )


def add_relation(
    db: Session,
    topic_id: str,
    related_topic_id: str,
    relation_type: str,
    source: str,
    course_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> TopicRelation:
    existing = get_relation(db, topic_id, related_topic_id, relation_type)
    if existing is not None:
        return existing

    row = TopicRelation(
        id=str(uuid.uuid4()),
        topic_id=topic_id,
        related_topic_id=related_topic_id,
        relation_type=relation_type,
        source=source,
        course_id=course_id,
        created_at=_now_iso(),
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_relation(db: Session, relation_id: str) -> bool:
    row = db.query(TopicRelation).filter(TopicRelation.id == relation_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
