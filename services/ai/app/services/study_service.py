"""Study service — action-aware RAG dispatch with structured tracing.

Retrieval and generation are both delegated to the local QVAC Node.js service
(via @qvac/sdk).  No external LLM API is used.

Workspace = course_id, matching the convention in pipeline.py and chat_service.py.
"""
import dataclasses
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk, EvidencePack
from app.schemas.study_schemas import (
    STUDY_ACTION_REGISTRY,
    StudyAction,
)
from app.services import evidence_pack_service

logger = logging.getLogger(__name__)

_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

_qvac_client = httpx.AsyncClient(
    base_url=_QVAC_SERVICE_URL,
    timeout=httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0),
)


# ---------------------------------------------------------------------------
# System prompts per action
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS = {
    StudyAction.EXPLAIN: (
        "You are an expert Bitcoin tutor at BitPolito Academy, helping university students"
        " understand Bitcoin and its underlying technology with rigour and precision.\n"
        "RULES:\n"
        "1. Use ONLY the information in the provided context passages — never inject external"
        " knowledge not supported by the text.\n"
        "2. Use the exact technical terminology present in the document: UTXO, block subsidy,"
        " hashrate, timechain, proof-of-work, mempool, scriptPubKey, etc. Do not paraphrase"
        " with imprecise equivalents.\n"
        "3. Cite every factual claim with its source passage as [ref_N] inline"
        " (e.g. 'The block subsidy halves every 210 000 blocks [ref_2].').\n"
        "4. If a topic is not covered in the context, state explicitly:"
        " \"This specific point is not covered in the provided material.\"\n"
        "5. Write in a pedagogical tone: clear, structured, building from fundamentals"
        " to details. Aim for 2–4 focused paragraphs — expand only when the topic genuinely"
        " requires it.\n"
        "6. Do NOT open with generic phrases like 'Based on the provided context…'."
        " Start directly with the explanation."
    ),
    StudyAction.SUMMARIZE: (
        "You are an expert Bitcoin tutor at BitPolito Academy.\n"
        "RULES:\n"
        "1. Summarise the provided context as 5–8 concise numbered bullet points.\n"
        "2. Preserve all key technical definitions and figures exactly as they appear"
        " in the source (use exact terms: UTXO, hashrate, block subsidy, etc.).\n"
        "3. Cover main ideas in order of importance; do not add information absent"
        " from the context.\n"
        "4. After each bullet, note the supporting passage as [ref_N].\n"
        "5. End with a one-sentence synthesis that connects the key points."
    ),
    StudyAction.OPEN_QUESTIONS: (
        "You are an expert Bitcoin tutor at BitPolito Academy.\n"
        "Generate exactly 5 open-ended study questions based ONLY on the provided context.\n"
        "RULES:\n"
        "1. Each question must require conceptual reasoning, not simple recall"
        " (e.g. 'Why does X imply Y?' rather than 'What is X?').\n"
        "2. Use exact Bitcoin terminology from the document.\n"
        "3. Order questions from foundational to advanced.\n"
        "4. Output a numbered list of questions only — no answers, no preamble."
    ),
    StudyAction.QUIZ: (
        "You are an expert Bitcoin tutor at BitPolito Academy.\n"
        "Create exactly 4 multiple-choice questions based ONLY on the provided context.\n"
        "RULES:\n"
        "1. Each question must test understanding, not trivia. Use precise Bitcoin"
        " terminology from the document.\n"
        "2. Plausible distractors only — wrong options must be conceptually close, not absurd.\n"
        "3. The correct answer must be directly supported by at least one context passage.\n"
        "4. Cite the supporting passage inline after the answer as [ref_N].\n"
        "5. Format every question exactly as:\n"
        "Q: <question text>\n"
        "A) <option>\nB) <option>\nC) <option>\nD) <option>\n"
        "Answer: <letter>) <brief explanation> [ref_N]"
    ),
    StudyAction.ORAL: (
        "You are simulating a university oral exam on Bitcoin at BitPolito Academy.\n"
        "Generate exactly 3 oral exam questions drawn from the provided context.\n"
        "RULES:\n"
        "1. Order questions from most conceptual to most technical.\n"
        "2. For each question, provide a model answer that a well-prepared student should give,"
        " citing supporting passages as [ref_N].\n"
        "3. After the model answer, add one follow-up question that a professor would ask"
        " to probe deeper understanding.\n"
        "4. Use exact Bitcoin terminology from the document.\n"
        "5. Format each entry as:\n"
        "Q<n>: <question>\n"
        "Model answer: <answer with [ref_N] citations>\n"
        "Follow-up: <deeper question>"
    ),
    StudyAction.DERIVE: (
        "You are an expert Bitcoin tutor skilled in formal derivations, at BitPolito Academy.\n"
        "Using ONLY the provided context, present a step-by-step proof or derivation.\n"
        "RULES:\n"
        "1. Number each step; state the reasoning and the rule applied at each step.\n"
        "2. Cite the context passage that justifies each step as [ref_N].\n"
        "3. Use exact mathematical notation and Bitcoin-specific terms from the document.\n"
        "4. If the full derivation is not supported by the context, state explicitly which"
        " steps cannot be completed from the provided material."
    ),
    StudyAction.COMPARE: (
        "You are an expert Bitcoin tutor at BitPolito Academy.\n"
        "Using ONLY the provided context, produce a structured comparison of the requested concepts.\n"
        "RULES:\n"
        "1. Use a parallel-list or table format with clearly labelled columns for each concept.\n"
        "2. Compare on the same dimensions (e.g. security model, scalability, consensus"
        " mechanism) — do not mix apples and oranges.\n"
        "3. Use exact technical terms from the document; cite sources as [ref_N].\n"
        "4. Conclude with a 1-paragraph synthesis that draws out the most important"
        " trade-off or distinction, citing [ref_N]."
    ),
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class DispatchTrace:
    request_id: str
    course_id: str
    action: str
    query_length: int
    retrieval_ran: bool
    chunks_found: int
    generation_ran: bool
    fallback_used: bool
    output_length: int
    duration_ms: float
    error: Optional[str]


@dataclass
class SourceChunk:
    snippet: str
    score: float
    label: str = ""
    page: int = 0
    slide: int = 0
    section: str = ""
    doc_id: str = ""


@dataclass
class DispatchResult:
    answer: str
    citations: List[SourceChunk] = field(default_factory=list)
    retrieval_used: bool = False
    # Structured retrieval context — available for debug/inspection, not exposed in HTTP response.
    evidence_pack: Optional[EvidencePack] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _empty_pack(query: str, action: StudyAction) -> EvidencePack:
    return EvidencePack(
        query=query, action=action.value,
        chunks=[], total_candidates=0, ordering=[], deduped_passages=[],
    )


_REF_PATTERN = re.compile(r'\[ref_(\d+)\]', re.IGNORECASE)


def _parse_citations(text: str, pack: EvidencePack) -> List[SourceChunk]:
    """Extract [ref_N] markers from generated text and return referenced chunks.

    The LLM is instructed to emit [ref_N] in-line; this function parses those
    markers and returns SourceChunks for only the cited evidence, preserving
    citation order (first appearance wins for dedup).

    Falls back to all pack chunks when no [ref_N] markers are found — this
    happens when the LLM ignores the citation instruction or when the action
    does not require source grounding.
    """
    cited_indices: list[int] = []
    seen: set[int] = set()
    for m in _REF_PATTERN.finditer(text):
        idx = int(m.group(1)) - 1  # [ref_N] is 1-based
        if 0 <= idx < len(pack.chunks) and idx not in seen:
            cited_indices.append(idx)
            seen.add(idx)

    if not cited_indices:
        # No markers found — return all pack chunks as citations (backward-compat)
        source_chunks = pack.chunks
    else:
        source_chunks = [pack.chunks[i] for i in cited_indices]

    return [
        SourceChunk(
            snippet=c.text,
            score=c.score,
            label=c.anchor.doc_name,
            page=c.anchor.page or 0,
            slide=c.anchor.slide or 0,
            section=c.anchor.section or "",
            doc_id=c.anchor.doc_id,
        )
        for c in source_chunks
    ]


async def _retrieve(question: str, course_id: str, action: StudyAction) -> tuple[str, EvidencePack]:
    """Call QVAC /query, wrap response into a structured EvidencePack.

    Returns (raw_answer, pack).  raw_answer is the QVAC-generated string
    (used as fallback when the LLM is unavailable); pack is the canonical
    interface for generation and citation display.

    The retrieval query may be rewritten or HyDE-expanded before hitting QVAC;
    the original *question* is preserved for generation prompts and citations.
    Returns an empty pack when QVAC is unavailable.
    """
    from app.rag.query_rewriter import expand_query
    retrieval_query = await expand_query(question)

    try:
        resp = await _qvac_client.post(
            "/query",
            json={"question": retrieval_query, "workspace": course_id, "topK": _TOP_K},
        )
        resp.raise_for_status()
        data = resp.json()
        raw_answer: str = data.get("answer", "")

        candidates: List[EvidenceChunk] = [
            EvidenceChunk(
                chunk_id=s.get("chunk_id") or f"qvac_{s.get('doc_id', 'unk')}_{i}",
                text=s.get("snippet", ""),
                score=float(s.get("score", 0.0)),
                anchor=CitationAnchor(
                    doc_id=str(s.get("doc_id", "")),
                    doc_name=str(s.get("label", "")),
                    section=s.get("section") or None,
                    page=int(s["page"]) if s.get("page") else None,
                    slide=int(s["slide"]) if s.get("slide") else None,
                    chunk_id=s.get("chunk_id") or f"qvac_{s.get('doc_id', 'unk')}_{i}",
                    chunk_type="paragraph",
                ),
            )
            for i, s in enumerate(data.get("sources", []))
        ]

        if not candidates:
            logger.info("QVAC returned 0 chunks for course '%s'", course_id)

        pack = evidence_pack_service.build_from_chunks(question, action.value, candidates)
        return raw_answer, pack

    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("QVAC retrieval failed (%s) — returning empty pack", exc)
        return "", _empty_pack(question, action)


_AND_SPLIT = re.compile(
    r'\b(?:vs\.?|versus|compare(?:d\s+to)?|differ(?:ence)?(?:\s+between)?|between\s+.+\s+and)\b',
    re.IGNORECASE,
)


async def _retrieve_multi(
    question: str, course_id: str, action: StudyAction
) -> tuple[str, EvidencePack]:
    """Parallel two-hop retrieval for COMPARE/DERIVE actions with multi-entity queries.

    Splits the question on comparison keywords, runs one sub-retrieval per entity,
    merges by chunk_id, and builds a unified EvidencePack covering both concepts.
    Falls back to standard single retrieval when fewer than two parts are detected
    or for any other action type.
    """
    import asyncio  # noqa: PLC0415

    if action not in (StudyAction.COMPARE, StudyAction.DERIVE):
        return await _retrieve(question, course_id, action)

    parts = [p.strip() for p in _AND_SPLIT.split(question) if len(p.strip()) >= 3]
    if len(parts) < 2:
        return await _retrieve(question, course_id, action)

    results = await asyncio.gather(
        *[_retrieve(p, course_id, action) for p in parts[:2]],
        return_exceptions=True,
    )

    merged: dict[str, EvidenceChunk] = {}
    raw_answers: list[str] = []
    for res in results:
        if isinstance(res, BaseException):
            logger.warning("Two-hop sub-retrieval failed: %s", res)
            continue
        raw_ans, pack = res  # type: ignore[misc]
        if raw_ans:
            raw_answers.append(raw_ans)
        for chunk in pack.chunks:
            if chunk.chunk_id not in merged:
                merged[chunk.chunk_id] = chunk

    if not merged:
        logger.info("Two-hop produced no chunks — falling back to single retrieval")
        return await _retrieve(question, course_id, action)

    logger.debug(
        "Two-hop retrieval for '%s': %d unique chunks from %d sub-queries",
        action.value, len(merged), len(parts[:2]),
    )
    combined = evidence_pack_service.build_from_chunks(
        question, action.value, list(merged.values())
    )
    return raw_answers[0] if raw_answers else "", combined


async def _generate(action: StudyAction, question: str, context: str) -> Optional[str]:
    """Call QVAC /generate with the action-specific system prompt (local LLM via QVAC SDK).

    The pre-formatted context string (with [ref_N] markers) is passed as a single
    context block so the LLM sees the citation anchors embedded by evidence_pack_service.

    Returns None when QVAC is unreachable or returns an empty answer, allowing
    the caller to fall back to the raw retrieval context.
    """
    system_prompt = _SYSTEM_PROMPTS.get(action, "")
    try:
        resp = await _qvac_client.post(
            "/generate",
            json={
                "question": question,
                "context": [{"label": "", "text": context}],
                "systemPrompt": system_prompt,
            },
        )
        resp.raise_for_status()
        answer: str = resp.json().get("answer", "")
        return answer or None
    except httpx.HTTPError as exc:
        logger.warning("QVAC /generate failed for action '%s': %s", action.value, exc)
        return None


async def _route(
    question: str,
    course_id: str,
    action: StudyAction,
    trace: DispatchTrace,
    rag_only: bool = False,
) -> DispatchResult:
    meta = STUDY_ACTION_REGISTRY[action]

    # Step 1 — Retrieval → EvidencePack
    raw_answer = ""
    pack = _empty_pack(question, action)

    if meta.retrieval_required:
        trace.retrieval_ran = True
        raw_answer, pack = await _retrieve_multi(question, course_id, action)
        trace.chunks_found = len(pack.chunks)

    # Step 2 — skip generation when the action doesn't need it, OR when rag_only is active.
    # rag_only lets callers force raw-retrieval mode for every action (e.g. no LLM key configured).
    if not meta.generation_required or rag_only:
        all_sources: List[SourceChunk] = [
            SourceChunk(
                snippet=c.text,
                score=c.score,
                label=c.anchor.doc_name,
                page=c.anchor.page or 0,
                slide=c.anchor.slide or 0,
                section=c.anchor.section or "",
                doc_id=c.anchor.doc_id,
            )
            for c in pack.chunks
        ]
        answer = pack.context_block() or raw_answer or "No relevant content found."
        return DispatchResult(
            answer=answer,
            citations=all_sources,
            retrieval_used=bool(all_sources),
            evidence_pack=pack,
        )

    # Step 3 — Generation using the pack's context block
    generated = await _generate(action, question, pack.context_block())
    if generated is not None:
        trace.generation_ran = True
        answer = generated
        # Parse [ref_N] markers to surface only the cited chunks as citations.
        sources = _parse_citations(generated, pack)
    else:
        trace.fallback_used = True
        answer = raw_answer or "No relevant content found."
        sources = [
            SourceChunk(
                snippet=c.text,
                score=c.score,
                label=c.anchor.doc_name,
                page=c.anchor.page or 0,
                slide=c.anchor.slide or 0,
                section=c.anchor.section or "",
                doc_id=c.anchor.doc_id,
            )
            for c in pack.chunks
        ]

    return DispatchResult(answer=answer, citations=sources, retrieval_used=bool(sources), evidence_pack=pack)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def dispatch(
    question: str,
    course_id: str,
    action: StudyAction,
    rag_only: bool = False,
) -> DispatchResult:
    """Route a student query through retrieval and optional generation.

    Emits a single structured JSON log line at INFO level on every call,
    including when an exception is raised.  The request_id is not exposed
    in the HTTP response — it lives only in the log.
    """
    if len(question.strip()) < 5:
        raise ValueError("Query too short — must be at least 5 characters")

    request_id = str(uuid.uuid4())
    started_at = time.perf_counter()

    trace = DispatchTrace(
        request_id=request_id,
        course_id=course_id,
        action=action.value,
        query_length=len(question),
        retrieval_ran=False,
        chunks_found=0,
        generation_ran=False,
        fallback_used=False,
        output_length=0,
        duration_ms=0.0,
        error=None,
    )

    try:
        # Semantic cache — include action in key so QUIZ and EXPLAIN don't collide.
        # Skip cache when rag_only changes the output format.
        cache_key = f"{question} [action:{action.value}]" + (" [rag_only]" if rag_only else "")
        from app.services.cache_service import get_cached, set_cached  # noqa: PLC0415
        cached = get_cached(cache_key, course_id)
        if cached is not None:
            return DispatchResult(
                answer=cached["answer"],
                citations=[SourceChunk(**c) for c in cached.get("citations", [])],
                retrieval_used=cached.get("retrieval_used", True),
            )

        result = await _route(question, course_id, action, trace, rag_only=rag_only)
        trace.output_length = len(result.answer)

        set_cached(cache_key, course_id, {
            "answer": result.answer,
            "citations": [dataclasses.asdict(c) for c in result.citations],
            "retrieval_used": result.retrieval_used,
        })
        return result
    except Exception as exc:
        trace.error = str(exc)
        raise
    finally:
        trace.duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info("dispatch_trace %s", json.dumps(dataclasses.asdict(trace)))
