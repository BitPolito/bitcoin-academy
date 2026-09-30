"""Unit tests for app/prompts/registry.py — P6.

The registry mirrors prompt text/version owned by each service module; these
tests mostly guard against regressions in that mirroring (wrong version
picked up, a prompt silently dropped) rather than testing prompt content
itself.
"""
from app.prompts import get_prompt, list_prompts
from app.prompts.registry import Prompt


EXPECTED_NAMES = {
    "outline_map", "outline_reduce", "content_gen", "judge", "quiz_gen",
    "study_explain", "study_summarize", "study_open_questions", "study_quiz",
    "study_oral", "study_derive", "study_compare",
}


def test_list_prompts_covers_every_expected_entry():
    names = {p.name for p in list_prompts()}
    assert names == EXPECTED_NAMES


def test_list_prompts_sorted_by_name():
    names = [p.name for p in list_prompts()]
    assert names == sorted(names)


def test_get_prompt_returns_prompt_instance():
    p = get_prompt("content_gen")
    assert isinstance(p, Prompt)
    assert p.name == "content_gen"
    assert p.system  # non-empty


def test_get_prompt_raises_keyerror_for_unknown_name():
    import pytest
    with pytest.raises(KeyError, match="Unknown prompt"):
        get_prompt("does-not-exist")


def test_content_gen_version_matches_lesson_service_constant():
    from app.services import lesson_service
    assert get_prompt("content_gen").version == lesson_service.CONTENT_PROMPT_VERSION
    assert get_prompt("content_gen").system == lesson_service._CONTENT_SYSTEM


def test_judge_version_matches_lesson_service_constant():
    from app.services import lesson_service
    assert get_prompt("judge").version == lesson_service.CONTENT_PROMPT_VERSION
    assert get_prompt("judge").system == lesson_service._JUDGE_SYSTEM


def test_quiz_gen_version_matches_quiz_generation_constant():
    from app.services import quiz_generation
    assert get_prompt("quiz_gen").version == quiz_generation.QUIZ_PROMPT_VERSION
    assert get_prompt("quiz_gen").system == quiz_generation.QUIZ_SYSTEM


def test_outline_prompts_version_match_outline_service_constant():
    from app.services import outline_service
    assert get_prompt("outline_map").version == outline_service.OUTLINE_PROMPT_VERSION
    assert get_prompt("outline_reduce").version == outline_service.OUTLINE_PROMPT_VERSION


def test_study_prompts_mirror_study_service_dict():
    from app.services import study_service
    from app.schemas.study_schemas import StudyAction

    for action, text in study_service._SYSTEM_PROMPTS.items():
        entry = get_prompt(f"study_{action.value}")
        assert entry.system == text
        assert entry.version == study_service.STUDY_PROMPT_VERSION

    # RETRIEVE has no generation prompt (RAG-only action) — must not appear.
    assert StudyAction.RETRIEVE not in study_service._SYSTEM_PROMPTS


def test_content_hash_bump_reflected_via_registry(monkeypatch):
    """A version bump at the source constant must be visible through the
    registry on next lookup — proves there's no stale copy anywhere."""
    from app.services import lesson_service
    import app.prompts.registry as registry_module

    # Force a fresh registry build after monkeypatching the source constant.
    registry_module._registry_cache = None
    monkeypatch.setattr(lesson_service, "CONTENT_PROMPT_VERSION", "v99-test")
    try:
        assert get_prompt("content_gen").version == "v99-test"
    finally:
        registry_module._registry_cache = None  # avoid leaking into other tests
