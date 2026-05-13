"""Parent-chunk expansion — replaces child text with richer parent context.

Retrieval returns short child chunks (~150 words, precise for matching).
Before handing context to the LLM, we fetch the corresponding parent text
(~1200 words) so the model has full surrounding context. Citation anchors
(page, slide, section) remain at child precision for source attribution.

Only pipeline.py-generated child chunks follow the naming convention that
makes parent IDs derivable. QVAC chunks are returned unchanged.
"""
import logging
import re
from typing import List

from app.schemas.evidence_pack import EvidenceChunk

logger = logging.getLogger(__name__)

# Child IDs produced by pipeline.py: {doc_id}_p{NNNN}_c{NNNN}
_CHILD_SUFFIX_RE = re.compile(r"_c\d{4}$")


def _parent_id_from_child(chunk_id: str) -> str | None:
    """Derive parent_id by stripping the _cNNNN suffix, or return None."""
    m = _CHILD_SUFFIX_RE.search(chunk_id)
    return chunk_id[: m.start()] if m else None


def expand_to_parents(chunks: List[EvidenceChunk]) -> List[EvidenceChunk]:
    """Replace child text with parent text for LLM context generation.

    - Expansion is best-effort: chunks whose parent is missing are returned
      unchanged (graceful degradation to child text).
    - When two sibling children share the same parent_id, only the first
      sibling gets the expanded parent text to avoid duplicate context blocks.
    - Citation anchors stay from the child for precise source attribution.
    """
    if not chunks:
        return chunks

    parent_ids = {
        pid
        for c in chunks
        if (pid := _parent_id_from_child(c.chunk_id)) is not None
    }
    if not parent_ids:
        return chunks

    parent_texts = _fetch_parent_texts(list(parent_ids))
    if not parent_texts:
        return chunks

    seen_parents: set[str] = set()
    expanded: List[EvidenceChunk] = []
    for chunk in chunks:
        pid = _parent_id_from_child(chunk.chunk_id)
        if pid and pid in parent_texts and pid not in seen_parents:
            seen_parents.add(pid)
            expanded.append(chunk.model_copy(update={"text": parent_texts[pid]}))
        else:
            # Sibling from same parent or no-parent chunk — keep child text.
            expanded.append(chunk)

    n_expanded = sum(1 for a, b in zip(chunks, expanded) if a.text != b.text)
    logger.debug(
        "Parent expansion: %d/%d chunks expanded to parent context",
        n_expanded, len(chunks),
    )
    return expanded


def _fetch_parent_texts(parent_ids: List[str]) -> dict[str, str]:
    """Fetch parent chunk texts from the DB in a single query."""
    try:
        from app.db.session import get_db_context  # noqa: PLC0415
        from app.db.models import ChunkParent       # noqa: PLC0415

        with get_db_context() as db:
            rows = (
                db.query(ChunkParent)
                .filter(ChunkParent.id.in_(parent_ids))
                .all()
            )
            return {row.id: row.text for row in rows}
    except Exception as exc:
        logger.warning(
            "Parent DB fetch failed — using child text as LLM context: %s", exc
        )
        return {}
