"""Tests for the cross-course topic taxonomy foundation (#139).

Covers: manual alias curation (no fuzzy/embedding matching), occurrence
population from already-persisted outline output, and prerequisite-relation
seeding from outline ordering. See docs/design/topic-taxonomy-isolation.md
for the isolation boundary these tests assume but do not themselves prove —
that proof lives in tests/integration/test_course_isolation.py.
"""
import uuid

import pytest
from sqlalchemy.orm import Session

from app.db.models import Chapter, Course, Lesson, Section, TopicOccurrenceRole
from app.repositories import topic_repo
from app.services import topic_service


def _make_course(db: Session, title: str = "Test Course") -> Course:
    section = Section(id=str(uuid.uuid4()), title="Section")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), section_id=section.id, title=title)
    db.add(course)
    db.commit()
    return course


def _make_chapter(db: Session, course: Course, order_index: int = 0) -> Chapter:
    chapter = Chapter(
        id=str(uuid.uuid4()),
        course_id=course.id,
        title=f"Chapter {order_index}",
        order_index=order_index,
    )
    db.add(chapter)
    db.commit()
    return chapter


def _make_lesson(
    db: Session, chapter: Chapter, title: str, description: str = "", order_index: int = 0
) -> Lesson:
    lesson = Lesson(
        id=str(uuid.uuid4()),
        chapter_id=chapter.id,
        title=title,
        description=description,
        content="",
        order_index=order_index,
    )
    db.add(lesson)
    db.commit()
    return lesson


# ---------------------------------------------------------------------------
# Manual curation
# ---------------------------------------------------------------------------

def test_create_topic_is_idempotent_on_canonical_name(db):
    t1 = topic_service.create_topic(db, "UTXO")
    t2 = topic_service.create_topic(db, "UTXO")
    assert t1.id == t2.id


def test_add_alias_attaches_to_topic(db):
    topic = topic_service.create_topic(db, "UTXO")
    alias = topic_service.add_alias(db, topic.id, "unspent transaction output")

    aliases = topic_repo.list_aliases_for_topic(db, topic.id)
    assert alias.alias == "unspent transaction output"
    assert [a.alias for a in aliases] == ["unspent transaction output"]


def test_add_alias_rejects_alias_already_claimed_by_another_topic(db):
    """Getting this wrong conflates two distinct concepts — the issue's
    explicitly named risk — so a second topic must not silently steal an
    alias already resolving elsewhere."""
    topic_a = topic_service.create_topic(db, "UTXO")
    topic_b = topic_service.create_topic(db, "UTXO set")
    topic_service.add_alias(db, topic_a.id, "unspent output")

    with pytest.raises(ValueError):
        topic_service.add_alias(db, topic_b.id, "unspent output")


def test_add_alias_is_idempotent_for_the_same_topic(db):
    topic = topic_service.create_topic(db, "UTXO")
    a1 = topic_service.add_alias(db, topic.id, "unspent output")
    a2 = topic_service.add_alias(db, topic.id, "unspent output")
    assert a1.id == a2.id


def test_create_relation_rejects_self_relation(db):
    topic = topic_service.create_topic(db, "UTXO")
    with pytest.raises(ValueError):
        topic_service.create_relation(db, topic.id, topic.id, "prerequisite")


def test_create_relation_is_marked_manual(db):
    a = topic_service.create_topic(db, "UTXO")
    b = topic_service.create_topic(db, "Transaction malleability")
    relation = topic_service.create_relation(db, a.id, b.id, "prerequisite")
    assert relation.source == "manual"


# ---------------------------------------------------------------------------
# Occurrence population from outline pipeline output
# ---------------------------------------------------------------------------

def test_populate_occurrences_matches_canonical_name_in_lesson_title(db):
    course = _make_course(db)
    chapter = _make_chapter(db, course)
    _make_lesson(db, chapter, "Understanding UTXOs", order_index=0)

    topic = topic_service.create_topic(db, "UTXO")
    created = topic_service.populate_occurrences_for_course(db, course.id)

    assert created == 1
    occurrences = topic_repo.list_occurrences_for_topic(db, topic.id, course.id)
    assert len(occurrences) == 1
    assert occurrences[0].matched_term.lower() == "utxo"


def test_populate_occurrences_matches_curated_alias(db):
    course = _make_course(db)
    chapter = _make_chapter(db, course)
    _make_lesson(
        db, chapter, "The transaction model",
        description="Covers the unspent transaction output model in depth.",
        order_index=0,
    )

    topic = topic_service.create_topic(db, "UTXO")
    topic_service.add_alias(db, topic.id, "unspent transaction output")
    created = topic_service.populate_occurrences_for_course(db, course.id)

    assert created == 1
    occ = topic_repo.list_occurrences_for_topic(db, topic.id, course.id)[0]
    assert occ.matched_term == "unspent transaction output"


def test_populate_occurrences_requires_word_boundary(db):
    """'UTXO' must not match inside 'UTXOset' — precision over recall."""
    course = _make_course(db)
    chapter = _make_chapter(db, course)
    _make_lesson(db, chapter, "The UTXOset data structure", order_index=0)

    topic_service.create_topic(db, "UTXO")
    created = topic_service.populate_occurrences_for_course(db, course.id)

    assert created == 0


def test_populate_occurrences_role_heuristic_first_introduced_then_developed(db):
    course = _make_course(db)
    chapter = _make_chapter(db, course)
    _make_lesson(db, chapter, "Introduction to UTXOs", order_index=0)
    _make_lesson(db, chapter, "Advanced UTXO handling", order_index=1)

    topic = topic_service.create_topic(db, "UTXO")
    topic_service.populate_occurrences_for_course(db, course.id)

    occurrences = sorted(
        topic_repo.list_occurrences_for_topic(db, topic.id, course.id),
        key=lambda o: o.created_at,
    )
    roles = [o.role for o in occurrences]
    assert roles[0] == TopicOccurrenceRole.INTRODUCED
    assert TopicOccurrenceRole.DEVELOPED in roles


def test_populate_occurrences_clears_stale_rows_on_rerun(db):
    """Regenerating an outline must not leave occurrences from the previous
    draft pointing at lessons that no longer exist."""
    course = _make_course(db)
    chapter = _make_chapter(db, course)
    _make_lesson(db, chapter, "Introduction to UTXOs", order_index=0)
    topic = topic_service.create_topic(db, "UTXO")
    topic_service.populate_occurrences_for_course(db, course.id)
    assert len(topic_repo.list_occurrences_for_topic(db, topic.id, course.id)) == 1

    # Second lesson added, outline "regenerated"
    _make_lesson(db, chapter, "More on UTXOs", order_index=1)
    topic_service.populate_occurrences_for_course(db, course.id)

    occurrences = topic_repo.list_occurrences_for_topic(db, topic.id, course.id)
    assert len(occurrences) == 2


def test_populate_occurrences_is_scoped_to_the_requested_course(db):
    """A topic shared across two courses must only get occurrences for the
    course being populated — populating course A must not touch course B."""
    course_a = _make_course(db, "Course A")
    course_b = _make_course(db, "Course B")
    chapter_a = _make_chapter(db, course_a)
    chapter_b = _make_chapter(db, course_b)
    _make_lesson(db, chapter_a, "UTXOs in course A", order_index=0)
    _make_lesson(db, chapter_b, "UTXOs in course B", order_index=0)

    topic = topic_service.create_topic(db, "UTXO")
    topic_service.populate_occurrences_for_course(db, course_a.id)

    occ_a = topic_repo.list_occurrences_for_topic(db, topic.id, course_a.id)
    occ_b = topic_repo.list_occurrences_for_topic(db, topic.id, course_b.id)
    assert len(occ_a) == 1
    assert len(occ_b) == 0


# ---------------------------------------------------------------------------
# Prerequisite relation seeding
# ---------------------------------------------------------------------------

def test_seed_prerequisite_relations_links_adjacent_introduced_topics(db):
    course = _make_course(db)
    chapter = _make_chapter(db, course)
    _make_lesson(db, chapter, "Introduction to UTXOs", order_index=0)
    _make_lesson(db, chapter, "Transaction malleability explained", order_index=1)

    utxo = topic_service.create_topic(db, "UTXO")
    malleability = topic_service.create_topic(db, "Transaction malleability")
    topic_service.populate_occurrences_for_course(db, course.id)

    created = topic_service.seed_prerequisite_relations_for_course(db, course.id)

    assert created == 1
    relations = topic_repo.list_relations_for_topic(db, utxo.id)
    assert len(relations) == 1
    assert relations[0].related_topic_id == malleability.id
    assert relations[0].source == "outline_seed"


def test_seed_prerequisite_relations_does_not_override_manual_edges(db):
    course = _make_course(db)
    chapter = _make_chapter(db, course)
    _make_lesson(db, chapter, "Introduction to UTXOs", order_index=0)
    _make_lesson(db, chapter, "Transaction malleability explained", order_index=1)

    utxo = topic_service.create_topic(db, "UTXO")
    malleability = topic_service.create_topic(db, "Transaction malleability")
    # Human already curated the opposite-direction edge.
    topic_service.create_relation(db, malleability.id, utxo.id, "prerequisite")

    topic_service.populate_occurrences_for_course(db, course.id)
    created = topic_service.seed_prerequisite_relations_for_course(db, course.id)

    assert created == 0
    relations = topic_repo.list_relations_for_topic(db, malleability.id)
    assert len(relations) == 1
    assert relations[0].source == "manual"


def test_seed_prerequisite_relations_is_rerun_safe(db):
    course = _make_course(db)
    chapter = _make_chapter(db, course)
    _make_lesson(db, chapter, "Introduction to UTXOs", order_index=0)
    _make_lesson(db, chapter, "Transaction malleability explained", order_index=1)
    topic_service.create_topic(db, "UTXO")
    topic_service.create_topic(db, "Transaction malleability")
    topic_service.populate_occurrences_for_course(db, course.id)

    first = topic_service.seed_prerequisite_relations_for_course(db, course.id)
    second = topic_service.seed_prerequisite_relations_for_course(db, course.id)

    assert first == 1
    assert second == 0
