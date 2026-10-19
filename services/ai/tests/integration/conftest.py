"""Shared fixtures for the integration tests."""
import pytest


@pytest.fixture(autouse=True)
def _disable_query_expansion(monkeypatch):
    """Keep HyDE and query rewriting off so no test calls a real QVAC service.

    Both flags are read once at import time, so patch the module attributes
    rather than the environment. Without this, a QVAC service running on
    localhost rewrites the question with generated text: the chat and study
    payload assertions fail locally while CI, with no QVAC, stays green (#208).
    The rewriter itself is covered by tests/unit/test_query_rewriter.py.
    """
    monkeypatch.setattr("app.rag.query_rewriter._HYDE_ENABLED", False)
    monkeypatch.setattr("app.rag.query_rewriter._REWRITE_ENABLED", False)
