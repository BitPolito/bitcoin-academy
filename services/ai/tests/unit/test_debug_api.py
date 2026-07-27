"""Debug API — internal visibility endpoints.

The debug router is mounted only when DEBUG_MODE is enabled, so these tests
build a standalone app around the router rather than relying on import-time
configuration of the main application.

Two things are verified: the endpoints work (they were entirely untested), and
they stay unmounted by default — they carry no authentication, so shipping them
enabled would expose document contents and retrieval internals.
"""
import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.debug_api import router as debug_router
from app.db.models import Course, CourseDocument, Section
from app.db.session import get_db


@pytest.fixture
def debug_client(db: Session) -> TestClient:
    """A minimal app exposing only the debug router, wired to the test database."""
    from sqlalchemy.orm import sessionmaker

    app = FastAPI()
    app.include_router(debug_router)

    engine = db.get_bind()
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _make_document(db: Session, **overrides) -> CourseDocument:
    section = Section(id=str(uuid.uuid4()), title="S")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), section_id=section.id, title="C")
    db.add(course)

    doc = CourseDocument(
        id=str(uuid.uuid4()),
        course_id=course.id,
        filename="lecture.pdf",
        **overrides,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ---------------------------------------------------------------------------
# Document inspection
# ---------------------------------------------------------------------------

def test_chunks_endpoint_returns_stored_sample_chunks(debug_client, db):
    chunks = [{"chunk_id": "c1", "text": "Bitcoin uses proof of work."}]
    doc = _make_document(db, sample_chunks_json=json.dumps(chunks))

    response = debug_client.get(f"/api/debug/documents/{doc.id}/chunks")

    assert response.status_code == 200
    assert response.json() == chunks


def test_chunks_endpoint_returns_empty_list_when_none_stored(debug_client, db):
    doc = _make_document(db, sample_chunks_json=None)
    response = debug_client.get(f"/api/debug/documents/{doc.id}/chunks")
    assert response.status_code == 200
    assert response.json() == []


def test_chunks_endpoint_tolerates_corrupt_json(debug_client, db):
    """A debug endpoint must not 500 on malformed stored data — that would hide
    the very problem it exists to reveal."""
    doc = _make_document(db, sample_chunks_json="{not valid json")
    response = debug_client.get(f"/api/debug/documents/{doc.id}/chunks")
    assert response.status_code == 200
    assert response.json() == []


def test_chunks_endpoint_404s_for_an_unknown_document(debug_client):
    response = debug_client.get(f"/api/debug/documents/{uuid.uuid4()}/chunks")
    assert response.status_code == 404


def test_parsed_endpoint_returns_parser_metadata(debug_client, db):
    doc = _make_document(
        db,
        parser_used="pymupdf4llm-page-chunks",
        page_count=12,
        extracted_text_preview="Bitcoin: A Peer-to-Peer Electronic Cash System",
        sections_json=json.dumps([{"title": "Intro"}, {"title": "Transactions"}]),
    )

    response = debug_client.get(f"/api/debug/documents/{doc.id}/parsed")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == doc.id
    assert body["filename"] == "lecture.pdf"
    assert body["parser_used"] == "pymupdf4llm-page-chunks"
    assert body["page_count"] == 12
    assert "Peer-to-Peer" in body["extracted_text_preview"]
    assert len(body["sections"]) == 2


def test_parsed_endpoint_truncates_sections_to_three(debug_client, db):
    """The preview is a sample, not a dump."""
    sections = [{"title": f"Section {i}"} for i in range(10)]
    doc = _make_document(db, sections_json=json.dumps(sections))

    response = debug_client.get(f"/api/debug/documents/{doc.id}/parsed")

    assert response.status_code == 200
    assert len(response.json()["sections"]) == 3


def test_parsed_endpoint_tolerates_corrupt_sections_json(debug_client, db):
    doc = _make_document(db, sections_json="[[[")
    response = debug_client.get(f"/api/debug/documents/{doc.id}/parsed")
    assert response.status_code == 200
    assert response.json()["sections"] == []


def test_parsed_endpoint_404s_for_an_unknown_document(debug_client):
    response = debug_client.get(f"/api/debug/documents/{uuid.uuid4()}/parsed")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Retrieval inspection — no index present, so these exercise the empty path.
# ---------------------------------------------------------------------------

def test_retrieval_endpoint_returns_an_empty_result_without_an_index(debug_client):
    course_id = str(uuid.uuid4())
    response = debug_client.post(
        f"/api/debug/courses/{course_id}/retrieval", params={"query": "utxo"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["course_id"] == course_id
    assert body["query"] == "utxo"
    assert body["total"] == 0
    assert body["chunks"] == []


def test_retrieval_endpoint_rejects_an_empty_query(debug_client):
    response = debug_client.post(
        f"/api/debug/courses/{uuid.uuid4()}/retrieval", params={"query": ""}
    )
    assert response.status_code == 422


def test_retrieval_endpoint_caps_top_k(debug_client):
    """top_k is bounded so a debug call cannot be used to pull the whole index."""
    response = debug_client.post(
        f"/api/debug/courses/{uuid.uuid4()}/retrieval",
        params={"query": "utxo", "top_k": 500},
    )
    assert response.status_code == 422


def test_evidence_endpoint_returns_a_wellformed_empty_pack(debug_client):
    course_id = str(uuid.uuid4())
    response = debug_client.get(
        f"/api/debug/courses/{course_id}/evidence", params={"query": "merkle tree"}
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["query"] == "merkle tree"
    assert pack["action"] == "explain"
    assert pack["chunks"] == []
    assert pack["total_candidates"] == 0


def test_retrieval_trace_returns_every_pipeline_stage(debug_client):
    """The trace is the tool for debugging retrieval quality; each stage must be
    present even when empty, so the shape is stable for the UI."""
    response = debug_client.post(
        "/api/debug/retrieval/test",
        json={"query": "proof of work", "course_id": str(uuid.uuid4()), "action": "explain"},
    )

    assert response.status_code == 200
    trace = response.json()
    for stage in ("raw_chunks", "reranked_chunks", "discarded_chunks"):
        assert stage in trace, f"Trace is missing the {stage} stage"
        assert isinstance(trace[stage], list)
    assert "evidence_pack" in trace
    assert trace["query"] == "proof of work"


def test_pipeline_health_reports_index_and_upload_state(debug_client):
    response = debug_client.get("/api/debug/pipeline/health")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)


# ---------------------------------------------------------------------------
# The router must stay unmounted by default.
# ---------------------------------------------------------------------------

def test_debug_router_is_not_mounted_on_the_main_app_by_default(client):
    """These endpoints have no authentication dependency. If DEBUG_MODE were on
    by default, anyone could read parsed document contents."""
    response = client.get(f"/api/debug/documents/{uuid.uuid4()}/parsed")
    assert response.status_code == 404, (
        "The debug router is mounted on the main application. It exposes "
        "unauthenticated document and retrieval inspection and must be gated "
        "behind DEBUG_MODE."
    )


def test_debug_endpoints_declare_no_authentication_dependency():
    """Documents the current security model explicitly: the debug router relies
    entirely on not being mounted. If authentication is ever added, this test
    should be updated to assert it — a deliberate, reviewable change."""
    for route in debug_router.routes:
        dependencies = getattr(route, "dependencies", [])
        assert not dependencies, (
            f"{route.path} now declares dependencies. If authentication was "
            f"added, update this test and consider mounting the router "
            f"unconditionally."
        )
