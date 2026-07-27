"""Contract stability — shapes other components depend on must not drift silently.

These are deliberately rigid. A failure here is not necessarily a bug: it means
a contract changed, and the change must be acknowledged by updating the test in
the same pull request. That is the point — the alternative is a field quietly
disappearing and breaking the frontend, the citation UI, or the debug surface
with no signal at review time.
"""
import os
import re
from pathlib import Path

import pytest

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk, EvidencePack
from app.schemas.study_schemas import STUDY_ACTION_REGISTRY, StudyAction

_SERVICES_AI = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SERVICES_AI.parents[1]


# ---------------------------------------------------------------------------
# Study action registry — the frontend renders its UI from this.
# ---------------------------------------------------------------------------

EXPECTED_ACTIONS = {
    "explain",
    "summarize",
    "retrieve",
    "open_questions",
    "quiz",
    "oral",
    "derive",
    "compare",
}


def test_study_action_set_is_stable():
    """Removing or renaming an action breaks the frontend and stored history."""
    actual = {a.value for a in StudyAction}
    assert actual == EXPECTED_ACTIONS, (
        "The study action set changed. Update EXPECTED_ACTIONS and the frontend "
        f"action bar together.\nAdded: {actual - EXPECTED_ACTIONS}\n"
        f"Removed: {EXPECTED_ACTIONS - actual}"
    )


def test_every_action_has_registry_metadata():
    """The dispatcher routes by registry metadata; a missing entry is a KeyError at runtime."""
    for action in StudyAction:
        assert action in STUDY_ACTION_REGISTRY, (
            f"StudyAction.{action.name} has no STUDY_ACTION_REGISTRY entry. "
            f"study_service._route would raise KeyError on this action."
        )


@pytest.mark.parametrize("action", list(StudyAction))
def test_registry_entries_are_fully_populated(action: StudyAction):
    """Every declared field must carry a usable value."""
    meta = STUDY_ACTION_REGISTRY[action]
    assert meta.name, f"{action.value}: empty display name"
    assert meta.description, f"{action.value}: empty description"
    assert meta.example_query, f"{action.value}: empty example query"
    assert meta.output_type in {"prose", "list", "chunks", "qa_pairs"}, (
        f"{action.value}: unexpected output_type {meta.output_type!r} — the "
        f"frontend switches on this value"
    )
    assert isinstance(meta.retrieval_required, bool)
    assert isinstance(meta.generation_required, bool)
    assert isinstance(meta.source_grounding_required, bool)


def test_retrieve_action_stays_generation_free():
    """`retrieve` returns raw passages; enabling generation would change its contract."""
    meta = STUDY_ACTION_REGISTRY[StudyAction.RETRIEVE]
    assert meta.retrieval_required is True
    assert meta.generation_required is False


def test_every_action_requires_retrieval():
    """The product is retrieval-first: no action may generate without evidence."""
    for action, meta in STUDY_ACTION_REGISTRY.items():
        assert meta.retrieval_required is True, (
            f"{action.value} does not require retrieval. This violates the "
            f"retrieval-first principle in docs/overview.md."
        )


# ---------------------------------------------------------------------------
# Evidence pack — the contract between retrieval and generation.
# ---------------------------------------------------------------------------

EXPECTED_PACK_FIELDS = {
    "query",
    "action",
    "chunks",
    "total_candidates",
    "ordering",
    "deduped_passages",
    "total_tokens_estimate",
    "truncated",
    "sources",
}

EXPECTED_ANCHOR_FIELDS = {
    "doc_id",
    "doc_name",
    "section",
    "page",
    "slide",
    "chunk_id",
    "chunk_type",
}


def test_evidence_pack_fields_are_stable():
    actual = set(EvidencePack.model_fields)
    assert actual == EXPECTED_PACK_FIELDS, (
        "EvidencePack changed shape. It is consumed by generation, the citation "
        f"UI and the debug endpoints.\nAdded: {actual - EXPECTED_PACK_FIELDS}\n"
        f"Removed: {EXPECTED_PACK_FIELDS - actual}"
    )


def test_citation_anchor_fields_are_stable():
    """Anchors are how a generated claim traces back to a page or slide."""
    actual = set(CitationAnchor.model_fields)
    assert actual == EXPECTED_ANCHOR_FIELDS, (
        f"CitationAnchor changed shape.\nAdded: {actual - EXPECTED_ANCHOR_FIELDS}\n"
        f"Removed: {EXPECTED_ANCHOR_FIELDS - actual}"
    )


def _anchor(chunk_id: str = "c1") -> CitationAnchor:
    return CitationAnchor(
        doc_id="doc-1",
        doc_name="lecture.pdf",
        section="Consensus",
        page=3,
        slide=None,
        chunk_id=chunk_id,
        chunk_type="paragraph",
    )


def test_context_block_emits_sequential_ref_markers():
    """Generation prompts instruct the model to cite [ref_N]; N must be 1-based
    and sequential, because study_service parses those markers back into citations."""
    pack = EvidencePack(
        query="q",
        action="explain",
        chunks=[],
        total_candidates=0,
        ordering=[],
        deduped_passages=["first passage", "second passage", "third passage"],
    )
    block = pack.context_block()

    markers = re.findall(r"\[ref_(\d+)\]", block)
    assert markers == ["1", "2", "3"], (
        f"context_block must number passages 1..N in order; got {markers}. "
        f"study_service._parse_citations maps [ref_N] to chunks[N-1]."
    )
    assert "first passage" in block


def test_context_block_is_empty_without_passages():
    """An empty pack must produce an empty context, not a stray separator."""
    pack = EvidencePack(
        query="q", action="explain", chunks=[],
        total_candidates=0, ordering=[], deduped_passages=[],
    )
    assert pack.context_block() == ""


def test_evidence_chunk_similarity_score_mirrors_score():
    chunk = EvidenceChunk(chunk_id="c1", text="t", score=0.87, anchor=_anchor())
    assert chunk.similarity_score == 0.87


def test_rerank_score_defaults_to_zero_meaning_not_reranked():
    """evidence_pack_service branches on rerank_score != 0.0 to decide the sort key."""
    chunk = EvidenceChunk(chunk_id="c1", text="t", score=0.5, anchor=_anchor())
    assert chunk.rerank_score == 0.0


# ---------------------------------------------------------------------------
# Configuration integrity — documented defaults must match code defaults.
# ---------------------------------------------------------------------------

def _env_example_keys() -> set[str]:
    path = _SERVICES_AI / ".env.example"
    keys = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def test_env_example_exists_and_is_populated():
    keys = _env_example_keys()
    assert len(keys) > 10, f"services/ai/.env.example looks empty: {keys}"


def test_required_settings_are_documented_in_env_example():
    """A setting with no default must be discoverable, or first boot fails cryptically."""
    keys = _env_example_keys()
    for required in ("DATABASE_URL", "SECRET_KEY", "ENVIRONMENT"):
        assert required in keys, (
            f"{required} is required at startup but absent from .env.example. "
            f"A new contributor cannot start the service."
        )


def test_readme_documents_the_rag_variables_that_exist():
    """The README RAG table drifted from code before (SKIP_CHROMA_INDEX was
    documented as `true` while the code defaulted to `false`). This asserts the
    variables named in the table are ones the code actually reads."""
    readme = (_REPO_ROOT / "README.md").read_text()
    documented = set(re.findall(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", readme, re.MULTILINE))
    assert documented, "No configuration variables found in the README table"

    sources = "\n".join(
        p.read_text()
        for p in (_SERVICES_AI / "app").rglob("*.py")
    )
    for name in sorted(documented):
        assert name in sources, (
            f"README documents `{name}` but no module reads it. Either the "
            f"variable was removed and the README is stale, or it is misspelled."
        )


def test_debug_mode_is_off_by_default():
    """Debug endpoints carry no authentication, so they must never be on by default."""
    from app.core.config import Settings

    saved = os.environ.pop("DEBUG_MODE", None)
    try:
        assert Settings.DEBUG_MODE is False or os.getenv("DEBUG_MODE"), (
            "DEBUG_MODE defaults to true. The debug router exposes unauthenticated "
            "retrieval and document inspection endpoints."
        )
    finally:
        if saved is not None:
            os.environ["DEBUG_MODE"] = saved
