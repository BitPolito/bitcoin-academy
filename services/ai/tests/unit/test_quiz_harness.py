import pytest
from unittest.mock import AsyncMock, patch

from app.services.qvac_structured import LlmDisabledError, StructuredGenerationError
from app.services.quiz_harness import _plan_targets

_CONTEXT = [
    {"label": "p1", "text": "UTXO text", "chunk_id": "c1"},
    {"label": "p2", "text": "PoW text", "chunk_id": "c2"},
]


@pytest.mark.asyncio
async def test_plan_targets_maps_passage_index_to_chunk_id():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"targets": [
            {"passage_index": 2, "cognitive_level": "application"},
            {"passage_index": 1, "cognitive_level": "recall"},
        ]}
        targets = await _plan_targets(_CONTEXT, target_count=2)

    assert targets == [
        {"chunk_id": "c2", "cognitive_level": "application"},
        {"chunk_id": "c1", "cognitive_level": "recall"},
    ]


@pytest.mark.asyncio
async def test_plan_targets_corrects_invalid_passage_index():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"targets": [{"passage_index": 99, "cognitive_level": "recall"}]}
        targets = await _plan_targets(_CONTEXT, target_count=1)

    assert targets[0]["chunk_id"] in {"c1", "c2"}


@pytest.mark.asyncio
async def test_plan_targets_pads_when_model_returns_too_few():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"targets": [{"passage_index": 1, "cognitive_level": "recall"}]}
        targets = await _plan_targets(_CONTEXT, target_count=3)

    assert len(targets) == 3


@pytest.mark.asyncio
async def test_plan_targets_reuses_chunks_when_target_count_exceeds_available():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"targets": []}
        targets = await _plan_targets(_CONTEXT, target_count=5)

    assert len(targets) == 5
    assert {t["chunk_id"] for t in targets} == {"c1", "c2"}


@pytest.mark.asyncio
async def test_plan_targets_propagates_llm_disabled():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.side_effect = LlmDisabledError("disabled")
        with pytest.raises(LlmDisabledError):
            await _plan_targets(_CONTEXT, target_count=1)
