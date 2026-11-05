import pytest
from unittest.mock import AsyncMock, patch

from app.services.qvac_structured import LlmDisabledError, StructuredGenerationError
from app.services.quiz_harness import _critique_one, _generate_one, _plan_targets, run

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


@pytest.mark.asyncio
async def test_critique_one_passes_when_all_criteria_met():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {
            "entailed": True, "distractors_plausible": True, "single_defensible": True,
            "requires_course_material": True, "duplicate": False,
        }
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict == {"passed": True, "failed_criteria": []}


@pytest.mark.asyncio
async def test_critique_one_reports_each_failed_criterion():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {
            "entailed": False, "distractors_plausible": True, "single_defensible": True,
            "requires_course_material": True, "duplicate": True,
        }
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict["passed"] is False
    assert set(verdict["failed_criteria"]) == {"entailed", "duplicate"}


@pytest.mark.asyncio
async def test_critique_one_handles_missing_fields_defensively():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {"entailed": True}  # worker returned a partial object
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict["passed"] is False
    assert "distractors_plausible" in verdict["failed_criteria"]


@pytest.mark.asyncio
async def test_critique_one_passes_accepted_questions_as_duplicate_context():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.return_value = {
            "entailed": True, "distractors_plausible": True, "single_defensible": True,
            "requires_course_material": True, "duplicate": False,
        }
        await _critique_one(_QUESTION, "UTXO text", [{"prompt": "Earlier question?"}])

    prompt_arg = mock_gj.call_args.args[0]
    assert "Earlier question?" in prompt_arg


@pytest.mark.asyncio
async def test_critique_one_fails_closed_on_llm_disabled():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.side_effect = LlmDisabledError("disabled")
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict["passed"] is False
    assert verdict["failed_criteria"] == ["critic unavailable"]


@pytest.mark.asyncio
async def test_critique_one_fails_closed_on_structured_generation_error():
    with patch("app.services.quiz_harness.generate_json", new_callable=AsyncMock) as mock_gj:
        mock_gj.side_effect = StructuredGenerationError("bad schema")
        verdict = await _critique_one(_QUESTION, "UTXO text", [])

    assert verdict["passed"] is False
    assert verdict["failed_criteria"] == ["critic unavailable"]


@pytest.mark.asyncio
async def test_run_all_pass_returns_every_question_with_no_repairs():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.quiz_harness._generate_one", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.quiz_harness._critique_one", new_callable=AsyncMock) as mock_crit:
        mock_plan.return_value = [{"chunk_id": "c1", "cognitive_level": "recall"}] * 2
        mock_gen.return_value = dict(_QUESTION)
        mock_crit.return_value = {"passed": True, "failed_criteria": []}

        result = await run("UTXO model", _CONTEXT, target_count=2)

    assert len(result["questions"]) == 2
    assert result["trace"]["repaired"] == 0
    assert result["trace"]["final_count"] == 2
    assert result["trace"]["calls_used"] == 1 + 2 + 2  # plan + 2 generate + 2 critique


@pytest.mark.asyncio
async def test_run_rejected_then_repaired_is_recorded_and_kept():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.quiz_harness._generate_one", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.quiz_harness._critique_one", new_callable=AsyncMock) as mock_crit:
        mock_plan.return_value = [{"chunk_id": "c1", "cognitive_level": "recall"}]
        mock_gen.return_value = dict(_QUESTION)
        mock_crit.side_effect = [
            {"passed": False, "failed_criteria": ["entailed"]},
            {"passed": True, "failed_criteria": []},
        ]

        result = await run("UTXO model", _CONTEXT, target_count=1)

    assert result["trace"]["repaired"] == 1
    assert len(result["questions"]) == 1
    assert result["trace"]["calls_used"] == 1 + 2 + 2  # plan + (generate+critique) x2


@pytest.mark.asyncio
async def test_run_retry_limit_reached_drops_the_question_with_reasons():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.quiz_harness._generate_one", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.quiz_harness._critique_one", new_callable=AsyncMock) as mock_crit:
        mock_plan.return_value = [{"chunk_id": "c1", "cognitive_level": "recall"}]
        mock_gen.return_value = dict(_QUESTION)
        mock_crit.return_value = {"passed": False, "failed_criteria": ["entailed"]}

        result = await run("UTXO model", _CONTEXT, target_count=1)

    assert result["questions"] == []
    assert result["trace"]["final_count"] == 0
    assert len(result["trace"]["rejected"]) == 1
    assert result["trace"]["rejected"][0]["reasons"] == ["entailed"]
    # Exactly one repair attempt — no third generate/critique pass.
    assert result["trace"]["calls_used"] == 1 + 2 + 2


@pytest.mark.asyncio
async def test_run_llm_disabled_at_plan_stage_returns_no_questions():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan:
        mock_plan.side_effect = LlmDisabledError("disabled")

        result = await run("UTXO model", _CONTEXT, target_count=2)

    assert result["questions"] == []
    assert result["trace"]["final_count"] == 0


@pytest.mark.asyncio
async def test_run_llm_disabled_mid_generate_drops_that_target_and_continues():
    with patch("app.services.quiz_harness._plan_targets", new_callable=AsyncMock) as mock_plan, \
         patch("app.services.quiz_harness._generate_one", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.quiz_harness._critique_one", new_callable=AsyncMock) as mock_crit:
        mock_plan.return_value = [{"chunk_id": "c1", "cognitive_level": "recall"}] * 2
        mock_gen.side_effect = [dict(_QUESTION), None]  # second target's generation failed
        mock_crit.return_value = {"passed": True, "failed_criteria": []}

        result = await run("UTXO model", _CONTEXT, target_count=2)

    assert len(result["questions"]) == 1
    assert len(result["trace"]["rejected"]) == 1
