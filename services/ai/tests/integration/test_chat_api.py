"""Integration tests for POST /api/courses/{course_id}/chat.

The chat endpoint uses a module-level httpx.AsyncClient (_client) that makes
two sequential calls: POST /retrieve (dense retrieval) and POST /generate (LLM).
All tests mock app.services.chat_service._client so no QVAC service is needed.
"""
import httpx
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


def _chunk_dict(chunk_id="c1", content="Bitcoin content.", score=0.9, label="doc.pdf") -> dict:
    return {
        "chunk_id": chunk_id, "content": content, "score": score,
        "label": label, "page": 1, "slide": 0, "section": "Intro", "doc_id": "doc1",
    }


def _mock_chat_client(chunks=None, answer="Test answer.") -> MagicMock:
    """Return a mock _client with post side_effect=[retrieve, generate]."""
    mock = MagicMock()
    mock.post = AsyncMock(side_effect=[_retrieve_resp(chunks), _generate_resp(answer)])
    return mock


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_requires_auth(client, db):
    course, _ = make_course_with_lessons(db)
    resp = client.post(f"/api/courses/{course.id}/chat", json={"message": "What is Bitcoin?"})
    assert resp.status_code == 401


@pytest.mark.integration
def test_chat_rejects_empty_bearer(client, db):
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/chat",
        json={"message": "What is Bitcoin?"},
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_rejects_empty_message(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/chat",
        json={"message": ""},
        headers=_auth(user.id),
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_chat_rejects_missing_message(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/chat",
        json={},
        headers=_auth(user.id),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Empty corpus — QVAC returns no sources
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_empty_corpus_returns_200(client, db):
    """When QVAC finds nothing, the endpoint still returns 200."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = _mock_chat_client(chunks=[], answer="No content indexed yet.")
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is a UTXO?"},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert data["retrieval_used"] is False
    assert data["citations"] == []


@pytest.mark.integration
def test_chat_empty_corpus_answer_is_informative(client, db):
    """Empty-corpus answer must tell the student materials aren't available."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = _mock_chat_client(
        chunks=[],
        answer="No relevant content found in the course materials for this question.",
    )
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Explain the Merkle tree."},
            headers=_auth(user.id),
        )

    answer = resp.json()["answer"].lower()
    assert any(kw in answer for kw in ["no relevant", "not yet", "not found", "materials"])


# ---------------------------------------------------------------------------
# Successful retrieval — QVAC returns sources
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_returns_citations_on_hit(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = _mock_chat_client(
        chunks=[_chunk_dict("c1", "A UTXO is an unspent transaction output.", 0.9)],
        answer="A UTXO is an unspent transaction output.",
    )
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is a UTXO?"},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_used"] is True
    assert len(data["citations"]) == 1
    c = data["citations"][0]
    assert "UTXO" in c["snippet"]
    assert isinstance(c["score"], float)


@pytest.mark.integration
def test_chat_answer_comes_from_qvac_service(client, db):
    """The answer field must be exactly what the QVAC service returned."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    expected = "Proof-of-work is a consensus mechanism."
    mock = _mock_chat_client(
        chunks=[_chunk_dict("c1", "Bitcoin uses proof-of-work.", 0.95)],
        answer=expected,
    )
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Explain proof of work."},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    assert resp.json()["answer"] == expected


@pytest.mark.integration
def test_chat_multiple_citations(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    chunks = [
        _chunk_dict(f"c{i}", f"Content about topic {i}.", round(0.9 - i * 0.05, 2))
        for i in range(3)
    ]
    mock = _mock_chat_client(chunks=chunks, answer="Combined answer.")
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Tell me everything."},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    assert len(resp.json()["citations"]) == 3


@pytest.mark.integration
def test_chat_citation_scores_are_preserved(client, db):
    """Score values from retrieval must appear unchanged in the response."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    chunks = [
        _chunk_dict("c1", "First chunk.", 0.92),
        _chunk_dict("c2", "Second chunk.", 0.77),
    ]
    mock = _mock_chat_client(chunks=chunks, answer="Answer.")
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Question about Bitcoin basics."},
            headers=_auth(user.id),
        )

    citations = resp.json()["citations"]
    scores = {c["score"] for c in citations}
    assert 0.92 in scores
    assert 0.77 in scores


# ---------------------------------------------------------------------------
# QVAC service unavailable
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_qvac_service_unavailable_returns_200(client, db):
    """When the QVAC service is down, the endpoint returns 200 with a non-empty answer."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = MagicMock()
    mock.post = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is Bitcoin?"},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_used"] is False
    assert data["citations"] == []
    assert len(data["answer"]) > 0


@pytest.mark.integration
def test_chat_qvac_timeout_returns_200(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = MagicMock()
    mock.post = AsyncMock(side_effect=httpx.TimeoutException("read timeout"))
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is Bitcoin?"},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    assert resp.json()["retrieval_used"] is False


# ---------------------------------------------------------------------------
# QVAC call parameters — verify the service receives correct inputs
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_sends_course_id_as_workspace(client, db):
    """The /retrieve call must include workspace=course_id."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = _mock_chat_client()
    with patch("app.services.chat_service._client", mock):
        client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Question about Bitcoin."},
            headers=_auth(user.id),
        )

    _, call_kwargs = mock.post.call_args_list[0]
    assert call_kwargs["json"]["workspace"] == course.id


@pytest.mark.integration
def test_chat_sends_question_in_payload(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = _mock_chat_client()
    with patch("app.services.chat_service._client", mock):
        client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is a Merkle root?"},
            headers=_auth(user.id),
        )

    _, call_kwargs = mock.post.call_args_list[0]
    assert call_kwargs["json"]["question"] == "What is a Merkle root?"


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_response_has_required_fields(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = _mock_chat_client(chunks=[], answer="No content found.")
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Hello world?"},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) >= {"answer", "citations", "retrieval_used"}
    assert isinstance(data["answer"], str)
    assert isinstance(data["citations"], list)
    assert isinstance(data["retrieval_used"], bool)


@pytest.mark.integration
def test_chat_citation_has_snippet_and_score_fields(client, db):
    """Each citation must include snippet and score fields."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock = _mock_chat_client(
        chunks=[_chunk_dict("c1", "Some Bitcoin content.", 0.88)],
        answer="Answer.",
    )
    with patch("app.services.chat_service._client", mock):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Explain Bitcoin."},
            headers=_auth(user.id),
        )

    citation = resp.json()["citations"][0]
    assert "snippet" in citation
    assert "score" in citation
    assert isinstance(citation["snippet"], str)
    assert isinstance(citation["score"], float)
