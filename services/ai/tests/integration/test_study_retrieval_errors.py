"""A successful empty search is not a retrieval service failure (issue #210)."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.rag import query_rewriter
from app.core.errors import ExternalServiceError
from app.schemas.study_schemas import StudyAction
from app.services import study_service
from tests.conftest import make_course_with_lessons, make_user
from tests.integration.test_study_api import _auth, _study_payload


@pytest.fixture(autouse=True)
def isolated_retrieval(monkeypatch):
    monkeypatch.setattr(query_rewriter, "_HYDE_ENABLED", False)
    monkeypatch.setattr(query_rewriter, "_REWRITE_ENABLED", False)
    monkeypatch.setattr("app.services.cache_service.get_cached", lambda *a: None)


@pytest.mark.integration
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("error,code,message", [
    (httpx.ConnectError("private upstream address"), "RETRIEVAL_UNAVAILABLE", "unavailable"),
    (httpx.ReadTimeout("private upstream address"), "RETRIEVAL_TIMEOUT", "too long"),
    (ValueError("private response data"), "RETRIEVAL_FAILED", "could not complete"),
])
def test_retrieval_failure_is_an_error_not_an_empty_answer(client, db, stream, error, code, message):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    suffix = "/stream" if stream else ""
    with patch.object(study_service, "unified_retrieval", side_effect=error), \
         patch.object(study_service, "_generate", new_callable=AsyncMock) as generate, \
         patch.object(study_service, "_stream_generate") as stream_generate, \
         patch("app.services.cache_service.set_cached") as cache:
        response = client.post(
            f"/api/courses/{course.id}/study{suffix}",
            json=_study_payload(), headers=_auth(user.id),
        )

    if stream:
        frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
        assert frames[-1] == "[DONE]"
        assert json.loads(frames[0]).startswith("[ERROR] ")
    else:
        assert response.status_code == 503
        assert response.json()["error"]["code"] == code
    assert message in response.text
    assert "No relevant content" not in response.text
    assert "private" not in response.text
    generate.assert_not_called()
    stream_generate.assert_not_called()
    cache.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("subquery_has_evidence,final_has_evidence", [
    (False, False), (True, False), (False, True),
])
async def test_two_hop_keeps_useful_evidence_but_does_not_hide_failure(
    subquery_has_evidence, final_has_evidence,
):
    from tests.unit.test_study_service import _make_pack

    empty = study_service._empty_pack("Bitcoin versus Ethereum", StudyAction.COMPARE)
    evidence = _make_pack()
    error = ExternalServiceError(message="Search unavailable", code="RETRIEVAL_UNAVAILABLE")
    responses = [error, ("", evidence if subquery_has_evidence else empty)]
    if not subquery_has_evidence:
        responses.append(("", evidence if final_has_evidence else empty))
    with patch.object(study_service, "_retrieve", side_effect=responses):
        if subquery_has_evidence or final_has_evidence:
            _, pack = await study_service._retrieve_multi(
                "Bitcoin versus Ethereum", "course-1", StudyAction.COMPARE,
            )
            assert pack.chunks
        else:
            with pytest.raises(ExternalServiceError):
                await study_service._retrieve_multi(
                    "Bitcoin versus Ethereum", "course-1", StudyAction.COMPARE,
                )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_qvac_connection_error_still_accepts_chroma_fallback():
    from tests.unit.test_study_service import _make_chunk

    chunk = _make_chunk()
    with patch.object(study_service._qvac_client, "post", side_effect=httpx.ConnectError("down")), \
         patch("app.rag.retriever._chroma_retrieve", return_value=[chunk]), \
         patch("app.services.hybrid_search.bm25_search", return_value=[]), \
         patch("app.services.reranker.rerank", side_effect=lambda q, chunks: chunks), \
         patch("app.services.reranker.mmr_select", side_effect=lambda chunks, k: chunks), \
         patch("app.services.parent_expansion.expand_to_parents", side_effect=lambda chunks: chunks):
        _, pack = await study_service._retrieve("Bitcoin", "course-1", StudyAction.EXPLAIN)
    assert pack.chunks[0].chunk_id == chunk.chunk_id


@pytest.mark.integration
@pytest.mark.parametrize("stream", [False, True])
def test_successful_empty_search_remains_a_normal_result(client, db, stream):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    suffix = "/stream" if stream else ""
    with patch.object(study_service, "unified_retrieval", return_value=([], [])), \
         patch.object(study_service, "_generate", new_callable=AsyncMock) as generate, \
         patch.object(study_service, "_stream_generate") as stream_generate, \
         patch("app.services.cache_service.set_cached") as cache:
        response = client.post(
            f"/api/courses/{course.id}/study{suffix}",
            json=_study_payload(), headers=_auth(user.id),
        )
    assert response.status_code == 200
    assert "No relevant content found." in response.text
    assert "[ERROR]" not in response.text
    if not stream:
        assert response.json()["citations"] == []
        assert response.json()["retrieval_used"] is False
    generate.assert_not_called()
    stream_generate.assert_not_called()
    cache.assert_not_called()
