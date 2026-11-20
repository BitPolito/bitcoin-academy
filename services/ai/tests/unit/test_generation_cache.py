"""Unit tests for app.services.generation_cache — rung 0 of the inference
ladder (issue #137/#161)."""
import pytest

from app.services.generation_cache import compute_generation_hash


@pytest.mark.unit
def test_deterministic():
    h1 = compute_generation_hash(["a", "b"], "v1", "model-a")
    h2 = compute_generation_hash(["a", "b"], "v1", "model-a")
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.unit
def test_order_independent():
    h1 = compute_generation_hash(["a", "b"], "v1", "model-a")
    h2 = compute_generation_hash(["b", "a"], "v1", "model-a")
    assert h1 == h2


@pytest.mark.unit
def test_changes_with_source_content():
    h1 = compute_generation_hash(["a"], "v1", "model-a")
    h2 = compute_generation_hash(["a-edited"], "v1", "model-a")
    assert h1 != h2


@pytest.mark.unit
def test_changes_with_prompt_version():
    h1 = compute_generation_hash(["a"], "v1", "model-a")
    h2 = compute_generation_hash(["a"], "v2", "model-a")
    assert h1 != h2


@pytest.mark.unit
def test_changes_with_model():
    h1 = compute_generation_hash(["a"], "v1", "model-a")
    h2 = compute_generation_hash(["a"], "v1", "model-b")
    assert h1 != h2
