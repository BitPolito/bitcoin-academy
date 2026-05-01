"""Unit test for the sys.modules aliasing in pipeline.py (dual-import guard).

The key invariant: DocumentChunk imported via 'app.schemas.normalized_document'
and via 'services.ai.app.schemas.normalized_document' must be the *same class
object* — otherwise Pydantic isinstance checks fail silently at runtime.
"""
import sys
import pytest


@pytest.mark.unit
def test_alias_module_registered_in_sys_modules():
    """After importing pipeline, the long-form module path must be in sys.modules."""
    import app.workers.pipeline  # noqa: F401
    assert "services.ai.app.schemas.normalized_document" in sys.modules


@pytest.mark.unit
def test_alias_points_to_same_module_object():
    """Both module paths must resolve to the exact same module object."""
    import app.workers.pipeline  # noqa: F401
    import app.schemas.normalized_document as short_mod
    long_mod = sys.modules["services.ai.app.schemas.normalized_document"]
    assert short_mod is long_mod


@pytest.mark.unit
def test_document_chunk_class_identity():
    """DocumentChunk from short and long paths must be the identical class."""
    import app.workers.pipeline  # noqa: F401
    from app.schemas.normalized_document import DocumentChunk as DC_short
    from services.ai.app.schemas.normalized_document import DocumentChunk as DC_long  # type: ignore[import]
    assert DC_short is DC_long


@pytest.mark.unit
def test_normalized_document_class_identity():
    """NormalizedDocument class identity across both import paths."""
    import app.workers.pipeline  # noqa: F401
    from app.schemas.normalized_document import NormalizedDocument as ND_short
    from services.ai.app.schemas.normalized_document import NormalizedDocument as ND_long  # type: ignore[import]
    assert ND_short is ND_long


@pytest.mark.unit
def test_namespace_package_chain_registered():
    """Intermediate namespace packages must exist in sys.modules."""
    import app.workers.pipeline  # noqa: F401
    for name in ["services", "services.ai", "services.ai.app", "services.ai.app.schemas"]:
        assert name in sys.modules, f"Missing namespace package: {name}"


@pytest.mark.unit
def test_pydantic_isinstance_works_cross_path():
    """An instance created via short path is recognised as DC_long and vice versa."""
    import app.workers.pipeline  # noqa: F401
    from app.schemas.normalized_document import (
        DocumentChunk as DC_short,
        DocumentType,
    )
    from services.ai.app.schemas.normalized_document import DocumentChunk as DC_long  # type: ignore[import]

    chunk = DC_short(
        doc_id="d",
        course_id="c",
        document_type=DocumentType.LECTURE_NOTES,
        text="hello",
        block_ids=["b1"],
        citation_label="p. 1",
        chunk_index=0,
        char_count=5,
    )
    assert isinstance(chunk, DC_long)
    assert isinstance(chunk, DC_short)
