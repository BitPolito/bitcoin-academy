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
from typing import AsyncGenerator, List, Optional

import httpx

from app.core.errors import ExternalServiceError
from app.schemas.evidence_pack import EvidenceChunk, EvidencePack
from app.schemas.study_schemas import (
    MIN_STUDY_QUERY_LENGTH,
    STUDY_ACTION_REGISTRY,
    ActionMeta,
    StudyAction,
)
from app.rag.retriever import unified_retrieval
from app.services import evidence_pack_service

logger = logging.getLogger(__name__)

_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")

# Bump when any prompt in _SYSTEM_PROMPTS below changes meaning (not just
# wording) — tracked in app/prompts/registry.py for cross-system auditing.
STUDY_PROMPT_VERSION = "v1"

# Retrieval client: 45 s read covers dense search + BM25 on large corpora.
_qvac_client = httpx.AsyncClient(
    base_url=_QVAC_SERVICE_URL,
    timeout=httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0),
)

# Generation client: 120 s read covers Qwen3-4B Q4 on CPU-only hardware for long
# derivations/comparisons. Kept separate so retrieval timeouts remain tight.
_qvac_gen_client = httpx.AsyncClient(
    base_url=_QVAC_SERVICE_URL,
    timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0),
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
        "5. CRITICAL — use EXACTLY these labels on their own lines, with a colon, no variations:\n"
        "   Q1: / Q2: / Q3:\n"
        "   Model answer:\n"
        "   Follow-up:\n"
        "   Any other label will break the parser that students use to see their results.\n"
        "6. Format:\n"
        "Q1: <question>\n"
        "Model answer: <answer with [ref_N] citations>\n"
        "Follow-up: <deeper question as a question ending with ?>\n"
        "\n"
        "Q2: <question>\n"
        "Model answer: <answer with [ref_N] citations>\n"
        "Follow-up: <deeper question ending with ?>"
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
        "1. First, identify exactly 3–4 comparison dimensions that are relevant to BOTH concepts"
        " and that appear in the source material. List them explicitly as:\n"
        "   **Dimensions: <dim1>, <dim2>, <dim3>[, <dim4>]**\n"
        "2. Then produce a Markdown table with one row per dimension and one column per concept.\n"
        "   | Dimension | Concept A | Concept B |\n"
        "   |---|---|---|\n"
        "   Fill every cell with a concise value drawn from the context.\n"
        "3. Use exact technical terms from the document; cite sources inline as [ref_N].\n"
        "4. Conclude with a 1-paragraph synthesis drawing out the most important"
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


# Returned instead of a generated answer when retrieval finds no evidence.
_NO_EVIDENCE_ANSWER = "No relevant content found."


def _lacks_evidence(meta: ActionMeta, pack: EvidencePack) -> bool:
    """Study outputs must be generated only from retrieved evidence
    (specification 10). With an empty pack the model would answer from its own
    knowledge, presented to the student as course material."""
    return meta.retrieval_required and not pack.chunks


_REF_PATTERN = re.compile(r'\[ref_(\d+)\]', re.IGNORECASE)
# A marker cut off at the end of a streamed token: "[", "[re", "[ref_1", ...
_PARTIAL_REF_PATTERN = re.compile(r'\[(?:r(?:e(?:f(?:_\d*)?)?)?)?\Z', re.IGNORECASE)


class _CitationRenumberer:
    """Renumber [ref_N] markers 1, 2, ... in order of first appearance (#264).

    The client numbers the sources list from 1, and that list is ordered by
    first citation, so the inline markers must use the same numbers. Works on
    streamed tokens: a marker split across tokens is held back until it is
    complete. Markers outside the evidence pack are left unchanged.
    """

    def __init__(self, pack_size: int) -> None:
        self._pack_size = pack_size
        self._numbers: dict[int, int] = {}  # pack index -> new 1-based number
        self._pending = ""

    @property
    def cited_indices(self) -> list[int]:
        """Pack indices of the cited chunks, in citation order."""
        return list(self._numbers)

    def feed(self, token: str) -> str:
        text = self._pending + token
        partial = _PARTIAL_REF_PATTERN.search(text)
        cut = partial.start() if partial else len(text)
        self._pending = text[cut:]
        return _REF_PATTERN.sub(self._renumber, text[:cut])

    def flush(self) -> str:
        text, self._pending = self._pending, ""
        return _REF_PATTERN.sub(self._renumber, text)

    def _renumber(self, match: re.Match[str]) -> str:
        idx = int(match.group(1)) - 1  # [ref_N] is 1-based
        if not 0 <= idx < self._pack_size:
            return match.group(0)
        number = self._numbers.setdefault(idx, len(self._numbers) + 1)
        return f"[ref_{number}]"


def _cited_sources(pack: EvidencePack, cited_indices: list[int]) -> List[SourceChunk]:
    """SourceChunks for the cited evidence, in citation order.

    Falls back to all pack chunks when no [ref_N] markers are found — this
    happens when the LLM ignores the citation instruction or when the action
    does not require source grounding.
    """
    chunks = [pack.chunks[i] for i in cited_indices] if cited_indices else pack.chunks
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
        for c in chunks
    ]


def _parse_citations(text: str, pack: EvidencePack) -> tuple[str, List[SourceChunk]]:
    """Renumber the [ref_N] markers in generated text and return the cited chunks.

    Returns (text, sources): marker N in the returned text refers to sources[N - 1].
    """
    renumberer = _CitationRenumberer(len(pack.chunks))
    remapped = renumberer.feed(text) + renumberer.flush()
    return remapped, _cited_sources(pack, renumberer.cited_indices)


async def _retrieve(question: str, course_id: str, action: StudyAction) -> tuple[str, EvidencePack]:
    """Run the shared hybrid pipeline and wrap the result into an EvidencePack.

    Returns (raw_answer, pack). raw_answer is always "" now: retrieval no
    longer goes through QVAC /query, which pre-generated an answer, so the
    generation-failure fallback relies on the pack alone.

    Uses the same pipeline as the chat path (app.rag.retriever): a
    RAG_RETRIEVE_K candidate pool, BM25 fusion, reranking and MMR down to
    RAG_TOP_K, parent expansion. Action-specific boosting is applied on top
    by evidence_pack_service.build_from_chunks.

    The retrieval query may be rewritten or HyDE-expanded before hitting QVAC;
    the original *question* is preserved for generation prompts and citations.
    Raises ExternalServiceError when retrieval fails. An empty pack means the
    search completed successfully but found no relevant passages.
    """
    from app.rag.query_rewriter import expand_query
    retrieval_query = await expand_query(question)

    try:
        context_chunks, _ = await unified_retrieval(
            question, course_id, retrieval_query, client=_qvac_client
        )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Study retrieval failed: %s", exc)
        if isinstance(exc, httpx.TimeoutException):
            message = "The course search service took too long to respond. Please try again."
            code = "RETRIEVAL_TIMEOUT"
        elif isinstance(exc, httpx.HTTPError):
            message = "The course search service is unavailable. Please try again shortly."
            code = "RETRIEVAL_UNAVAILABLE"
        else:
            message = "The course search service could not complete the search. Please try again."
            code = "RETRIEVAL_FAILED"
        raise ExternalServiceError(message=message, code=code) from exc

    if not context_chunks:
        logger.info("Retrieval returned 0 chunks for course '%s'", course_id)

    pack = evidence_pack_service.build_from_chunks(question, action.value, context_chunks)
    return "", pack


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
    retrieval_errors: list[ExternalServiceError] = []
    for res in results:
        if isinstance(res, BaseException):
            logger.warning("Two-hop sub-retrieval failed: %s", res)
            if isinstance(res, ExternalServiceError):
                retrieval_errors.append(res)
            continue
        raw_ans, pack = res
        if raw_ans:
            raw_answers.append(raw_ans)
        for chunk in pack.chunks:
            if chunk.chunk_id not in merged:
                merged[chunk.chunk_id] = chunk

    if not merged:
        logger.info("Two-hop produced no chunks — falling back to single retrieval")
        result = await _retrieve(question, course_id, action)
        # An empty final search does not erase a failed sub-query. Useful
        # evidence from either path still preserves the existing fallback.
        if not result[1].chunks and retrieval_errors:
            raise retrieval_errors[0]
        return result

    logger.debug(
        "Two-hop retrieval for '%s': %d unique chunks from %d sub-queries",
        action.value, len(merged), len(parts[:2]),
    )
    combined = evidence_pack_service.build_from_chunks(
        question, action.value, list(merged.values())
    )
    return raw_answers[0] if raw_answers else "", combined


_THINKING_ACTIONS = frozenset({StudyAction.DERIVE})


async def _generate(action: StudyAction, question: str, context: str) -> Optional[str]:
    """Call QVAC /generate with the action-specific system prompt (local LLM via QVAC SDK).

    The pre-formatted context string (with [ref_N] markers) is passed as a single
    context block so the LLM sees the citation anchors embedded by evidence_pack_service.

    Returns None when QVAC is unreachable or returns an empty answer, allowing
    the caller to fall back to the raw retrieval context.

    preserveMarkdown is always True for study actions — their system prompts request
    structured output (tables, numbered steps, [ref_N] markers) that must not be stripped.
    enableThinking is True only for DERIVE to leverage Qwen3's step-by-step reasoning.
    """
    system_prompt = _SYSTEM_PROMPTS.get(action, "")
    enable_thinking = action in _THINKING_ACTIONS
    try:
        resp = await _qvac_gen_client.post(
            "/generate",
            json={
                "question": question,
                "context": [{"label": "", "text": context}],
                "systemPrompt": system_prompt,
                "preserveMarkdown": True,
                "enableThinking": enable_thinking,
            },
        )
        resp.raise_for_status()
        answer: str = resp.json().get("answer", "")
        return answer or None
    except httpx.HTTPError as exc:
        logger.warning("QVAC /generate failed for action '%s': %s", action.value, exc)
        return None


async def _stream_generate(
    action: StudyAction, question: str, context: str
) -> AsyncGenerator[str, None]:
    """Call QVAC /stream with the action-specific system prompt and yield raw tokens.

    Used by stream_dispatch() to provide progressive display for slow generations on
    limited hardware.  enableThinking follows the same rules as _generate().
    """
    system_prompt = _SYSTEM_PROMPTS.get(action, "")
    enable_thinking = action in _THINKING_ACTIONS
    tokens_yielded = 0
    try:
        async with _qvac_gen_client.stream(
            "POST",
            "/stream",
            json={
                "question": question,
                "context": [{"label": "", "text": context}],
                "systemPrompt": system_prompt,
                "enableThinking": enable_thinking,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    return
                try:
                    token = json.loads(payload)
                    if isinstance(token, str):
                        if token.startswith("[ERROR]"):
                            raise httpx.RemoteProtocolError("QVAC reported a stream failure")
                        tokens_yielded += 1
                        yield token
                except (json.JSONDecodeError, ValueError):
                    pass
            if tokens_yielded:
                raise httpx.RemoteProtocolError("QVAC stream ended without [DONE]")
    except httpx.HTTPError as exc:
        logger.warning("QVAC /stream failed for action '%s': %s", action.value, exc)
        if tokens_yielded:
            # Partial stream: propagate so the caller streams what it has but
            # does NOT persist a truncated answer to the shared semantic cache.
            raise
        return


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

    if _lacks_evidence(meta, pack):
        trace.fallback_used = True
        return DispatchResult(
            answer=raw_answer or _NO_EVIDENCE_ANSWER,
            citations=[],
            retrieval_used=False,
            evidence_pack=pack,
        )

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
        answer = pack.context_block() or raw_answer or _NO_EVIDENCE_ANSWER
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
        answer, sources = _parse_citations(generated, pack)
    else:
        trace.fallback_used = True
        answer = pack.context_block() or raw_answer or _NO_EVIDENCE_ANSWER
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
    if len(question.strip()) < MIN_STUDY_QUERY_LENGTH:
        raise ValueError(
            f"Query too short — must be at least {MIN_STUDY_QUERY_LENGTH} characters"
        )

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

        # A no-evidence result is not cached, so a document uploaded later can
        # answer the same question.
        if not result.retrieval_used and STUDY_ACTION_REGISTRY[action].retrieval_required:
            return result

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


# Actions that must be fully buffered before the frontend can parse the output.
# QUIZ needs the complete text to split on question delimiters.
# ORAL needs the complete text to parse Q/model-answer/follow-up blocks.
# RETRIEVE has no generation at all.
_BUFFERED_ACTIONS = frozenset({StudyAction.QUIZ, StudyAction.ORAL, StudyAction.RETRIEVE})

_CITATIONS_SENTINEL = "\x00CITATIONS\x00"


async def stream_dispatch(
    question: str,
    course_id: str,
    action: StudyAction,
    rag_only: bool = False,
) -> AsyncGenerator[str, None]:
    """Streaming variant of dispatch().

    Yields raw token strings followed by a citations sentinel for the frontend
    to parse. Uses the same retrieval pipeline as dispatch() and shares its
    semantic cache — a cache hit short-circuits retrieval and generation entirely,
    returning the cached answer as a single chunk at the speed of Redis.

    QUIZ, ORAL, and RETRIEVE are always buffered (full output needed for parsing).
    All other actions stream token-by-token via QVAC /stream.

    Sentinel format: \\x00CITATIONS\\x00<json-array-of-SourceChunk-dicts>
    """
    if len(question.strip()) < MIN_STUDY_QUERY_LENGTH:
        raise ValueError(
            f"Query too short — must be at least {MIN_STUDY_QUERY_LENGTH} characters"
        )

    # --- Semantic cache lookup (shared with dispatch()) ---
    from app.services.cache_service import get_cached, set_cached  # noqa: PLC0415
    cache_key = f"{question} [action:{action.value}]" + (" [rag_only]" if rag_only else "")
    cached = get_cached(cache_key, course_id)
    if cached is not None:
        yield cached["answer"]
        yield _CITATIONS_SENTINEL + json.dumps(cached.get("citations", []))
        return

    meta = STUDY_ACTION_REGISTRY[action]

    # Retrieval — identical to dispatch()
    raw_answer = ""
    pack = _empty_pack(question, action)
    if meta.retrieval_required:
        raw_answer, pack = await _retrieve_multi(question, course_id, action)

    # No evidence: no generation and no cache write (see _lacks_evidence).
    if _lacks_evidence(meta, pack):
        yield raw_answer or _NO_EVIDENCE_ANSWER
        yield _CITATIONS_SENTINEL + json.dumps([])
        return

    # Build citations list for the sentinel payload
    def _make_sources(chunks: list[EvidenceChunk]) -> List[SourceChunk]:
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
            for c in chunks
        ]

    def _cache_and_sentinel(answer: str, sources: List[SourceChunk]) -> str:
        citations_raw = [dataclasses.asdict(s) for s in sources]
        set_cached(cache_key, course_id, {
            "answer": answer,
            "citations": citations_raw,
            "retrieval_used": bool(sources),
        })
        return _CITATIONS_SENTINEL + json.dumps(citations_raw)

    # Retrieve-only or rag_only: emit context block as a single chunk, then citations
    if not meta.generation_required or rag_only:
        answer = pack.context_block() or raw_answer or _NO_EVIDENCE_ANSWER
        sources = _make_sources(pack.chunks)
        yield answer
        yield _cache_and_sentinel(answer, sources)
        return

    # Buffered actions (QUIZ, ORAL): generate fully, emit, cache, sentinel
    if action in _BUFFERED_ACTIONS:
        generated = await _generate(action, question, pack.context_block())
        if generated:
            answer, sources = _parse_citations(generated, pack)
        else:
            answer = pack.context_block() or raw_answer or _NO_EVIDENCE_ANSWER
            sources = _make_sources(pack.chunks)
        yield answer
        yield _cache_and_sentinel(answer, sources)
        return

    # Streaming actions: stream tokens, accumulate for citation parsing + cache write.
    # Markers are renumbered as they stream, so the client sees the same
    # numbers as the sources list and the cached answer.
    renumberer = _CitationRenumberer(len(pack.chunks))
    accumulated: list[str] = []
    try:
        async for token in _stream_generate(action, question, pack.context_block()):
            text = renumberer.feed(token)
            accumulated.append(text)
            yield text
    except httpx.HTTPError as exc:
        raise ExternalServiceError(
            message="Answer interrupted. Please retry.",
            code="GENERATION_INTERRUPTED",
        ) from exc

    if accumulated:
        tail = renumberer.flush()
        if tail:
            accumulated.append(tail)
            yield tail
        full_text = "".join(accumulated)
        sources = _cited_sources(pack, renumberer.cited_indices)
        yield _cache_and_sentinel(full_text, sources)
    else:
        # Stream yielded nothing — fall back to buffered generate
        generated = await _generate(action, question, pack.context_block())
        if generated:
            remapped_text, sources = _parse_citations(generated, pack)
            yield remapped_text
            yield _cache_and_sentinel(remapped_text, sources)
        else:
            fallback = pack.context_block() or raw_answer or _NO_EVIDENCE_ANSWER
            sources = _make_sources(pack.chunks)
            yield fallback
            yield _cache_and_sentinel(fallback, sources)
