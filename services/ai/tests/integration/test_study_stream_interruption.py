"""Issue #289: partial Study answers must end visibly in failure, not success."""
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk, EvidencePack
from app.services import study_service
from tests.conftest import make_course_with_lessons, make_user
from tests.integration.test_study_api import _auth, _study_payload


@pytest.mark.parametrize("ending", ["disconnect", "eof", "error_frame"])
def test_interrupted_study_stream_emits_safe_error_and_done(client, db, ending):
    user = make_user(db)
    course, _ = make_course_with_lessons(db)
    chunk = EvidenceChunk(
        chunk_id="c1", text="source passage", score=0.9,
        anchor=CitationAnchor(doc_id="d1", doc_name="source.pdf", page=1, chunk_id="c1", chunk_type="paragraph"),
    )
    pack = EvidencePack(
        query="question", action="explain", chunks=[chunk], total_candidates=1,
        ordering=[0], deduped_passages=[chunk.text],
    )

    async def lines():
        yield 'data: "Partial answer"'
        if ending == "disconnect":
            raise httpx.ReadError("private upstream address")
        if ending == "error_frame":
            yield 'data: "[ERROR] private upstream address"'
            yield 'data: [DONE]'

    response = MagicMock()
    response.aiter_lines = lines

    @asynccontextmanager
    async def stream(*args, **kwargs):
        yield response

    upstream = MagicMock()
    upstream.stream = stream
    with patch("app.services.cache_service.get_cached", return_value=None), \
         patch("app.services.cache_service.set_cached") as cache, \
         patch.object(study_service, "_retrieve_multi", return_value=("", pack)), \
         patch.object(study_service, "_qvac_gen_client", upstream), \
         patch.object(study_service, "_generate", new_callable=AsyncMock) as fallback:
        result = client.post(
            f"/api/courses/{course.id}/study/stream",
            json=_study_payload(), headers=_auth(user.id),
        )

    frames = [line[6:] for line in result.text.splitlines() if line.startswith("data: ")]
    assert frames[-1] == "[DONE]"
    assert [json.loads(frame) for frame in frames[:-1]] == [
        "Partial answer", "[ERROR] Answer interrupted. Please retry.",
    ]
    assert "private" not in result.text
    assert "CITATIONS" not in result.text
    cache.assert_not_called()
    fallback.assert_not_called()
