"""Chat service — forwards RAG queries to the QVAC Node.js service.

The QVAC service owns embedding, HyperDB retrieval, and optional LLM synthesis.
This module is only responsible for the HTTP call and mapping the response to
the ChatResult type consumed by chat_api.py.

QVAC workspace = course_id, matching the convention in pipeline.py and ingest.js.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import List

import httpx

logger = logging.getLogger(__name__)

_QVAC_SERVICE_URL = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
_TOP_K = int(os.getenv("RAG_TOP_K", "5"))


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    snippet: str
    score: float


@dataclass
class ChatResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    retrieval_used: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def answer(question: str, course_id: str) -> ChatResult:
    """Send the question to the QVAC /query endpoint and return a ChatResult.

    retrieval_used is True only when the QVAC service returned at least one
    source — empty sources means nothing was found in the workspace, not that
    retrieval was skipped.
    """
    try:
        resp = httpx.post(
            f"{_QVAC_SERVICE_URL}/query",
            json={"question": question, "workspace": course_id, "topK": _TOP_K},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("QVAC service unavailable: %s", exc)
        return ChatResult(
            answer="The AI service is temporarily unavailable. Please try again later.",
            retrieval_used=False,
        )

    sources = data.get("sources", [])
    return ChatResult(
        answer=data["answer"],
        citations=[Citation(snippet=s["snippet"], score=s["score"]) for s in sources],
        retrieval_used=bool(sources),
    )
