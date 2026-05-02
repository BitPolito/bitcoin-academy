"""Chat service — RAG-backed Q&A using ChromaDB retrieval.

Uses the local ChromaDB + evidence pack pipeline as the primary retrieval path.
Falls back to the QVAC Node.js service if QVAC_SERVICE_URL is configured and
the local retrieval returns no results (e.g. collection not yet indexed).
"""
import logging
import os
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "")
_TOP_K = int(os.getenv("RAG_TOP_K", "5"))


@dataclass
class Citation:
    snippet: str
    score: float


@dataclass
class ChatResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    retrieval_used: bool = False


def answer(question: str, course_id: str) -> ChatResult:
    """Return a ChatResult for the given question using local ChromaDB retrieval."""
    result = _answer_local(question, course_id)
    if result is not None:
        return result

    if _QVAC_SERVICE_URL:
        result = _answer_qvac(question, course_id)
        if result is not None:
            return result

    return ChatResult(
        answer="The AI service is temporarily unavailable. Please try again later.",
        retrieval_used=False,
    )


def _answer_local(question: str, course_id: str) -> ChatResult | None:
    try:
        from app.services.evidence_pack_service import build as build_pack
        from app.rag.chains import run_llm_chain
        from app.rag.prompts import EXPLAIN_PROMPT

        pack = build_pack(question, "explain", course_id, top_k=_TOP_K)
        citations = [
            Citation(snippet=c.text[:300], score=c.score)
            for c in pack.chunks
        ]

        if not pack.chunks:
            return None

        context = "\n\n".join(c.text for c in pack.chunks)
        llm_answer = run_llm_chain(EXPLAIN_PROMPT, question, context)

        return ChatResult(
            answer=llm_answer or context[:800],
            citations=citations,
            retrieval_used=True,
        )
    except Exception as exc:
        logger.warning("Local retrieval failed: %s", exc)
        return None


def _answer_qvac(question: str, course_id: str) -> ChatResult | None:
    try:
        import httpx

        resp = httpx.post(
            f"{_QVAC_SERVICE_URL}/query",
            json={"question": question, "workspace": course_id, "topK": _TOP_K},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        sources = data.get("sources", [])
        return ChatResult(
            answer=data["answer"],
            citations=[Citation(snippet=s["snippet"], score=s["score"]) for s in sources],
            retrieval_used=bool(sources),
        )
    except Exception as exc:
        logger.warning("QVAC service unavailable: %s", exc)
        return None
