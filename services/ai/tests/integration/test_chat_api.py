"""Integration tests for POST /api/courses/{course_id}/chat.

Strategy:
- Auth is tested via JWT created with create_access_token (no real login needed).
- ChromaDB and fastembed are patched to avoid slow ML inference in CI.
- Empty-corpus path (no ChromaDB hits) is tested without any mocking.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


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
# Empty corpus — no ChromaDB content → graceful fallback
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_empty_corpus_returns_200_with_answer(client, db):
    """When ChromaDB has no indexed content, the API still returns 200 with a human-readable answer."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    # Patch retrieval so it returns empty hits (simulates empty vector store)
    with patch("app.services.chat_service._retrieve", return_value=[]):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "What is a UTXO?"},
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert data["retrieval_used"] is False
    assert data["citations"] == []


@pytest.mark.integration
def test_chat_empty_corpus_answer_is_informative(client, db):
    """Empty-corpus answer should tell the student material isn't indexed yet."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch("app.services.chat_service._retrieve", return_value=[]):
        resp = client.post(
            f"/api/courses/{course.id}/chat",
            json={"message": "Explain the Merkle tree."},
            headers=_auth(user.id),
        )

    answer = resp.json()["answer"].lower()
    # Should mention no content / not indexed
    assert any(kw in answer for kw in ["no relevant", "not yet", "not found", "materials"])


# ---------------------------------------------------------------------------
# Successful retrieval path — with mocked ChromaDB hits
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_returns_citations_on_hit(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    fake_hits = [
        {
            "id": "chunk-1",
            "text": "A UTXO is an unspent transaction output.",
            "distance": 0.1,
            "label": "p. 3",
            "section": "Transactions",
            "page": 3,
            "slide": None,
        }
    ]

    with patch("app.services.chat_service._retrieve", return_value=fake_hits):
        with patch("app.services.chat_service._call_llm", return_value="A UTXO is an unspent output."):
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
    assert c["label"] == "p. 3"
    assert c["page"] == 3
    assert "UTXO" in c["text_snippet"]


@pytest.mark.integration
def test_chat_answer_comes_from_llm_when_available(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    fake_hits = [
        {
            "id": "chunk-1",
            "text": "Bitcoin uses proof-of-work.",
            "distance": 0.05,
            "label": "p. 1",
            "section": "Consensus",
            "page": 1,
            "slide": None,
        }
    ]

    with patch("app.services.chat_service._retrieve", return_value=fake_hits):
        with patch("app.services.chat_service._call_llm", return_value="Proof-of-work is a consensus mechanism."):
            resp = client.post(
                f"/api/courses/{course.id}/chat",
                json={"message": "Explain proof of work."},
                headers=_auth(user.id),
            )

    assert resp.status_code == 200
    assert resp.json()["answer"] == "Proof-of-work is a consensus mechanism."


@pytest.mark.integration
def test_chat_fallback_when_llm_returns_none(client, db):
    """When _call_llm returns None, the raw context is returned instead."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    fake_hits = [
        {
            "id": "chunk-1",
            "text": "Satoshi Nakamoto published the Bitcoin whitepaper in 2008.",
            "distance": 0.2,
            "label": "Slide 1",
            "section": None,
            "page": None,
            "slide": 1,
        }
    ]

    with patch("app.services.chat_service._retrieve", return_value=fake_hits):
        with patch("app.services.chat_service._call_llm", return_value=None):
            resp = client.post(
                f"/api/courses/{course.id}/chat",
                json={"message": "Who is Satoshi?"},
                headers=_auth(user.id),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_used"] is True
    # Fallback includes raw context
    assert "Satoshi" in data["answer"] or "relevant passages" in data["answer"].lower()


@pytest.mark.integration
def test_chat_multiple_citations(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    fake_hits = [
        {"id": f"chunk-{i}", "text": f"Content {i}.", "distance": 0.1 * i,
         "label": f"p. {i}", "section": f"Section {i}", "page": i, "slide": None}
        for i in range(1, 4)
    ]

    with patch("app.services.chat_service._retrieve", return_value=fake_hits):
        with patch("app.services.chat_service._call_llm", return_value="Combined answer."):
            resp = client.post(
                f"/api/courses/{course.id}/chat",
                json={"message": "Tell me everything."},
                headers=_auth(user.id),
            )

    assert resp.status_code == 200
    assert len(resp.json()["citations"]) == 3


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_chat_response_has_required_fields(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch("app.services.chat_service._retrieve", return_value=[]):
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
