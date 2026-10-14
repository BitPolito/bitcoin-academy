"""Options of the RAG evaluation suite (tests/test_rag.py).

The technical set is the one run against the open corpus (baselines, CI); the
Bitcoin Standard set is local-only because the book is copyrighted. A
metrics-only report must never carry corpus text, since baselines are committed.
"""
import importlib
import os
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def suite():
    # test_rag sets RAG_* defaults in os.environ at import; keep them out of
    # the rest of the test session.
    with patch.dict(os.environ):
        return importlib.import_module("tests.test_rag")


@pytest.mark.unit
def test_query_sets_split_technical_from_bitcoin_standard(suite):
    technical = suite.QUERY_SETS["technical"]
    standard = suite.QUERY_SETS["bitcoin-standard"]

    assert len(technical) == 41
    assert {cat for cat, _ in technical} == {"technical"}
    assert len(standard) == 35
    assert "technical" not in {cat for cat, _ in standard}
    assert len(suite.QUERY_SETS["all"]) == len(technical) + len(standard)


@pytest.mark.unit
def test_metrics_only_report_carries_no_corpus_text(suite):
    result = suite.QueryResult(
        idx=1, category="technical", query="What is a UTXO?",
        answer="An answer quoting the corpus.",
        citations=[suite.CitationResult(
            label="p. 1", section="Transactions", page=1, score=0.8,
            snippet="Verbatim corpus passage.",
        )],
        retrieval_used=True,
    )

    full = suite._to_dict(result)
    metrics = suite._to_dict(result, metrics_only=True)

    assert full["answer"] and full["citations"][0]["snippet"]
    assert "answer" not in metrics
    assert "snippet" not in metrics["citations"][0]
    assert metrics["citations"][0]["section"] == "Transactions"
    assert metrics["num_citations"] == 1
