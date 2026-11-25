"""Topic taxonomy service — curation actions and outline-driven population
(#139, foundational data layer).

Isolation boundary (binding — see docs/design/topic-taxonomy-isolation.md):
this module is a navigation/explanation layer. It must never be imported by
app/rag/* or by the retrieval/evidence-pack path in study_service, and it
must never be used to widen a retrieval query. It only reads already-persisted
outline output (Chapter/Lesson rows) to populate occurrences; it does not run
its own extraction pass and does not call the LLM.

Alias resolution is manual curation only in this slice: aliases are added
one at a time through add_alias, and occurrence matching is exact,
case-insensitive, word-boundary matching against the canonical name and its
curated aliases. No embedding similarity, no LLM adjudication — see the
design doc for why precision is preferred over recall here.
"""
import re
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import (
    Chapter,
    Lesson,
    Topic,
    TopicAlias,
    TopicOccurrence,
    TopicOccurrenceRole,
    TopicRelation,
    TopicRelationSource,
)
from app.repositories import topic_repo


# ---------------------------------------------------------------------------
# Manual curation
# ---------------------------------------------------------------------------

def create_topic(
    db: Session,
    canonical_name: str,
    description: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Topic:
    canonical_name = canonical_name.strip()
    if not canonical_name:
        raise ValueError("canonical_name must not be empty")

    existing = topic_repo.get_topic_by_canonical_name(db, canonical_name)
    if existing is not None:
        return existing
    return topic_repo.create_topic(db, canonical_name, description, created_by)


def add_alias(
    db: Session,
    topic_id: str,
    alias: str,
    created_by: Optional[str] = None,
) -> TopicAlias:
    """Explicit curation action: attach an alternate name to a canonical topic.

    This is the only way an alias enters the system in this slice — see the
    module docstring. Rejects aliases already claimed by a *different* topic
    so two canonical topics can never silently share a name.
    """
    alias = alias.strip()
    if not alias:
        raise ValueError("alias must not be empty")

    topic = topic_repo.get_topic(db, topic_id)
    if topic is None:
        raise ValueError(f"Topic {topic_id} does not exist")

    existing = topic_repo.get_alias(db, alias)
    if existing is not None:
        if existing.topic_id != topic_id:
            raise ValueError(
                f"Alias {alias!r} already resolves to a different topic "
                f"({existing.topic_id}). Merge the topics explicitly instead "
                f"of attaching the same alias twice."
            )
        return existing

    return topic_repo.add_alias(db, topic_id, alias, created_by)


def create_relation(
    db: Session,
    topic_id: str,
    related_topic_id: str,
    relation_type: str,
    course_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> TopicRelation:
    """Explicit curation action: a human-authored prerequisite/related-to edge."""
    if topic_id == related_topic_id:
        raise ValueError("A topic cannot be related to itself")
    return topic_repo.add_relation(
        db,
        topic_id=topic_id,
        related_topic_id=related_topic_id,
        relation_type=relation_type,
        source=TopicRelationSource.MANUAL,
        course_id=course_id,
        created_by=created_by,
    )


# ---------------------------------------------------------------------------
# Population from the existing outline pipeline output
# ---------------------------------------------------------------------------

def _match_terms_for_topic(topic: Topic, aliases: List[str]) -> List[str]:
    """Canonical name plus all curated aliases, longest first so a multi-word
    alias is preferred over a shorter one that happens to be a substring."""
    terms = [topic.canonical_name] + aliases
    return sorted(set(terms), key=len, reverse=True)


def _find_match(text: str, terms: List[str]) -> Optional[str]:
    """Exact, case-insensitive, word-boundary match, tolerant only of a
    trailing English plural "s" (so "UTXOs" resolves to "UTXO"). This is a
    deterministic morphological rule, not fuzzy matching or similarity
    scoring — "UTXOset" or "unspent output theory" must still not match.
    Per the issue's stated precision-over-recall preference, nothing beyond
    this is tolerated."""
    for term in terms:
        pattern = r"(?<![\w])" + re.escape(term) + r"s?(?![\w])"
        if re.search(pattern, text, re.IGNORECASE):
            return term
    return None


def populate_occurrences_for_course(db: Session, course_id: str) -> int:
    """Scan the course's persisted outline output (Chapter → Lesson, already
    written by outline_service._persist_outline) and record a TopicOccurrence
    wherever a lesson's title or description matches a canonical topic name
    or one of its curated aliases.

    This is the "populate from the existing outline pipeline rather than a
    separate extraction pass" requirement: it reads Lesson rows the outline
    service already wrote, and performs no LLM or embedding calls.

    Role assignment is a simple heuristic, correctable by hand afterwards:
    the first lesson (by chapter/lesson order) in the course that matches a
    topic is "introduced"; subsequent matches of the same topic in the same
    course are "developed".

    Re-populating a course clears its previous occurrences first, so a
    regenerated outline does not leave stale rows behind.
    """
    topics = topic_repo.list_topics(db)
    if not topics:
        return 0

    topic_terms: Dict[str, List[str]] = {}
    for topic in topics:
        aliases = [a.alias for a in topic_repo.list_aliases_for_topic(db, topic.id)]
        topic_terms[topic.id] = _match_terms_for_topic(topic, aliases)

    lessons = (
        db.query(Lesson)
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(Chapter.course_id == course_id)
        .order_by(Chapter.order_index, Lesson.order_index)
        .all()
    )

    topic_repo.delete_occurrences_for_course(db, course_id)

    seen_in_course: set = set()
    created = 0
    for lesson in lessons:
        text = f"{lesson.title} {lesson.description or ''}"
        for topic in topics:
            match = _find_match(text, topic_terms[topic.id])
            if match is None:
                continue

            role = (
                TopicOccurrenceRole.INTRODUCED
                if topic.id not in seen_in_course
                else TopicOccurrenceRole.DEVELOPED
            )
            seen_in_course.add(topic.id)

            topic_repo.add_occurrence(
                db,
                topic_id=topic.id,
                course_id=course_id,
                lesson_id=lesson.id,
                matched_term=match,
                role=role,
            )
            created += 1

    return created


def seed_prerequisite_relations_for_course(db: Session, course_id: str) -> int:
    """Seed tentative prerequisite edges from the outline's pedagogical
    ordering: if topic A is first introduced strictly before topic B within
    this course's lesson ordering, propose "A is a prerequisite of B".

    Seeded edges are marked source=outline_seed (never "manual") so a curator
    can tell at a glance which edges were proposed by this heuristic and
    which were authored by hand, and remove a wrong one without second-
    guessing a human decision. An edge already present (either direction, in
    either source) is left alone — this never overwrites curation.

    Only *adjacent* pairs in the introduction order are seeded (topic N is a
    tentative prerequisite of topic N+1), not every earlier-later pair. The
    outline's ordering only licenses a claim about immediate neighbours;
    inferring a prerequisite edge between topics introduced many lessons
    apart would be the kind of recall-over-precision guess the issue warns
    against.
    """
    # Order of introduction within the course, by the lesson's own position
    # in the outline (chapter order, then lesson order) rather than row
    # insertion order — deterministic regardless of timestamp resolution.
    introduced_rows = (
        db.query(TopicOccurrence)
        .join(Lesson, TopicOccurrence.lesson_id == Lesson.id)
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(
            TopicOccurrence.course_id == course_id,
            TopicOccurrence.role == TopicOccurrenceRole.INTRODUCED,
        )
        .order_by(Chapter.order_index, Lesson.order_index)
        .all()
    )

    ordered_topic_ids: List[str] = []
    seen: set = set()
    for occ in introduced_rows:
        if occ.topic_id not in seen:
            seen.add(occ.topic_id)
            ordered_topic_ids.append(occ.topic_id)

    created = 0
    for earlier, later in zip(ordered_topic_ids, ordered_topic_ids[1:]):
        if topic_repo.relation_exists_either_direction(
            db, earlier, later, "prerequisite"
        ):
            continue
        topic_repo.add_relation(
            db,
            topic_id=earlier,
            related_topic_id=later,
            relation_type="prerequisite",
            source=TopicRelationSource.OUTLINE_SEED,
            course_id=course_id,
        )
        created += 1

    return created
