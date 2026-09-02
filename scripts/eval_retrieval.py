#!/usr/bin/env python3
"""Retrieval evaluation script — measures Recall@5, MRR, and Precision@3.

Usage
-----
    # From repo root with the AI service virtualenv active:
    QVAC_SERVICE_URL=http://localhost:3001 python scripts/eval_retrieval.py \
        --queries tests/rag/test_queries.json \
        --course-id <course_id> \
        [--top-k 5] \
        [--min-score 0.0]

Environment
-----------
    QVAC_SERVICE_URL  QVAC service URL (default: http://localhost:3001).

The script does NOT require OPENAI_API_KEY — it evaluates retrieval only,
not LLM generation.

Metrics
-------
    Recall@K     Fraction of queries where at least one expected keyword
                 appears in the top-K retrieved chunks.
    MRR          Mean Reciprocal Rank — average of 1/rank where the first
                 relevant chunk (keyword match) appears in the result list.
    Precision@3  Average fraction of the top-3 chunks that are relevant.
"""
import argparse
import json
import os

import httpx


def _is_relevant(chunk_text: str, expected_keywords: list[str]) -> bool:
    """Return True if any expected keyword appears (case-insensitive) in the chunk."""
    text_lower = chunk_text.lower()
    return any(kw.lower() in text_lower for kw in expected_keywords)


def recall_at_k(relevant_flags: list[bool], k: int) -> float:
    """1 if any of the top-k chunks is relevant, else 0."""
    return 1.0 if any(relevant_flags[:k]) else 0.0


def reciprocal_rank(relevant_flags: list[bool]) -> float:
    """1/rank of first relevant chunk, or 0 if none found."""
    for i, flag in enumerate(relevant_flags):
        if flag:
            return 1.0 / (i + 1)
    return 0.0


def precision_at_k(relevant_flags: list[bool], k: int) -> float:
    """Fraction of top-k chunks that are relevant."""
    top = relevant_flags[:k]
    return sum(top) / k if top else 0.0


def evaluate(
    queries_path: str,
    course_id: str,
    top_k: int = 5,
    min_score: float = 0.0,
) -> None:
    qvac_url = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001").rstrip("/")

    with open(queries_path) as f:
        data = json.load(f)

    queries = data["queries"]
    print(f"\nEvaluating {len(queries)} queries (top_k={top_k}, min_score={min_score})\n")

    recalls: list[float] = []
    mrr_scores: list[float] = []
    p3_scores: list[float] = []

    for q in queries:
        qid = q["id"]
        query_text = q["query"]
        keywords = q["expected_keywords"]

        response = httpx.post(
            f"{qvac_url}/retrieve",
            json={"question": query_text, "workspace": course_id, "topK": top_k},
            timeout=60.0,
        )
        response.raise_for_status()
        chunks = [
            chunk
            for chunk in response.json().get("chunks", [])
            if float(chunk.get("score", 0.0)) >= min_score
        ]
        relevant_flags = [
            _is_relevant(chunk.get("content", chunk.get("text", "")), keywords)
            for chunk in chunks
        ]

        r_at_k = recall_at_k(relevant_flags, top_k)
        rr = reciprocal_rank(relevant_flags)
        p3 = precision_at_k(relevant_flags, 3)

        recalls.append(r_at_k)
        mrr_scores.append(rr)
        p3_scores.append(p3)

        status = "✓" if r_at_k > 0 else "✗"
        print(
            f"  {status} [{qid}] {query_text[:60]:<60}  "
            f"Recall@{top_k}={r_at_k:.0f}  RR={rr:.3f}  P@3={p3:.3f}  "
            f"chunks={len(chunks)}"
        )

    n = len(queries)
    print(f"\n{'─' * 72}")
    print(f"  Recall@{top_k}  : {sum(recalls)/n:.3f}  ({sum(recalls):.0f}/{n} queries hit)")
    print(f"  MRR        : {sum(mrr_scores)/n:.3f}")
    print(f"  Precision@3: {sum(p3_scores)/n:.3f}")
    print(f"{'─' * 72}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--queries",
        default="tests/rag/test_queries.json",
        help="Path to test_queries.json (default: tests/rag/test_queries.json)",
    )
    parser.add_argument(
        "--course-id",
        required=True,
        help="QVAC workspace/course ID to search",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve per query (default: 5)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum similarity score threshold (default: 0.0 = no filter)",
    )
    args = parser.parse_args()

    evaluate(
        queries_path=args.queries,
        course_id=args.course_id,
        top_k=args.top_k,
        min_score=args.min_score,
    )


if __name__ == "__main__":
    main()
