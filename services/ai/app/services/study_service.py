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

from app.schemas.study_schemas import (
    STUDY_ACTION_REGISTRY,
    StudyAction,
)

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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _retrieve(question: str, course_id: str) -> tuple[str, List[SourceChunk]]:
    """Call QVAC /query and return (raw_answer, sources)."""
    try:
        resp = await _qvac_client.post(
            "/query",
            json={"question": question, "workspace": course_id, "topK": _TOP_K},
        )
        resp.raise_for_status()
        data = resp.json()
        raw_answer = data.get("answer", "")
        sources = [
            SourceChunk(
                snippet=s.get("snippet", ""),
                score=s.get("score", 0.0),
                label=s.get("label", ""),
                page=s.get("page", 0),
                slide=s.get("slide", 0),
                section=s.get("section", ""),
                doc_id=s.get("doc_id", ""),
            )
            for s in data.get("sources", [])
        ]
        return raw_answer, sources
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("QVAC retrieval failed: %s", exc)
        return "", []


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

    # Step 1 — Retrieval
    raw_answer = ""
    sources: List[SourceChunk] = []
    context = ""

    if meta.retrieval_required:
        trace.retrieval_ran = True
        raw_answer, sources = await _retrieve(question, course_id)
        trace.chunks_found = len(sources)
        context = "\n\n---\n\n".join(
            f"[{i + 1}] {s.snippet}" for i, s in enumerate(sources)
        )

    # Step 2 — retrieve-only shortcut
    if not meta.generation_required:
        return DispatchResult(
            answer=raw_answer or "No relevant content found.",
            citations=sources,
            retrieval_used=bool(sources),
        )

    # Step 3 — Generation
    generated = await _generate(action, question, context)
    if generated is not None:
        trace.generation_ran = True
        answer = generated
    else:
        trace.fallback_used = True
        answer = raw_answer or "No relevant content found."

    return DispatchResult(answer=answer, citations=sources, retrieval_used=bool(sources))


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
