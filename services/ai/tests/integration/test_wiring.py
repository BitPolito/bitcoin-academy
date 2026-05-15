"""Step 8 wiring tests — verify that course_id flows correctly as the QVAC
workspace through both the upload and chat paths.

This is the contract the two paths must maintain: documents indexed under a
course_id workspace during ingest are retrievable when a student queries that
same course's chat endpoint. Breaking this invariant silently would mean the
RAG pipeline returns results from the wrong course, or nothing at all.

Test need to cover LLM query path and document upload path, and verify that both use the same course_id workspace when calling QVAC. Also verify that different courses use different workspaces, and that the chat endpoint correctly forwards the full QVAC response to the client.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


def _retrieve_resp(chunks=None) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"chunks": chunks or []}
    resp.raise_for_status.return_value = None
    return resp


def _generate_resp(answer="Test answer.") -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"answer": answer}
    resp.raise_for_status.return_value = None
    return resp


def _chunk_dict(chunk_id="c1", content="Bitcoin content.", score=0.9) -> dict:
    return {
        "chunk_id": chunk_id, "content": content, "score": score,
        "label": "doc.pdf", "page": 1, "slide": 0, "section": "Intro", "doc_id": "doc1",
    }


def _mock_chat_client(chunks=None, answer="Test answer.") -> MagicMock:
    mock = MagicMock()
    mock.post = AsyncMock(side_effect=[_retrieve_resp(chunks), _generate_resp(answer)])
    return mock


# ---------------------------------------------------------------------------
# Core workspace contract
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_upload_and_chat_use_same_qvac_workspace(client, db):
    """The QVAC workspace for ingest and query must both equal course_id.

    If either side uses a different identifier, documents indexed during upload
    will not be found at query time — the workspace is the only key linking the
    two operations.
    """
    course, _ = make_course_with_lessons(db)
    user = make_user(db)

    with patch("app.workers.pipeline.run") as mock_pipeline:
        resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("doc.pdf", b"%PDF fake", "application/pdf")},
        )
    assert resp.status_code == 201
    upload_course_id = mock_pipeline.call_args[1]["course_id"]

    mock_client = _mock_chat_client()
    with patch("app.services.chat_service._client", mock_client):
        client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is Bitcoin?"},
            headers=_auth(user.id),
        )
    _, call_kwargs = mock_client.post.call_args_list[0]
    chat_workspace = call_kwargs["json"]["workspace"]

    assert upload_course_id == course.id
    assert chat_workspace == course.id
    assert upload_course_id == chat_workspace


@pytest.mark.integration
def test_different_courses_use_different_workspaces(client, db):
    """Two courses must map to different QVAC workspaces — no cross-course leakage."""
    course_a, _ = make_course_with_lessons(db)
    course_b, _ = make_course_with_lessons(db)
    user = make_user(db)

    mock_a = _mock_chat_client()
    with patch("app.services.chat_service._client", mock_a):
        client.post(
            f"/api/courses/{course_a.id}/chat",
            json={"message": "Question about course A."},
            headers=_auth(user.id),
        )
    _, kwargs_a = mock_a.post.call_args_list[0]
    workspace_a = kwargs_a["json"]["workspace"]

    mock_b = _mock_chat_client()
    with patch("app.services.chat_service._client", mock_b):
        client.post(
            f"/api/courses/{course_b.id}/chat",
            json={"message": "Question about course B."},
            headers=_auth(user.id),
        )
    _, kwargs_b = mock_b.post.call_args_list[0]
    workspace_b = kwargs_b["json"]["workspace"]

    assert workspace_a != workspace_b
    assert workspace_a == course_a.id
    assert workspace_b == course_b.id


# ---------------------------------------------------------------------------
# Upload path
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_pipeline_receives_correct_args_from_upload_api(client, db):
    """Upload API must forward document_id, course_id, filename, and file_path to pipeline.run."""
    course, _ = make_course_with_lessons(db)

    with patch("app.workers.pipeline.run") as mock_pipeline:
        resp = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("lecture.pdf", b"%PDF fake", "application/pdf")},
        )

    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    kwargs = mock_pipeline.call_args[1]

    assert kwargs["document_id"] == doc_id
    assert kwargs["course_id"] == course.id
    assert kwargs["filename"] == "lecture.pdf"
    assert "file_path" in kwargs


# ---------------------------------------------------------------------------
# Chat path
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_posts_to_qvac_query_endpoint(client, db):
    """The chat handler must POST to /retrieve on the QVAC service for dense retrieval."""
    course, _ = make_course_with_lessons(db)
    user = make_user(db)

    mock_client = _mock_chat_client()
    with patch("app.services.chat_service._client", mock_client):
        client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Explain mining."},
            headers=_auth(user.id),
        )

    call_args, _ = mock_client.post.call_args_list[0]
    called_path = call_args[0]
    assert called_path == "/retrieve", f"Expected /retrieve endpoint, got: {called_path}"


@pytest.mark.integration
def test_chat_answer_and_citations_flow_from_qvac_to_client(client, db):
    """Answer and citations from QVAC must reach the HTTP client unchanged."""
    course, _ = make_course_with_lessons(db)
    user = make_user(db)

    expected_answer = "The blockchain is a distributed ledger."
    chunks = [
        _chunk_dict("c1", "A blockchain records transactions.", 0.95),
        _chunk_dict("c2", "Each block links to the previous one.", 0.88),
    ]
    mock_client = _mock_chat_client(chunks=chunks, answer=expected_answer)
    with patch("app.services.chat_service._client", mock_client):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is blockchain?"},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == expected_answer
    assert data["retrieval_used"] is True
    assert len(data["citations"]) == 2
    scores = {c["score"] for c in data["citations"]}
    assert 0.95 in scores
    assert 0.88 in scores


@pytest.mark.integration
def test_chat_topk_is_forwarded_to_qvac(client, db):
    """The QVAC /retrieve call must include a topK parameter."""
    course, _ = make_course_with_lessons(db)
    user = make_user(db)

    mock_client = _mock_chat_client()
    with patch("app.services.chat_service._client", mock_client):
        client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Question about Bitcoin."},
            headers=_auth(user.id),
        )

    _, call_kwargs = mock_client.post.call_args_list[0]
    payload = call_kwargs["json"]
    assert "topK" in payload
    assert isinstance(payload["topK"], int)
    assert payload["topK"] > 0
