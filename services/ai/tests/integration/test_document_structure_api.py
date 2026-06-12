"""Integration tests for GET /api/documents/{id}/structure.

Three sources: "ingest" (tree persisted by the pipeline), "rebuilt" (flat
tree from chunk_parent for legacy documents), "unavailable" (not READY or
nothing indexed). Uses the in-memory SQLite fixtures from conftest.
"""
import json
import uuid

import pytest

from app.db.models import ChunkParent, CourseDocument, DocumentStatus
from tests.conftest import make_course_with_lessons

_TREE = [
    {
        "title": "Chapter One",
        "level": 1,
        "page_start": 1,
        "page_end": 9,
        "parent_chunk_ids": ["d_p0000"],
        "children": [
            {
                "title": "Section 1.1",
                "level": 2,
                "page_start": 2,
                "page_end": 9,
                "parent_chunk_ids": ["d_p0001"],
                "children": [],
            }
        ],
    }
]


def _make_document(db, course_id: str, **overrides) -> CourseDocument:
    fields = {
        "id": str(uuid.uuid4()),
        "course_id": course_id,
        "filename": "test.pdf",
        "size": 1234,
        "status": DocumentStatus.READY,
        **overrides,
    }
    doc = CourseDocument(**fields)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@pytest.mark.integration
def test_structure_returns_ingest_tree(client, db):
    course, _ = make_course_with_lessons(db)
    doc = _make_document(db, course.id, section_tree_json=json.dumps(_TREE))

    resp = client.get(f"/api/documents/{doc.id}/structure")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "ingest"
    assert body["document_id"] == doc.id
    assert body["tree"][0]["title"] == "Chapter One"
    assert body["tree"][0]["children"][0]["title"] == "Section 1.1"
    assert body["tree"][0]["children"][0]["parent_chunk_ids"] == ["d_p0001"]


@pytest.mark.integration
def test_structure_rebuilds_flat_tree_from_chunk_parents(client, db):
    course, _ = make_course_with_lessons(db)
    doc = _make_document(db, course.id)  # READY, no section_tree_json
    for idx, (section, page) in enumerate([("Intro", 1), ("Intro", 2), ("Mining", 5)]):
        db.add(ChunkParent(
            id=f"{doc.id}_p{idx:04d}",
            doc_id=doc.id,
            course_id=course.id,
            text="parent text",
            citation_section=section,
            citation_page=page,
        ))
    db.commit()

    resp = client.get(f"/api/documents/{doc.id}/structure")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "rebuilt"
    assert [n["title"] for n in body["tree"]] == ["Intro", "Mining"]
    assert body["tree"][0]["page_start"] == 1
    assert body["tree"][0]["page_end"] == 2
    assert len(body["tree"][0]["parent_chunk_ids"]) == 2
    # Rebuilt trees are not persisted — reindex produces the real one.
    db.refresh(doc)
    assert doc.section_tree_json is None


@pytest.mark.integration
def test_structure_unavailable_when_not_ready(client, db):
    course, _ = make_course_with_lessons(db)
    doc = _make_document(db, course.id, status=DocumentStatus.PROCESSING)

    resp = client.get(f"/api/documents/{doc.id}/structure")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "unavailable"
    assert body["tree"] is None


@pytest.mark.integration
def test_structure_unavailable_when_no_parents(client, db):
    course, _ = make_course_with_lessons(db)
    doc = _make_document(db, course.id)  # READY but nothing in chunk_parent

    resp = client.get(f"/api/documents/{doc.id}/structure")
    assert resp.status_code == 200
    assert resp.json()["source"] == "unavailable"


@pytest.mark.integration
def test_structure_unknown_document_404(client, db):
    resp = client.get(f"/api/documents/{uuid.uuid4()}/structure")
    assert resp.status_code == 404
