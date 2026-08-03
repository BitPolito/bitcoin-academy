"""Lesson content generation service — Phase 3 of the course builder.

For each draft lesson:
  1. Load the source parent chunks anchored in lesson.source_refs_json.
  2. Call /generate_json to produce Markdown content + objectives + glossary + self_check.
  3. Run a groundedness judge (second LLM pass) that reads the content and sources,
     returning {faithful: bool, issues: [str]}.
  4. Persist content into Lesson.content; set status "published" or "needs_review".
  5. Generate a lesson quiz (3-4 MCQ) and persist to Quiz/Question/OptionChoice tables.

Caching: content_hash = SHA256(sorted source_refs + lesson.title + CONTENT_PROMPT_VERSION).
If the hash matches the stored one and content is non-empty, the lesson is skipped.

All LLM calls go through qvac_structured.generate_json.
"""
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models import (
    Chapter,
    ChunkParent,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
    Quiz,
    QuizScope,
)
from app.services import quiz_generation
from app.services.qvac_structured import (
    LlmDisabledError,
    StructuredGenerationError,
    generate_json,
)

logger = logging.getLogger(__name__)

CONTENT_PROMPT_VERSION = "v1"

# Max parent chunks to include in the generation context (token-budget guard).
MAX_CONTEXT_CHUNKS = 3

# ---------------------------------------------------------------------------
# JSON schemas
# ---------------------------------------------------------------------------

_CONTENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["content", "objectives", "glossary", "self_check"],
    "properties": {
        "content": {"type": "string"},
        "objectives": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 4,
        },
        "glossary": {
            "type": "array",
            "minItems": 0,
            "maxItems": 8,
            "items": {
                "type": "object",
                "required": ["term", "definition"],
                "properties": {
                    "term": {"type": "string"},
                    "definition": {"type": "string"},
                },
            },
        },
        "self_check": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 3,
        },
    },
}

_JUDGE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["faithful", "issues"],
    "properties": {
        "faithful": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
            "maxItems": 5,
        },
    },
}

# Quiz schema/system-prompt live in quiz_generation.py — shared with the
# study-page ad-hoc quiz endpoint (see quizzes_api.py). Keeping a single
# generator avoids the free-text-parsing/DB-persisted split that used to
# exist between the two call sites.

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_CONTENT_SYSTEM = (
    "You are an expert course author at BitPolito Academy. "
    "Write a complete, pedagogically structured lesson from the provided source material.\n"
    "RULES:\n"
    "1. Use ONLY the information in the provided source passages — never inject external knowledge.\n"
    "2. Use exact technical terminology from the document (UTXO, hashrate, proof-of-work, etc.).\n"
    "3. Cite every factual claim as [ref_N] where N is the 1-based passage index.\n"
    "4. Write 3–5 focused paragraphs: introduction → key concepts → synthesis.\n"
    "5. Do NOT open with generic phrases like 'In this lesson' or 'Based on the context'.\n"
    "6. Objectives: 2–4 specific, measurable learning outcomes (verb + concept).\n"
    "7. Glossary: include only technical terms that appear in the source.\n"
    "8. Self-check: 2–3 concise questions a student should answer after reading."
)

_JUDGE_SYSTEM = (
    "You are a groundedness judge for educational content. "
    "Your task is to verify that the lesson content is faithful to the provided source passages.\n"
    "RULES:\n"
    "1. Check whether claims marked [ref_N] are actually supported by the corresponding passage.\n"
    "2. Flag claims that contradict the source, exaggerate, or introduce information not in the text.\n"
    "3. Minor rephrasing of source text is acceptable if meaning is preserved.\n"
    "4. Return faithful=true only if ALL cited claims are directly supported."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_content_hash(lesson: Lesson) -> str:
    """SHA256 of (sorted source_refs + lesson.title + prompt_version)."""
    refs: List[str] = []
    if lesson.source_refs_json:
        try:
            refs = json.loads(lesson.source_refs_json)
        except json.JSONDecodeError:
            pass
    payload = json.dumps(sorted(refs)) + lesson.title + CONTENT_PROMPT_VERSION
    return hashlib.sha256(payload.encode()).hexdigest()


_ISSUES_COMMENT_RE = re.compile(r"\n\n<!-- groundedness_issues:\n(.*?)\n-->", re.DOTALL)


def extract_issues(content: str) -> Tuple[str, List[str]]:
    """Split lesson.content into (clean_markdown, groundedness_issues).

    process_lesson() embeds judge issues as an HTML comment so nothing is
    lost, but a comment isn't fit for a student-facing response — the review
    UI (content_api.py) needs the issues as a structured list and the content
    without the comment.
    """
    match = _ISSUES_COMMENT_RE.search(content)
    if not match:
        return content, []
    issues = [
        line[2:].strip() for line in match.group(1).splitlines() if line.strip().startswith("-")
    ]
    clean = content[: match.start()] + content[match.end():]
    return clean, issues


def _load_context(lesson: Lesson, db: Session) -> Tuple[List[str], List[Dict[str, str]]]:
    """Return (source_ref_ids, context_items) for the lesson.

    Context items follow the /generate convention: {"label": str, "text": str}.
    Capped at MAX_CONTEXT_CHUNKS to stay within the 8K token budget.
    """
    if not lesson.source_refs_json:
        return [], []
    try:
        chunk_ids: List[str] = json.loads(lesson.source_refs_json)
    except json.JSONDecodeError:
        return [], []

    chunk_ids = chunk_ids[:MAX_CONTEXT_CHUNKS]
    rows = {
        r.id: r
        for r in db.query(ChunkParent).filter(ChunkParent.id.in_(chunk_ids)).all()
    }
    context_items: List[Dict[str, str]] = []
    used_ids: List[str] = []
    for cid in chunk_ids:
        if cid in rows:
            context_items.append({"label": cid, "text": rows[cid].text})
            used_ids.append(cid)
    return used_ids, context_items


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _update_run(run: GenerationRun, db: Session, status: str, stage: Optional[str] = None, error: Optional[str] = None) -> None:
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
# Content generation
# ---------------------------------------------------------------------------

async def _generate_content(
    lesson: Lesson, context_items: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Call /generate_json to produce lesson content + metadata."""
    prompt = (
        f'Write a complete lesson titled: "{lesson.title}".\n'
        f"Description: {lesson.description or lesson.title}\n\n"
        "Produce: lesson content (Markdown with [ref_N] citations), "
        "learning objectives, glossary of key terms, and self-check questions."
    )
    return await generate_json(
        prompt,
        _CONTENT_SCHEMA,
        context=context_items,
        system_prompt=_CONTENT_SYSTEM,
        generation_params={"temp": 0.2},
        task_type="content_gen",
    )


# ---------------------------------------------------------------------------
# Groundedness judge
# ---------------------------------------------------------------------------

async def _judge_groundedness(
    content: str, context_items: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Check that the lesson content is faithful to its source passages."""
    # Truncate content for judge to save tokens (first 800 words)
    content_preview = " ".join(content.split()[:800])
    prompt = (
        "Review this lesson content for faithfulness to the provided source passages.\n\n"
        f"LESSON CONTENT:\n{content_preview}\n\n"
        "Check: are all [ref_N] claims directly supported by the corresponding passages? "
        "List any unsupported or exaggerated claims as issues."
    )
    # Use abbreviated source for judge (first 200 words per chunk)
    judge_context = [
        {"label": item["label"], "text": " ".join(item["text"].split()[:200])}
        for item in context_items
    ]
    return await generate_json(
        prompt,
        _JUDGE_SCHEMA,
        context=judge_context,
        system_prompt=_JUDGE_SYSTEM,
        generation_params={"temp": 0.1},
        task_type="judge",
    )


# ---------------------------------------------------------------------------
# Quiz generation
# ---------------------------------------------------------------------------

async def _generate_quiz_data(
    lesson: Lesson, context_items: List[Dict[str, str]]
) -> Optional[Dict[str, Any]]:
    """Call /generate_json (via quiz_generation.py) to produce MCQ quiz data."""
    return await quiz_generation.generate_quiz_questions(lesson.title, context_items)


def _persist_quiz(lesson: Lesson, quiz_data: Dict[str, Any], db: Session) -> Optional[str]:
    """Write Quiz / Question / OptionChoice rows linked to the lesson."""
    quiz = quiz_generation.persist_quiz(
        db,
        quiz_data.get("questions", []),
        scope=QuizScope.LESSON,
        title=f"Quiz: {lesson.title[:80]}",
        lesson_id=lesson.id,
    )
    return quiz.id if quiz else None


# ---------------------------------------------------------------------------
# Single-lesson orchestrator
# ---------------------------------------------------------------------------

async def process_lesson(lesson_id: str, db: Session) -> str:
    """Generate content, run groundedness judge, generate quiz for one lesson.

    Returns the final lesson status: "published", "needs_review", or "skipped".
    The lesson is skipped if:
      - it has no source refs (can't generate grounded content)
      - its content_hash is unchanged (already generated from the same sources)
    """
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if lesson is None:
        raise ValueError(f"Lesson {lesson_id} not found")

    # ---- Cache check ----
    current_hash = compute_content_hash(lesson)
    if lesson.content_hash == current_hash and lesson.content:
        logger.info("lesson %s: cache hit — skipping", lesson_id)
        return "skipped"

    # ---- Load context ----
    used_ids, context_items = _load_context(lesson, db)
    if not context_items:
        logger.warning("lesson %s: no source refs — marking needs_review", lesson_id)
        lesson.status = "needs_review"
        db.commit()
        return "needs_review"

    # ---- Content generation ----
    try:
        result = await _generate_content(lesson, context_items)
    except LlmDisabledError:
        raise
    except StructuredGenerationError as exc:
        logger.warning("lesson %s: content generation failed: %s", lesson_id, exc)
        lesson.status = "needs_review"
        db.commit()
        return "needs_review"

    content = result.get("content", "")
    objectives = result.get("objectives", [])
    glossary = result.get("glossary", [])
    self_check = result.get("self_check", [])

    if not content.strip():
        lesson.status = "needs_review"
        db.commit()
        return "needs_review"

    # ---- Groundedness judge ----
    try:
        verdict = await _judge_groundedness(content, context_items)
        faithful = verdict.get("faithful", True)
        issues = verdict.get("issues", [])
    except (LlmDisabledError, StructuredGenerationError) as exc:
        logger.warning(
            "lesson %s: judge failed (%s) — assuming faithful", lesson_id, exc
        )
        faithful = True
        issues = []

    final_status = "published" if faithful else "needs_review"

    # ---- Persist content ----
    # Append objectives, glossary, self_check as Markdown sections after the main content.
    full_content = content

    if objectives:
        obj_lines = "\n".join(f"- {o}" for o in objectives)
        full_content += f"\n\n## Learning Objectives\n{obj_lines}"

    if glossary:
        gloss_lines = "\n".join(f"**{g['term']}**: {g['definition']}" for g in glossary)
        full_content += f"\n\n## Glossary\n{gloss_lines}"

    if self_check:
        sc_lines = "\n".join(f"{i+1}. {q}" for i, q in enumerate(self_check))
        full_content += f"\n\n## Self-Check\n{sc_lines}"

    if issues:
        issues_lines = "\n".join(f"- {iss}" for iss in issues)
        full_content += f"\n\n<!-- groundedness_issues:\n{issues_lines}\n-->"

    lesson.content = full_content
    lesson.content_hash = current_hash
    lesson.status = final_status
    db.commit()

    # ---- Quiz ----
    try:
        quiz_data = await _generate_quiz_data(lesson, context_items)
        if quiz_data:
            _persist_quiz(lesson, quiz_data, db)
    except LlmDisabledError:
        raise
    except Exception as exc:
        logger.warning("lesson %s: quiz generation failed: %s", lesson_id, exc)

    logger.info(
        "lesson %s (%s): status=%s faithful=%s",
        lesson_id,
        lesson.title[:40],
        final_status,
        faithful,
    )
    return final_status


# ---------------------------------------------------------------------------
# Course-level orchestrator
# ---------------------------------------------------------------------------

async def generate_course_content(
    course_id: str,
    db: Session,
    run_id: str,
    lesson_ids: Optional[List[str]] = None,
) -> None:
    """Process draft lessons for a course sequentially.

    If *lesson_ids* is given, only those lessons are processed and each has
    its content_hash cleared first — this is the "regenerate this lesson"
    path from the review UI, and must bypass the cache-hit skip in
    process_lesson() or a re-request would be a silent no-op. Without
    lesson_ids, all draft lessons in the course are processed (the initial
    generation path from POST /content/generate).

    Updates GenerationRun status/stage at each step for frontend polling.
    """
    run = db.query(GenerationRun).filter(GenerationRun.id == run_id).first()
    if run is None:
        raise ValueError(f"GenerationRun {run_id} not found")

    _update_run(run, db, GenerationRunStatus.RUNNING, "init")

    query = (
        db.query(Lesson)
        .join(Chapter, Lesson.chapter_id == Chapter.id)
        .filter(Chapter.course_id == course_id)
        .order_by(Chapter.order_index, Lesson.order_index)
    )
    if lesson_ids:
        lessons = query.filter(Lesson.id.in_(lesson_ids)).all()
        for lesson in lessons:
            lesson.content_hash = None
        db.commit()
    else:
        lessons = query.filter(Chapter.status == "draft").all()

    if not lessons:
        _update_run(run, db, GenerationRunStatus.ERROR, error="No draft lessons found for this course")
        return

    total = len(lessons)
    published = 0
    needs_review = 0
    skipped = 0

    for idx, lesson in enumerate(lessons):
        _update_run(run, db, GenerationRunStatus.RUNNING, f"lesson_{idx + 1}/{total}")
        try:
            result = await process_lesson(lesson.id, db)
            if result == "published":
                published += 1
            elif result == "needs_review":
                needs_review += 1
            else:
                skipped += 1
        except LlmDisabledError as exc:
            _update_run(run, db, GenerationRunStatus.ERROR, error=f"LLM disabled: {exc}")
            return
        except Exception as exc:
            logger.exception("lesson %s: unexpected error", lesson.id)
            _update_run(run, db, GenerationRunStatus.ERROR, error=str(exc))
            return

    _update_run(run, db, GenerationRunStatus.DONE, "done")
    logger.info(
        "content generation done: course=%s published=%d needs_review=%d skipped=%d",
        course_id, published, needs_review, skipped,
    )


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------

def publish_course(course_id: str, db: Session) -> Dict[str, int]:
    """Mark chapters and lessons as published.

    Only chapters where every lesson is 'published' (not needs_review) are
    published. Chapters with any needs_review lesson remain draft.

    Returns counts: {published_chapters, published_lessons, skipped_chapters}.
    """
    chapters = (
        db.query(Chapter)
        .filter(Chapter.course_id == course_id, Chapter.status == "draft")
        .all()
    )

    published_chapters = 0
    published_lessons = 0
    skipped_chapters = 0

    for chapter in chapters:
        lessons = db.query(Lesson).filter(Lesson.chapter_id == chapter.id).all()
        if not lessons:
            skipped_chapters += 1
            continue

        publishable = [ls for ls in lessons if ls.status == "published"]
        blocking = [ls for ls in lessons if ls.status == "needs_review"]

        if blocking:
            skipped_chapters += 1
            continue

        if publishable:
            for ls in publishable:
                ls.status = "published"
                published_lessons += 1
            chapter.status = "published"
            published_chapters += 1

    db.commit()
    return {
        "published_chapters": published_chapters,
        "published_lessons": published_lessons,
        "skipped_chapters": skipped_chapters,
    }
