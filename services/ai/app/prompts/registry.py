"""Central, read-only index of every system prompt used for LLM generation
in this codebase — course builder (outline, content, judge), quiz
generation, and the 8 study actions.

Each entry *mirrors* the prompt text and version constant owned by its
source module (outline_service, lesson_service, quiz_generation,
study_service) rather than duplicating the string — bump the version where
the prompt is actually defined and this index, and anything derived from it
(content_hash, GenerationRun.prompt_version), pick up the change
automatically. There is deliberately no reverse dependency: the owning
modules do not import this registry, so there is no import cycle and no risk
of the registry being the thing that breaks when a service module changes.

Use get_prompt(name) to inspect what version of what prompt produced a given
piece of generated content — e.g. when two runs disagree and you need to
know whether the prompt itself changed between them.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str


def _build_registry() -> Dict[str, Prompt]:
    from app.services import lesson_service, outline_service, quiz_generation, study_service

    entries: Dict[str, Prompt] = {
        "outline_map": Prompt(
            "outline_map", outline_service.OUTLINE_PROMPT_VERSION, outline_service._MAP_SYSTEM,
        ),
        "outline_reduce": Prompt(
            "outline_reduce", outline_service.OUTLINE_PROMPT_VERSION, outline_service._REDUCE_SYSTEM,
        ),
        "content_gen": Prompt(
            "content_gen", lesson_service.CONTENT_PROMPT_VERSION, lesson_service._CONTENT_SYSTEM,
        ),
        "judge": Prompt(
            "judge", lesson_service.CONTENT_PROMPT_VERSION, lesson_service._JUDGE_SYSTEM,
        ),
        "quiz_gen": Prompt(
            "quiz_gen", quiz_generation.QUIZ_PROMPT_VERSION, quiz_generation.QUIZ_SYSTEM,
        ),
    }
    for action, text in study_service._SYSTEM_PROMPTS.items():
        key = f"study_{action.value}"
        entries[key] = Prompt(key, study_service.STUDY_PROMPT_VERSION, text)
    return entries


_registry_cache: Optional[Dict[str, Prompt]] = None


def _registry() -> Dict[str, Prompt]:
    # Built lazily (not at module import time) so importing app.prompts never
    # forces app.services.* to load before they're otherwise needed — avoids
    # import-order surprises during app startup and in tests that only need
    # a subset of the service layer.
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = _build_registry()
    return _registry_cache


def get_prompt(name: str) -> Prompt:
    reg = _registry()
    if name not in reg:
        raise KeyError(f"Unknown prompt '{name}' — registered: {sorted(reg)}")
    return reg[name]


def list_prompts() -> List[Prompt]:
    return sorted(_registry().values(), key=lambda p: p.name)
