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
        "You are a Bitcoin education assistant for BitPolito Academy. "
        "Using ONLY the provided context, explain the concept clearly in 2–4 paragraphs. "
        "When you use information from a context passage, cite it as [ref_N] inline "
        "(e.g. 'Bitcoin mining [ref_1] is...'). "
        "If the answer is not in the context, say so explicitly."
    ),
    StudyAction.SUMMARIZE: (
        "You are a Bitcoin education assistant. "
        "Summarise the key points from the provided context as a numbered list of 5–8 concise bullet points. "
        "Cover the main ideas without adding information not present in the context."
    ),
    StudyAction.OPEN_QUESTIONS: (
        "Based on the provided context, generate exactly 5 open-ended questions "
        "that would prompt a student to think critically about the material. "
        "Output a numbered list of questions only — no answers."
    ),
    StudyAction.QUIZ: (
        "Based on the provided context, create 4 multiple-choice questions for self-assessment. "
        "For each question provide: the question, options A–D, and the correct answer. "
        "After the correct answer note the supporting reference as [ref_N]. "
        "Format each question as:\nQ: ...\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: [letter] [ref_N]"
    ),
    StudyAction.ORAL: (
        "You are simulating an oral exam on Bitcoin material. "
        "Generate 3 oral exam questions drawn from the provided context, "
        "followed by a concise model answer for each. "
        "Cite supporting context passages as [ref_N] in each model answer. "
        "Format each entry as:\nQ: ...\nModel answer: ..."
    ),
    StudyAction.DERIVE: (
        "You are a Bitcoin education assistant skilled in formal derivations. "
        "Using ONLY the provided context, present a step-by-step proof or derivation. "
        "Number each step, state the reasoning clearly, and cite sources as [ref_N]. "
        "If the full derivation is not supported by the context, say so explicitly."
    ),
    StudyAction.COMPARE: (
        "You are a Bitcoin education assistant. "
        "Using ONLY the provided context, produce a structured comparison of the requested concepts. "
        "Use a table or parallel-list format: left column = Concept A, right column = Concept B. "
        "Conclude with a 1-paragraph synthesis citing sources as [ref_N]."
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


def _chroma_evidence(question: str, course_id: str) -> List[EvidenceChunk]:
    """Query ChromaDB and return EvidenceChunk list (same shape as QVAC results)."""
    from app.services.chroma_retrieval import query_chroma  # lazy — avoids circular import
    return [
        EvidenceChunk(
            chunk_id=f"chroma_{s.get('doc_id', 'unk')}_{i}",
            text=s["snippet"],
            score=s["score"],
            anchor=CitationAnchor(
                doc_id=s["doc_id"],
                doc_name=s["label"],
                section=s["section"] or None,
                page=int(s["page"]) if s.get("page") else None,
                slide=int(s["slide"]) if s.get("slide") else None,
                chunk_id=f"chroma_{s.get('doc_id', 'unk')}_{i}",
                chunk_type="paragraph",
            ),
        )
        for i, s in enumerate(query_chroma(question, course_id, top_k=_TOP_K))
    ]


async def _retrieve(question: str, course_id: str, action: StudyAction) -> tuple[str, EvidencePack]:
    """Call QVAC /query, wrap response into a structured EvidencePack.

    Returns (raw_answer, pack).  raw_answer is the QVAC-generated string
    (used as fallback when the LLM is unavailable); pack is the canonical
    interface for generation and citation display.

    ChromaDB is queried as a fallback when QVAC returns zero chunks or fails.
    The retrieval query may be rewritten or HyDE-expanded before hitting QVAC;
    the original *question* is preserved for generation prompts and citations.
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
            logger.info(
                "QVAC returned 0 chunks for course '%s', trying ChromaDB fallback", course_id
            )
            candidates = _chroma_evidence(question, course_id)

        pack = evidence_pack_service.build_from_chunks(question, action.value, candidates)
        return raw_answer, pack

    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("QVAC retrieval failed (%s) — trying ChromaDB fallback", exc)
        candidates = _chroma_evidence(question, course_id)
        return "", evidence_pack_service.build_from_chunks(question, action.value, candidates)


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
        result = await _route(question, course_id, action, trace, rag_only=rag_only)
        trace.output_length = len(result.answer)
        return result
    except Exception as exc:
        trace.error = str(exc)
        raise
    finally:
        trace.duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info("dispatch_trace %s", json.dumps(dataclasses.asdict(trace)))
