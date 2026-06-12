"""Outline generation service — Phase 2 of the course builder.

Map-reduce pipeline:
  map  : for each document, call /generate_json once per top-level section to
         extract topic candidates grounded on real parent-chunk text.
  reduce: single LLM call to group candidates into chapters, deduplicate across
          documents, and order them pedagogically.
  persist: write draft Chapter / Lesson rows + update GenerationRun provenance.

All LLM calls go through qvac_structured.generate_json which enforces JSON
schema server-side (extraction + validation + correction retries).
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import (
    Chapter,
    ChunkParent,
    CourseDocument,
    DocumentStatus,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
)
from app.services.qvac_structured import (
    LlmDisabledError,
    StructuredGenerationError,
    generate_json,
)

logger = logging.getLogger(__name__)

OUTLINE_PROMPT_VERSION = "v1"

# How many top-level sections to map per document (token-budget guard).
MAX_SECTIONS_PER_DOC = 20
# Total words of parent-chunk preview sent as context for one section.
MAX_WORDS_PER_SECTION = 800
# Cap total candidates fed to the reduce step.
MAX_CANDIDATES_TOTAL = 50


# ---------------------------------------------------------------------------
# JSON schemas for /generate_json calls
# ---------------------------------------------------------------------------

_MAP_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["lessons"],
    "properties": {
        "lessons": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["title", "key_concepts", "difficulty"],
                "properties": {
                    "title": {"type": "string"},
                    "key_concepts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 6,
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["beginner", "intermediate", "advanced"],
                    },
                },
            },
        }
    },
}

_REDUCE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["chapters"],
    "properties": {
        "chapters": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "required": ["title", "description", "lessons"],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "lessons": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "required": [
                                "title",
                                "description",
                                "objectives",
                                "candidate_indices",
                            ],
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "objectives": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 1,
                                    "maxItems": 4,
                                },
                                "candidate_indices": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 1,
                                },
                            },
                        },
                    },
                },
            },
        }
    },
}

_MAP_SYSTEM = (
    "You are an expert curriculum designer. "
    "Given a document section and its source text, extract self-contained "
    "lesson topics suitable for a structured course. "
    "Stay strictly faithful to the source material — do not invent content."
)

_REDUCE_SYSTEM = (
    "You are an expert curriculum designer. "
    "Group the given lesson topics into a coherent, pedagogically ordered course. "
    "Order chapters from foundational to advanced. "
    "Merge near-duplicate topics that cover the same concept. "
    "Reference every topic by its index — do not leave any topic unused."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_chunk_ids(section: Dict[str, Any], max_chunks: int = 8) -> List[str]:
    """BFS over section tree, collecting parent_chunk_ids up to max_chunks."""
    result: List[str] = []
    queue = [section]
    while queue and len(result) < max_chunks:
        node = queue.pop(0)
        for cid in node.get("parent_chunk_ids", []):
            if len(result) >= max_chunks:
                break
            result.append(cid)
        queue.extend(node.get("children", []))
    return result


def _section_context(
    chunk_ids: List[str], db: Session
) -> List[Dict[str, str]]:
    """Fetch up to MAX_WORDS_PER_SECTION words of parent-chunk text as context items."""
    if not chunk_ids:
        return []
    rows = {r.id: r for r in db.query(ChunkParent).filter(ChunkParent.id.in_(chunk_ids)).all()}
    items: List[Dict[str, str]] = []
    total_words = 0
    for cid in chunk_ids:
        if cid not in rows:
            continue
        words = rows[cid].text.split()
        budget = MAX_WORDS_PER_SECTION - total_words
        if budget <= 0:
            break
        snippet = " ".join(words[:budget])
        items.append({"label": cid, "text": snippet})
        total_words += min(len(words), budget)
    return items


def _get_section_tree(doc: CourseDocument, db: Session) -> Optional[List[Dict[str, Any]]]:
    """Return the section tree for a document, rebuilding from parents if needed."""
    if doc.section_tree_json:
        try:
            return json.loads(doc.section_tree_json)
        except json.JSONDecodeError:
            pass

    if doc.status != DocumentStatus.READY:
        return None

    from app.workers.pipeline import build_section_events_from_parents, build_section_tree

    parent_rows = (
        db.query(ChunkParent)
        .filter(ChunkParent.doc_id == doc.id)
        .order_by(ChunkParent.id)
        .all()
    )
    if not parent_rows:
        return None
    return build_section_tree(build_section_events_from_parents(parent_rows))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_run(
    run: GenerationRun,
    db: Session,
    status: str,
    stage: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    run.status = status
    if stage is not None:
        run.stage = stage
    if error is not None:
        run.error_message = error
    if status == GenerationRunStatus.RUNNING and run.started_at is None:
        run.started_at = _now_iso()
    if status in (GenerationRunStatus.DONE, GenerationRunStatus.ERROR):
        run.finished_at = _now_iso()
    db.commit()


# ---------------------------------------------------------------------------
# Map step
# ---------------------------------------------------------------------------

async def _map_section(
    section: Dict[str, Any], doc_id: str, db: Session
) -> List[Dict[str, Any]]:
    """Extract lesson candidates from one section via /generate_json."""
    chunk_ids = _collect_chunk_ids(section)
    context = _section_context(chunk_ids, db)
    if not context:
        return []

    prompt = (
        f'Section: "{section["title"]}" '
        f'(pages {section.get("page_start", "?")}–{section.get("page_end", "?")})\n\n'
        "Extract 1-3 self-contained lesson topics from this section. "
        "Each lesson must be directly supported by the source text."
    )

    result = await generate_json(
        prompt,
        _MAP_SCHEMA,
        context=context,
        system_prompt=_MAP_SYSTEM,
        generation_params={"temp": 0.15},
    )

    candidates = []
    for ls in result.get("lessons", []):
        candidates.append(
            {
                "title": ls["title"],
                "key_concepts": ls.get("key_concepts", []),
                "difficulty": ls.get("difficulty", "intermediate"),
                "source_chunk_ids": chunk_ids,
                "source_doc_id": doc_id,
                "section_title": section["title"],
            }
        )
    return candidates


async def _map_document(
    doc: CourseDocument, db: Session
) -> List[Dict[str, Any]]:
    """Run the map step for one document: iterate its top-level sections."""
    tree = _get_section_tree(doc, db)
    if not tree:
        logger.warning("outline map: no section tree for document %s — skipping", doc.id)
        return []

    all_candidates: List[Dict[str, Any]] = []
    for section in tree[:MAX_SECTIONS_PER_DOC]:
        try:
            candidates = await _map_section(section, doc.id, db)
            all_candidates.extend(candidates)
        except LlmDisabledError:
            raise
        except StructuredGenerationError as exc:
            logger.warning(
                "outline map: section '%s' failed (%s) — skipping",
                section.get("title"),
                exc,
            )
    return all_candidates


# ---------------------------------------------------------------------------
# Reduce step
# ---------------------------------------------------------------------------

async def _reduce(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group candidates into chapters with pedagogical ordering."""
    lines = []
    for i, c in enumerate(candidates):
        concepts = ", ".join(c["key_concepts"][:4]) or "—"
        doc_tag = f' [doc:{c["source_doc_id"][:8]}]' if c.get("source_doc_id") else ""
        lines.append(f"[{i}] {c['title']} ({c['difficulty']}) — {concepts}{doc_tag}")

    prompt = (
        "Group these lesson topics into a pedagogical course outline.\n\n"
        "Rules:\n"
        "- Order from foundational to advanced\n"
        "- 2–6 lessons per chapter, at most 12 chapters\n"
        "- Merge duplicate/near-duplicate topics (same concept from different documents) "
        "into a single lesson, listing all their indices in candidate_indices\n"
        "- Every index [0]–[{last}] must appear in exactly one lesson\n\n"
        "Topics:\n{topics}"
    ).format(last=len(candidates) - 1, topics="\n".join(lines))

    return await generate_json(
        prompt,
        _REDUCE_SCHEMA,
        system_prompt=_REDUCE_SYSTEM,
        generation_params={"temp": 0.2},
    )


# ---------------------------------------------------------------------------
# Persist step
# ---------------------------------------------------------------------------

def _persist_outline(
    course_id: str,
    outline: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    db: Session,
) -> None:
    """Delete existing draft chapters for this course, write new draft outline."""
    # Remove previous draft output (published chapters are untouched)
    draft_chapters = (
        db.query(Chapter)
        .filter(Chapter.course_id == course_id, Chapter.status == "draft")
        .all()
    )
    for ch in draft_chapters:
        for ls in db.query(Lesson).filter(Lesson.chapter_id == ch.id).all():
            db.delete(ls)
        db.delete(ch)
    db.flush()

    for ch_idx, ch_data in enumerate(outline.get("chapters", [])):
        chapter = Chapter(
            id=str(uuid.uuid4()),
            course_id=course_id,
            title=ch_data["title"],
            description=ch_data.get("description", ""),
            order_index=ch_idx,
            status="draft",
        )
        db.add(chapter)
        db.flush()

        for ls_idx, ls_data in enumerate(ch_data.get("lessons", [])):
            # Aggregate source chunk IDs from all referenced candidates.
            seen: set = set()
            source_refs: List[str] = []
            for cidx in ls_data.get("candidate_indices", []):
                if 0 <= cidx < len(candidates):
                    for cid in candidates[cidx].get("source_chunk_ids", []):
                        if cid not in seen:
                            seen.add(cid)
                            source_refs.append(cid)

            lesson = Lesson(
                id=str(uuid.uuid4()),
                chapter_id=chapter.id,
                title=ls_data["title"],
                description=ls_data.get("description", ""),
                content="",
                order_index=ls_idx,
                status="draft",
                source_refs_json=json.dumps(source_refs) if source_refs else None,
            )
            db.add(lesson)

    db.commit()


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def generate_outline(
    course_id: str,
    doc_ids: List[str],
    db: Session,
    run_id: str,
    options: Optional[Dict[str, Any]] = None,
) -> None:
    """Full map → reduce → persist pipeline for a course outline.

    Updates GenerationRun.status/stage at each step so the frontend can
    poll progress via GET /generation-runs/{run_id}.
    """
    run = db.query(GenerationRun).filter(GenerationRun.id == run_id).first()
    if run is None:
        raise ValueError(f"GenerationRun {run_id} not found")

    _update_run(run, db, GenerationRunStatus.RUNNING, "init")

    # ---- MAP ----
    all_candidates: List[Dict[str, Any]] = []
    docs = db.query(CourseDocument).filter(CourseDocument.id.in_(doc_ids)).all()

    for doc_idx, doc in enumerate(docs):
        stage = f"map_{doc_idx + 1}/{len(docs)}"
        _update_run(run, db, GenerationRunStatus.RUNNING, stage)
        try:
            candidates = await _map_document(doc, db)
            all_candidates.extend(candidates)
            logger.info(
                "outline map: doc %s → %d candidates", doc.id, len(candidates)
            )
        except LlmDisabledError as exc:
            _update_run(run, db, GenerationRunStatus.ERROR, error=f"LLM disabled: {exc}")
            return
        except Exception as exc:
            logger.exception("outline map: unexpected error for doc %s", doc.id)
            _update_run(run, db, GenerationRunStatus.ERROR, error=str(exc))
            return

    if not all_candidates:
        _update_run(
            run, db, GenerationRunStatus.ERROR,
            error="No candidates generated — documents may have no section structure",
        )
        return

    # Cap for reduce context budget
    candidates = all_candidates[:MAX_CANDIDATES_TOTAL]
    if len(all_candidates) > MAX_CANDIDATES_TOTAL:
        logger.info(
            "outline: capped candidates from %d to %d for reduce step",
            len(all_candidates), MAX_CANDIDATES_TOTAL,
        )

    # ---- REDUCE ----
    _update_run(run, db, GenerationRunStatus.RUNNING, "reduce")
    try:
        outline = await _reduce(candidates)
    except LlmDisabledError as exc:
        _update_run(run, db, GenerationRunStatus.ERROR, error=f"LLM disabled: {exc}")
        return
    except StructuredGenerationError as exc:
        _update_run(
            run, db, GenerationRunStatus.ERROR,
            error=f"Reduce failed after retries: {exc}",
        )
        return
    except Exception as exc:
        logger.exception("outline reduce: unexpected error")
        _update_run(run, db, GenerationRunStatus.ERROR, error=str(exc))
        return

    # ---- PERSIST ----
    _update_run(run, db, GenerationRunStatus.RUNNING, "persist")
    try:
        _persist_outline(course_id, outline, candidates, db)
    except Exception as exc:
        logger.exception("outline persist: DB write failed")
        _update_run(run, db, GenerationRunStatus.ERROR, error=str(exc))
        return

    _update_run(run, db, GenerationRunStatus.DONE, "done")
    n_chapters = len(outline.get("chapters", []))
    n_lessons = sum(len(ch.get("lessons", [])) for ch in outline.get("chapters", []))
    logger.info(
        "outline done: course=%s run=%s → %d chapters, %d lessons",
        course_id, run_id, n_chapters, n_lessons,
    )
