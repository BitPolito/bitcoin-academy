"""Study service — action-aware RAG dispatch with structured tracing.

Retrieval is delegated to the QVAC Node.js service; generation uses
langchain-openai when OPENAI_API_KEY is set, with graceful fallback to the
QVAC raw answer when the key is absent or the call fails.

Workspace = course_id, matching the convention in pipeline.py and chat_service.py.
"""
import dataclasses
import json
import logging
import os
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
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
_LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

_qvac_client = httpx.AsyncClient(
    base_url=_QVAC_SERVICE_URL,
    timeout=httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0),
)

_LANGCHAIN_AVAILABLE = False
_ChatOpenAI = None
_SystemMessage = None
_HumanMessage = None

try:
    from langchain_openai import ChatOpenAI as _ChatOpenAI          # type: ignore[assignment]
    from langchain_core.messages import (                            # type: ignore[assignment]
        HumanMessage as _HumanMessage,
        SystemMessage as _SystemMessage,
    )
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# System prompts per action
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS = {
    StudyAction.EXPLAIN: (
        "You are a Bitcoin education assistant for BitPolito Academy. "
        "Using ONLY the provided context, explain the concept clearly in 2–4 paragraphs. "
        "Cite sources where relevant (e.g. 'p. 7', 'Slide 5'). "
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
        "Format each question as:\nQ: ...\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: [letter]"
    ),
    StudyAction.ORAL: (
        "You are simulating an oral exam on Bitcoin material. "
        "Generate 3 oral exam questions drawn from the provided context, "
        "followed by a concise model answer for each. "
        "Format each entry as:\nQ: ...\nModel answer: ..."
    ),
    StudyAction.DERIVE: (
        "You are a Bitcoin education assistant skilled in formal derivations. "
        "Using ONLY the provided context, present a step-by-step proof or derivation. "
        "Number each step, state the reasoning clearly, and cite sources (e.g. 'p.7', 'Slide 5'). "
        "If the full derivation is not supported by the context, say so explicitly."
    ),
    StudyAction.COMPARE: (
        "You are a Bitcoin education assistant. "
        "Using ONLY the provided context, produce a structured comparison of the requested concepts or definitions. "
        "Use a table or parallel-list format: left column = Concept A, right column = Concept B. "
        "Conclude with a 1-paragraph synthesis of key differences and similarities, citing sources."
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
    """
    try:
        resp = await _qvac_client.post(
            "/query",
            json={"question": question, "workspace": course_id, "topK": _TOP_K},
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


async def _generate(action: StudyAction, question: str, context: str) -> Optional[str]:
    """Call OpenAI via langchain-openai with the action-specific system prompt.

    Returns None when langchain-openai is unavailable or OPENAI_API_KEY is unset,
    allowing the caller to fall back to the raw QVAC answer.
    """
    if not _LANGCHAIN_AVAILABLE or not _OPENAI_API_KEY:
        return None

    system_prompt = _SYSTEM_PROMPTS[action]
    user_content = (
        f"Context:\n{context}\n\nQuestion: {question}"
        if context
        else f"Question: {question}"
    )

    try:
        llm = _ChatOpenAI(model="gpt-4o-mini", temperature=0.3, timeout=_LLM_TIMEOUT)  # type: ignore[call-arg]
        response = await llm.ainvoke(
            [_SystemMessage(content=system_prompt), _HumanMessage(content=user_content)]  # type: ignore[call-arg]
        )
        content = response.content
        return content if isinstance(content, str) else str(content)
    except Exception as exc:
        logger.warning("LLM generation failed for action '%s': %s", action.value, exc)
        return None


async def _route(
    question: str,
    course_id: str,
    action: StudyAction,
    trace: DispatchTrace,
) -> DispatchResult:
    meta = STUDY_ACTION_REGISTRY[action]

    # Step 1 — Retrieval → EvidencePack
    raw_answer = ""
    pack = _empty_pack(question, action)

    if meta.retrieval_required:
        trace.retrieval_ran = True
        raw_answer, pack = await _retrieve(question, course_id, action)
        trace.chunks_found = len(pack.chunks)

    # Derive SourceChunk list from pack (preserves existing DispatchResult/API shape)
    sources: List[SourceChunk] = [
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

    # Step 2 — retrieve-only shortcut: return deduplicated passages directly
    if not meta.generation_required:
        answer = pack.context_block() or raw_answer or "No relevant content found."
        return DispatchResult(
            answer=answer,
            citations=sources,
            retrieval_used=bool(sources),
            evidence_pack=pack,
        )

    # Step 3 — Generation using the pack's context block
    generated = await _generate(action, question, pack.context_block())
    if generated is not None:
        trace.generation_ran = True
        answer = generated
    else:
        trace.fallback_used = True
        answer = raw_answer or "No relevant content found."

    return DispatchResult(answer=answer, citations=sources, retrieval_used=bool(sources), evidence_pack=pack)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def dispatch(
    question: str,
    course_id: str,
    action: StudyAction,
) -> DispatchResult:
    """Route a student query through retrieval and optional generation.

    Emits a single structured JSON log line at INFO level on every call,
    including when an exception is raised.  The request_id is not exposed
    in the HTTP response — it lives only in the log.
    """
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
        result = await _route(question, course_id, action, trace)
        trace.output_length = len(result.answer)
        return result
    except Exception as exc:
        trace.error = str(exc)
        raise
    finally:
        trace.duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info("dispatch_trace %s", json.dumps(dataclasses.asdict(trace)))
