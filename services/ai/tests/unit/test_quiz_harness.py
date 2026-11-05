import pytest
from unittest.mock import AsyncMock, patch

from app.services.qvac_structured import LlmDisabledError, StructuredGenerationError
from app.services.quiz_harness import _generate_one, _plan_targets

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


_TARGET = {"chunk_id": "c1", "cognitive_level": "recall"}

_QUESTION = {
    "prompt": "What is a UTXO?",
    "options": [
        {"key": "A", "text": "An unspent transaction output"},
        {"key": "B", "text": "A mining reward"},
        {"key": "C", "text": "A block header"},
        {"key": "D", "text": "A wallet address"},
    ],
    "correct_key": "A",
    "concept_tag": "utxo-model",
    "difficulty": "beginner",
}


@pytest.mark.asyncio
async def test_generate_one_attaches_chunk_id():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = dict(_QUESTION)
        question = await _generate_one(_TARGET, _CONTEXT)

    assert question["chunk_id"] == "c1"
    assert question["prompt"] == "What is a UTXO?"


@pytest.mark.asyncio
async def test_generate_one_scopes_context_to_the_target_chunk():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = dict(_QUESTION)
        await _generate_one(_TARGET, _CONTEXT)

    call_context = mock_gj.call_args.kwargs["context"]
    assert call_context == [{"label": "p1", "text": "UTXO text", "chunk_id": "c1"}]


@pytest.mark.asyncio
async def test_generate_one_includes_feedback_in_prompt_when_repairing():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = dict(_QUESTION)
        await _generate_one(_TARGET, _CONTEXT, feedback="rejected: distractors too easy")

    prompt_arg = mock_gj.call_args.args[0]
    assert "rejected: distractors too easy" in prompt_arg


@pytest.mark.asyncio
async def test_generate_one_returns_none_on_structured_generation_error():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.side_effect = StructuredGenerationError("bad schema")
        question = await _generate_one(_TARGET, _CONTEXT)

    assert question is None


@pytest.mark.asyncio
async def test_generate_one_returns_none_for_unresolvable_chunk_id():
    unresolvable_target = {"chunk_id": "does-not-exist", "cognitive_level": "recall"}
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        question = await _generate_one(unresolvable_target, _CONTEXT)

    assert question is None
    mock_gj.assert_not_called()
