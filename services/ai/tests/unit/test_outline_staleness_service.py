import json
import uuid

from app.db.models import Chapter, ChunkParent, CourseDocument, Lesson
from app.services.outline_staleness_service import (
    mark_document_changed,
    mark_new_document,
    mark_overlapping_new_source,
    source_snapshot,
)
from tests.conftest import make_course_with_lessons


def test_document_change_marks_only_sourced_lessons_and_preserves_human_edits(db):
    course, lessons = make_course_with_lessons(db)
    document = CourseDocument(id=str(uuid.uuid4()), course_id=course.id, filename="source.pdf", size=10)
    parent = ChunkParent(
        id="source-chunk", doc_id=document.id, course_id=course.id, text="Stable source text",
        citation_label="p1", citation_page=1, citation_section="Intro",
    )
    db.add_all([document, parent])
    db.flush()
    lessons[0].source_refs_json = json.dumps([parent.id])
    lessons[0].source_snapshot_json = json.dumps(source_snapshot(db, [parent.id]))
    lessons[0].is_human_modified = True
    db.commit()

    assert mark_document_changed(db, document.id, "Source was deleted") == 1
    db.commit()

    assert lessons[0].is_stale is True
    assert lessons[0].stale_reason == "Source was deleted"
    assert lessons[0].is_human_modified is True
    assert lessons[0].content == "Content."
    assert lessons[1].is_stale is False
    assert lessons[0].chapter.is_stale is True
    assert course.outline_stale is True


def test_source_snapshot_detects_parser_content_changes(db):
    course, _ = make_course_with_lessons(db)
    parent = ChunkParent(
        id="same-id", doc_id="doc-1", course_id=course.id, text="Version one",
        citation_label="p1", citation_page=1, citation_section="Intro",
    )
    db.add(parent)
    db.commit()
    first = source_snapshot(db, [parent.id])
    parent.text = "Version two"
    db.commit()
    second = source_snapshot(db, [parent.id])
    assert first[0]["chunk_id"] == second[0]["chunk_id"]
    assert first[0]["content_hash"] != second[0]["content_hash"]


def test_new_document_marks_course_and_only_overlapping_lessons(db):
    course, lessons = make_course_with_lessons(db)
    lessons[0].title = "Bitcoin mining difficulty"
    lessons[1].title = "Wallet privacy"
    document = CourseDocument(id=str(uuid.uuid4()), course_id=course.id, filename="mining.pdf", size=10)
    parent = ChunkParent(
        id="mining-chunk", doc_id=document.id, course_id=course.id,
        text="Bitcoin mining difficulty adjusts over time.", citation_label="p1",
        citation_page=1, citation_section="Mining",
    )
    db.add_all([document, parent])
    db.commit()

    mark_new_document(db, course.id, document.filename)
    assert course.outline_stale is True
    assert mark_overlapping_new_source(db, document.id) == 1
    assert lessons[0].is_stale is True
    assert lessons[1].is_stale is False
