"""Integration tests for POST /api/courses/{course_id}/chat.

The chat endpoint now delegates to the QVAC Node.js service via httpx.post.
All tests mock httpx.post so no QVAC service needs to be running.

Citation schema changed from {label, section, page, slide, text_snippet}
to {snippet, score} to match the QVAC /query response format.
"""
import httpx
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


def _qvac_ok(answer="Test answer.", sources=None) -> MagicMock:
    """Build a mock httpx.Response for a successful QVAC /query call."""
    resp = MagicMock()
    resp.json.return_value = {"answer": answer, "sources": sources or []}
    resp.raise_for_status.return_value = None
    return resp


def _qvac_empty() -> MagicMock:
    """QVAC response when no content is indexed for the workspace."""
    return _qvac_ok(
        answer="No relevant content found for this question in the indexed course material.",
        sources=[],
    )


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

    with patch("httpx.post", return_value=_qvac_empty()):
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

    with patch("httpx.post", return_value=_qvac_empty()):
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

    with patch("httpx.post", return_value=_qvac_ok(
        answer="A UTXO is an unspent transaction output.",
        sources=[{"snippet": "A UTXO is an unspent transaction output.", "score": 0.9}],
    )):
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
    with patch("httpx.post", return_value=_qvac_ok(
        answer=expected,
        sources=[{"snippet": "Bitcoin uses proof-of-work.", "score": 0.95}],
    )):
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

    sources = [
        {"snippet": f"Content about topic {i}.", "score": round(0.9 - i * 0.05, 2)}
        for i in range(3)
    ]
    with patch("httpx.post", return_value=_qvac_ok(answer="Combined answer.", sources=sources)):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Tell me everything."},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    assert len(resp.json()["citations"]) == 3


@pytest.mark.integration
def test_chat_citation_scores_are_preserved(client, db):
    """Score values returned by QVAC must appear unchanged in the response."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    sources = [
        {"snippet": "First chunk.", "score": 0.92},
        {"snippet": "Second chunk.", "score": 0.77},
    ]
    with patch("httpx.post", return_value=_qvac_ok(answer="Answer.", sources=sources)):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Question."},
            headers=_auth(user.id),
        )

    citations = resp.json()["citations"]
    assert citations[0]["score"] == 0.92
    assert citations[1]["score"] == 0.77


# ---------------------------------------------------------------------------
# QVAC service unavailable
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_qvac_service_unavailable_returns_200(client, db):
    """When the QVAC service is down, the endpoint returns 200 with an error message."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch("httpx.post", side_effect=httpx.HTTPError("connection refused")):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is Bitcoin?"},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_used"] is False
    assert data["citations"] == []
    assert "unavailable" in data["answer"].lower()


@pytest.mark.integration
def test_chat_qvac_timeout_returns_200(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch("httpx.post", side_effect=httpx.TimeoutException("read timeout")):
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
    """httpx.post must be called with workspace=course_id."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch("httpx.post", return_value=_qvac_ok()) as mock_post:
        client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Question."},
            headers=_auth(user.id),
        )

    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["json"]["workspace"] == course.id


@pytest.mark.integration
def test_chat_sends_question_in_payload(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch("httpx.post", return_value=_qvac_ok()) as mock_post:
        client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is a Merkle root?"},
            headers=_auth(user.id),
        )

    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["json"]["question"] == "What is a Merkle root?"


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_response_has_required_fields(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch("httpx.post", return_value=_qvac_empty()):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Hello?"},
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
    """Each citation must have exactly snippet and score."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch("httpx.post", return_value=_qvac_ok(
        answer="Answer.",
        sources=[{"snippet": "Some Bitcoin content.", "score": 0.88}],
    )):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Explain Bitcoin."},
            headers=_auth(user.id),
        )

    citation = resp.json()["citations"][0]
    assert set(citation.keys()) == {"snippet", "score"}
    assert isinstance(citation["snippet"], str)
    assert isinstance(citation["score"], float)
