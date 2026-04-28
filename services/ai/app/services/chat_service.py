"""Chat service — RAG orchestration: retrieval + optional LLM synthesis."""
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

logger = logging.getLogger(__name__)

_CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "")
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
_TOP_K = int(os.getenv("RAG_TOP_K", "5"))


# ---------------------------------------------------------------------------
# Data classes (no Pydantic — service layer only)
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    label: str
    section: Optional[str]
    page: Optional[int]
    slide: Optional[int]
    text_snippet: str


@dataclass
class ChatResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    retrieval_used: bool = False


# ---------------------------------------------------------------------------
# ChromaDB singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_chroma_collection():
    """Return the shared ChromaDB collection, initialised once per process."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from pathlib import Path

    if not _CHROMA_DB_PATH:
        # Derive default relative to this file: services/ai/chroma_db
        chroma_path = str(Path(__file__).resolve().parents[2] / "chroma_db")
    else:
        chroma_path = _CHROMA_DB_PATH

    client = chromadb.PersistentClient(
        path=chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name="bitpolito_course",
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _retrieve(query: str, course_id: str, top_k: int = _TOP_K) -> List[dict]:
    """Embed query and search ChromaDB, filtered to the given course."""
    from fastembed import TextEmbedding

    model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    query_vec = list(model.embed([query]))[0].tolist()

    collection = _get_chroma_collection()

    # Filter to only chunks belonging to this course
    where: dict = {"course_id": course_id}

    try:
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=top_k,
            where=where,
        )
    except Exception as exc:
        logger.warning("ChromaDB query failed (possibly empty collection): %s", exc)
        return []

    hits = []
    if results["ids"] and results["ids"][0]:
        for i, chunk_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            hits.append({
                "id": chunk_id,
                "text": results["documents"][0][i] if results["documents"] else "",
                "distance": results["distances"][0][i] if results["distances"] else 1.0,
                "label": meta.get("label", ""),
                "section": meta.get("section", ""),
                "page": meta.get("page"),
                "slide": meta.get("slide"),
            })
    return hits


def _build_context(hits: List[dict]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        loc = h.get("label") or h.get("section") or f"chunk {i}"
        parts.append(f"[{i}] ({loc})\n{h['text']}")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# LLM synthesis (optional — gracefully skipped if no API key)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a Bitcoin education assistant for BitPolito Academy. "
    "Answer the student's question using ONLY the context provided below. "
    "Be concise, accurate, and cite the source by its label (e.g. 'p. 3', 'Slide 5'). "
    "If the answer is not in the context, say so explicitly."
)


def _call_llm(question: str, context: str) -> Optional[str]:
    if not _OPENAI_API_KEY:
        return None
    try:
        from langchain_openai import ChatOpenAI
        from langchain.schema import HumanMessage, SystemMessage

        # Set key via env so ChatOpenAI picks it up without a deprecated kwarg
        os.environ.setdefault("OPENAI_API_KEY", _OPENAI_API_KEY)
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Context:\n{context}\n\nQuestion: {question}"),
        ]
        response = llm.invoke(messages)
        return str(response.content) if response.content else None  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def answer(question: str, course_id: str) -> ChatResult:
    """Retrieve relevant chunks and synthesise an answer.

    Falls back to returning raw context if no OpenAI key is configured
    or if the LLM call fails.
    """
    hits = _retrieve(question, course_id)

    if not hits:
        return ChatResult(
            answer=(
                "No relevant content was found for your question in this course. "
                "The course materials may not yet be indexed."
            ),
            retrieval_used=False,
        )

    citations = [
        Citation(
            label=h["label"],
            section=h["section"] or None,
            page=int(h["page"]) if h.get("page") else None,
            slide=int(h["slide"]) if h.get("slide") else None,
            text_snippet=h["text"][:250],
        )
        for h in hits
    ]

    context = _build_context(hits)
    llm_answer = _call_llm(question, context)

    if llm_answer:
        answer_text = llm_answer
    else:
        # Graceful fallback: return the top retrieved chunk as plain context
        answer_text = (
            "Here are the most relevant passages from your course materials:\n\n"
            + context
        )

    return ChatResult(
        answer=answer_text,
        citations=citations,
        retrieval_used=True,
    )
