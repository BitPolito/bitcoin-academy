"""Study action service — dispatches requests to per-action handlers."""
import logging

from app.rag import chains, prompts
from app.schemas.evidence_pack import EvidencePack
from app.schemas.study_schemas import StudyAction, StudyRequest, StudyResponse
from app.services import evidence_pack_service

logger = logging.getLogger(__name__)

_TOP_K = 10


def dispatch(req: StudyRequest, course_id: str) -> StudyResponse:
    pack = evidence_pack_service.build(req.query, req.action, course_id, top_k=_TOP_K)
    output = _route(req, pack)
    return StudyResponse(
        action=req.action,
        output=output,
        evidence=pack,
        retrieval_used=len(pack.chunks) > 0,
    )


def _route(req: StudyRequest, pack: EvidencePack) -> str:
    context = _build_context(pack)
    query = req.query

    if req.action == StudyAction.EXPLAIN:
        result = chains.run_llm_chain(prompts.EXPLAIN_PROMPT, query, context)
        return result if result is not None else _fallback_explain(pack)

    if req.action == StudyAction.SUMMARIZE:
        result = chains.run_llm_chain(prompts.SUMMARIZE_PROMPT, query, context)
        return result if result is not None else _fallback_summarize(pack)

    if req.action == StudyAction.RETRIEVE:
        return _fallback_retrieve(pack)

    if req.action == StudyAction.OPEN_QUESTIONS:
        result = chains.run_llm_chain(prompts.OPEN_Q_PROMPT, query, context)
        return result if result is not None else _llm_unavailable_msg("open questions")

    if req.action == StudyAction.QUIZ:
        result = chains.run_llm_chain(prompts.QUIZ_PROMPT, query, context)
        return result if result is not None else _llm_unavailable_msg("quiz")

    if req.action == StudyAction.ORAL:
        result = chains.run_llm_chain(prompts.ORAL_PROMPT, query, context)
        return result if result is not None else _llm_unavailable_msg("oral exam questions")

    return ""


def _build_context(pack: EvidencePack) -> str:
    if not pack.chunks:
        return "No relevant passages found in the course materials."
    parts = []
    for i, chunk in enumerate(pack.chunks, 1):
        anchor = chunk.anchor
        ref = anchor.doc_name
        if anchor.section:
            ref += f" — {anchor.section}"
        if anchor.page:
            ref += f" (p.{anchor.page})"
        elif anchor.slide:
            ref += f" (slide {anchor.slide})"
        parts.append(f"[{i}] {ref}\n{chunk.text}")
    return "\n\n".join(parts)


def _fallback_explain(pack: EvidencePack) -> str:
    if not pack.chunks:
        return "No relevant passages found in the course materials for this query."
    lines = ["Here are the most relevant passages from your course materials:\n"]
    for i, c in enumerate(pack.chunks, 1):
        lines.append(f"{i}. {c.text[:400]}{'...' if len(c.text) > 400 else ''}")
    return "\n\n".join(lines)


def _fallback_summarize(pack: EvidencePack) -> str:
    if not pack.chunks:
        return "No relevant passages found in the course materials for this query."
    lines = ["Key passages from your course materials:\n"]
    for c in pack.chunks:
        lines.append(f"• {c.text[:300]}{'...' if len(c.text) > 300 else ''}")
    return "\n".join(lines)


def _fallback_retrieve(pack: EvidencePack) -> str:
    if not pack.chunks:
        return "No relevant passages found in the course materials for this query."
    lines = [f"Found {len(pack.chunks)} relevant passage(s):\n"]
    for i, c in enumerate(pack.chunks, 1):
        anchor = c.anchor
        ref = anchor.doc_name
        if anchor.section:
            ref += f" — {anchor.section}"
        if anchor.page:
            ref += f" · p.{anchor.page}"
        elif anchor.slide:
            ref += f" · slide {anchor.slide}"
        lines.append(f"[{i}] {ref} (score: {c.score:.0%})\n{c.text[:400]}")
    return "\n\n".join(lines)


def _llm_unavailable_msg(action_name: str) -> str:
    return (
        f"Generated {action_name} require an LLM (OPENAI_API_KEY not configured). "
        "The relevant source passages are shown below."
    )
