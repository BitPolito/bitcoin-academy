"""Chat service — QVAC-backed Q&A."""
import logging
import os
from dataclasses import dataclass, field
from typing import List

import httpx

logger = logging.getLogger(__name__)

_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "")
_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

_client = httpx.AsyncClient(base_url=_QVAC_SERVICE_URL, timeout=60.0)


@dataclass
class Citation:
    snippet: str
    score: float
    label: str = ""
    page: int = 0
    slide: int = 0
    section: str = ""
    doc_id: str = ""


@dataclass
class ChatResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    retrieval_used: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _chroma_chat_result(question: str, course_id: str) -> ChatResult:
    """Query ChromaDB and return a ChatResult with raw snippets as answer."""
    from app.services.chroma_retrieval import query_chroma  # lazy import
    sources = query_chroma(question, course_id, top_k=_TOP_K)
    citations = [
        Citation(
            snippet=s["snippet"],
            score=s["score"],
            label=s["label"],
            page=s["page"],
            slide=s["slide"],
            section=s["section"],
            doc_id=s["doc_id"],
        )
        for s in sources
    ]
    answer_text = (
        "\n\n---\n\n".join(s["snippet"] for s in sources)
        if sources
        else "No relevant content found."
    )
    return ChatResult(answer=answer_text, citations=citations, retrieval_used=bool(citations))


async def answer(question: str, course_id: str) -> ChatResult:
    """Send the question to the QVAC /query endpoint and return a ChatResult.

    Falls back to ChromaDB when QVAC is unavailable or returns zero sources.
    """
    try:
        resp = await _client.post(
            "/query",
            json={"question": question, "workspace": course_id, "topK": _TOP_K},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("QVAC service unavailable (%s) — trying ChromaDB fallback", exc)
        return _chroma_chat_result(question, course_id)

    try:
        data = resp.json()
        answer_text = data["answer"]
        sources = data.get("sources", [])
    except (ValueError, KeyError) as exc:
        logger.error("Unexpected QVAC response: %s — %.200s", exc, resp.text)
        return ChatResult(
            answer="Received an unexpected response from the AI service.",
            retrieval_used=False,
        )

    if not sources:
        logger.info(
            "QVAC returned 0 sources for course '%s', trying ChromaDB fallback", course_id
        )
        fallback = _chroma_chat_result(question, course_id)
        if fallback.citations:
            return fallback

    citations = [
        Citation(
            snippet=s.get("snippet", ""),
            score=s.get("score", 0.0),
            label=s.get("label", ""),
            page=s.get("page", 0),
            slide=s.get("slide", 0),
            section=s.get("section", ""),
            doc_id=s.get("doc_id", ""),
        )
        for s in sources
    ]

    return ChatResult(
        answer=answer_text,
        citations=citations,
        retrieval_used=bool(sources),
    )
