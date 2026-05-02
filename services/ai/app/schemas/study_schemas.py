"""Study action schemas — enum, registry, and API DTOs."""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Study action enum
# ---------------------------------------------------------------------------

class StudyAction(str, Enum):
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"
    RETRIEVE = "retrieve"
    OPEN_QUESTIONS = "open_questions"
    QUIZ = "quiz"
    ORAL = "oral"
    DERIVE = "derive"
    COMPARE = "compare"


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

@dataclass
class ActionMeta:
    name: str
    description: str
    retrieval_required: bool
    generation_required: bool
    output_type: str  # "prose" | "list" | "chunks" | "qa_pairs"
    source_grounding_required: bool
    example_query: str


STUDY_ACTION_REGISTRY: Dict[StudyAction, ActionMeta] = {
    StudyAction.EXPLAIN: ActionMeta(
        name="Explain",
        description="Clear prose explanation of the concept using retrieved context",
        retrieval_required=True,
        generation_required=True,
        output_type="prose",
        source_grounding_required=True,
        example_query="Explain how Bitcoin mining works",
    ),
    StudyAction.SUMMARIZE: ActionMeta(
        name="Summarize",
        description="Concise bullet-point summary of the main concepts",
        retrieval_required=True,
        generation_required=True,
        output_type="list",
        source_grounding_required=False,
        example_query="Summarize the key properties of Bitcoin",
    ),
    StudyAction.RETRIEVE: ActionMeta(
        name="Retrieve",
        description="Raw passage retrieval — returns the most relevant source chunks without generation",
        retrieval_required=True,
        generation_required=False,
        output_type="chunks",
        source_grounding_required=True,
        example_query="What is a UTXO?",
    ),
    StudyAction.OPEN_QUESTIONS: ActionMeta(
        name="Open Questions",
        description="Open-ended questions that prompt deeper understanding of the topic",
        retrieval_required=True,
        generation_required=True,
        output_type="list",
        source_grounding_required=False,
        example_query="Generate open questions about Bitcoin consensus",
    ),
    StudyAction.QUIZ: ActionMeta(
        name="Quiz",
        description="Multiple-choice Q&A pairs for self-assessment",
        retrieval_required=True,
        generation_required=True,
        output_type="qa_pairs",
        source_grounding_required=True,
        example_query="Quiz me on Bitcoin transaction structure",
    ),
    StudyAction.ORAL: ActionMeta(
        name="Oral",
        description="Simulated oral exam questions with model answers",
        retrieval_required=True,
        generation_required=True,
        output_type="qa_pairs",
        source_grounding_required=True,
        example_query="Prepare oral exam questions about Merkle trees",
    ),
    StudyAction.DERIVE: ActionMeta(
        name="Derive",
        description="Step-by-step proof or derivation scaffolded from source material",
        retrieval_required=True,
        generation_required=True,
        output_type="prose",
        source_grounding_required=True,
        example_query="Derive the proof of the source coding theorem",
    ),
    StudyAction.COMPARE: ActionMeta(
        name="Compare",
        description="Side-by-side comparison and reconciliation of definitions across sources",
        retrieval_required=True,
        generation_required=True,
        output_type="prose",
        source_grounding_required=True,
        example_query="Compare Bitcoin UTXO model with Ethereum account model",
    ),
}


# ---------------------------------------------------------------------------
# API DTOs
# ---------------------------------------------------------------------------

class StudyDispatchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    action: StudyAction


class CitationOut(BaseModel):
    snippet: str
    score: float
    label: str = ""
    page: int = 0
    slide: int = 0
    section: str = ""
    doc_id: str = ""


class StudyDispatchResponse(BaseModel):
    answer: str
    citations: List[CitationOut]
    retrieval_used: bool
    action: str


class ActionMetaOut(BaseModel):
    action: str
    name: str
    description: str
    retrieval_required: bool
    generation_required: bool
    output_type: str
    source_grounding_required: bool
    example_query: str


class StudyActionsResponse(BaseModel):
    actions: List[ActionMetaOut]
