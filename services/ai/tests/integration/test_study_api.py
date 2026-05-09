"""Integration tests for POST /api/courses/{course_id}/study.

QVAC is mocked via patch("httpx.AsyncClient.post") so no external service
needs to be running.  The three properties verified per the issue spec are:

1. Correct action dispatch (action echoed in response, retrieval called with
   the right workspace/question).
2. Citations present in the response when QVAC returns sources.
3. Graceful fallback when QVAC is unavailable (200, no citations, answer set).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import create_access_token
from tests.conftest import make_course_with_lessons, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(user_id: str) -> dict:
    token = create_access_token(user_id, "u@test.com", "student")
    return {"Authorization": f"Bearer {token}"}


def _qvac_resp(answer: str = "Bitcoin is a decentralised currency.", sources: list | None = None) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"answer": answer, "sources": sources or []}
    resp.raise_for_status.return_value = None
    return resp


def _qvac_with_sources() -> MagicMock:
    return _qvac_resp(
        answer="Bitcoin uses proof-of-work to achieve consensus.",
        sources=[
            {
                "chunk_id": "c1",
                "snippet": "Bitcoin uses proof-of-work.",
                "score": 0.92,
                "doc_id": "doc-abc",
                "label": "bitcoin_intro.pdf",
                "section": "Consensus",
                "page": 3,
                "slide": 0,
            },
            {
                "chunk_id": "c2",
                "snippet": "Miners compete to find a valid hash.",
                "score": 0.85,
                "doc_id": "doc-abc",
                "label": "bitcoin_intro.pdf",
                "section": "Mining",
                "page": 5,
                "slide": 0,
            },
        ],
    )


def _qvac_empty() -> MagicMock:
    return _qvac_resp(answer="No relevant content found.", sources=[])


def _study_payload(action: str = "explain", query: str = "What is Bitcoin?") -> dict:
    return {"action": action, "query": query}


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_study_requires_auth(client, db):
    course, _ = make_course_with_lessons(db)
    resp = client.post(f"/api/courses/{course.id}/study", json=_study_payload())
    assert resp.status_code == 401


@pytest.mark.integration
def test_study_rejects_invalid_token(client, db):
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/study",
        json=_study_payload(),
        headers={"Authorization": "Bearer bad.token.here"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_study_rejects_missing_action(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/study",
        json={"query": "What is Bitcoin?"},
        headers=_auth(user.id),
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_study_rejects_invalid_action(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/study",
        json={"action": "not_a_real_action", "query": "What is Bitcoin?"},
        headers=_auth(user.id),
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_study_rejects_empty_query(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    resp = client.post(
        f"/api/courses/{course.id}/study",
        json={"action": "explain", "query": ""},
        headers=_auth(user.id),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 1. Correct action dispatch
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("action", ["explain", "summarize", "retrieve", "quiz", "oral", "open_questions"])
def test_study_action_echoed_in_response(client, db, action):
    """action field in the response must match the requested action."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        return_value=_qvac_empty(),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload(action=action),
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    assert resp.json()["action"] == action


@pytest.mark.integration
def test_study_dispatches_with_correct_workspace(client, db):
    """QVAC must be called with workspace == course_id."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock_post = AsyncMock(return_value=_qvac_empty())
    with patch("app.services.study_service._qvac_client.post", mock_post):
        client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "Explain Bitcoin"),
            headers=_auth(user.id),
        )

    _, call_kwargs = mock_post.call_args
    assert call_kwargs["json"]["workspace"] == course.id


@pytest.mark.integration
def test_study_dispatches_with_correct_question(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    mock_post = AsyncMock(return_value=_qvac_empty())
    with patch("app.services.study_service._qvac_client.post", mock_post):
        client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "What is a Merkle tree?"),
            headers=_auth(user.id),
        )

    _, call_kwargs = mock_post.call_args
    assert call_kwargs["json"]["question"] == "What is a Merkle tree?"


@pytest.mark.integration
def test_study_retrieve_action_skips_generation(client, db):
    """retrieve action is retrieve-only: no LLM call, answer comes from passages."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        return_value=_qvac_with_sources(),
    ), patch("app.services.study_service._generate") as mock_generate:
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("retrieve", "What is proof-of-work?"),
            headers=_auth(user.id),
        )

    mock_generate.assert_not_called()
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Citations present in response
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_study_returns_citations_on_hit(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        return_value=_qvac_with_sources(),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "How does consensus work?"),
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_used"] is True
    assert len(data["citations"]) == 2


@pytest.mark.integration
def test_study_citation_schema(client, db):
    """Each citation must have the expected fields with correct types."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        return_value=_qvac_with_sources(),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "Explain mining."),
            headers=_auth(user.id),
        )

    citation = resp.json()["citations"][0]
    assert isinstance(citation["snippet"], str) and citation["snippet"]
    assert isinstance(citation["score"], float)
    assert "label" in citation
    assert "doc_id" in citation
    assert "page" in citation
    assert "section" in citation


@pytest.mark.integration
def test_study_citation_scores_preserved(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        return_value=_qvac_with_sources(),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "Explain proof-of-work."),
            headers=_auth(user.id),
        )

    citations = resp.json()["citations"]
    assert citations[0]["score"] == pytest.approx(0.92, abs=0.01)
    assert citations[1]["score"] == pytest.approx(0.85, abs=0.01)


@pytest.mark.integration
def test_study_no_citations_when_empty_corpus(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        return_value=_qvac_empty(),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "What is Bitcoin?"),
            headers=_auth(user.id),
        )

    data = resp.json()
    assert data["citations"] == []
    assert data["retrieval_used"] is False


# ---------------------------------------------------------------------------
# 3. Fallback when QVAC is down
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_study_qvac_down_returns_200(client, db):
    """When QVAC refuses connections, the endpoint must still return 200."""
    import httpx as _httpx

    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        side_effect=_httpx.ConnectError("connection refused"),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "What is Bitcoin?"),
            headers=_auth(user.id),
        )

    assert resp.status_code == 200


@pytest.mark.integration
def test_study_qvac_down_no_citations(client, db):
    import httpx as _httpx

    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        side_effect=_httpx.ConnectError("connection refused"),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "What is Bitcoin?"),
            headers=_auth(user.id),
        )

    data = resp.json()
    assert data["citations"] == []
    assert data["retrieval_used"] is False


@pytest.mark.integration
def test_study_qvac_down_answer_is_set(client, db):
    """Fallback must produce a non-empty answer string."""
    import httpx as _httpx

    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        side_effect=_httpx.ConnectError("connection refused"),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("explain", "What is Bitcoin?"),
            headers=_auth(user.id),
        )

    assert len(resp.json()["answer"]) > 0


@pytest.mark.integration
def test_study_qvac_timeout_returns_200(client, db):
    import httpx as _httpx

    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        side_effect=_httpx.TimeoutException("read timeout"),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload("summarize", "Summarise Bitcoin consensus."),
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    assert resp.json()["retrieval_used"] is False


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_study_response_has_required_fields(client, db):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)

    with patch(
        "app.services.study_service._qvac_client.post",
        new_callable=AsyncMock,
        return_value=_qvac_empty(),
    ):
        resp = client.post(
            f"/api/courses/{course.id}/study",
            json=_study_payload(),
            headers=_auth(user.id),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) >= {"answer", "citations", "retrieval_used", "action"}
    assert isinstance(data["answer"], str)
    assert isinstance(data["citations"], list)
    assert isinstance(data["retrieval_used"], bool)
    assert isinstance(data["action"], str)
