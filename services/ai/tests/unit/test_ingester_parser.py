"""Unit tests for StructuralParser using real fixture files (D-01, R-01).

Fixture files:
  docs/src/bitcoin_technical_document.pdf — 4-page technical PDF
  docs/src/bitcoin_creative_commons_en.pptx — 5-slide PPTX deck

Import order: pipeline must be imported first to trigger _alias_schema_module()
and register the ingester src dir in sys.path.

parse_pages() receives pdfplumber page objects (for PDFs) or python-pptx slide
objects (for PPTX) — never raw integers.  We use RamSafeIngestor.process_in_batches
to get the correct page/slide objects, matching what pipeline.py does.
"""
from pathlib import Path

import pytest

import app.workers.pipeline  # noqa: F401 — triggers alias + sys.path setup
from module_1_ingestor import RamSafeIngestor  # noqa: E402
from module_2_parser import StructuralParser  # noqa: E402

from app.schemas.normalized_document import BlockType, DocumentType

_REPO_ROOT = Path(__file__).resolve().parents[4]  # bitcoin-academy/
_DOCS = _REPO_ROOT / "docs" / "src"
PDF_PATH = _DOCS / "bitcoin_technical_document.pdf"
PPTX_PATH = _DOCS / "bitcoin_creative_commons_en.pptx"


def _require_fixture(path: Path):
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")


def _parse_file(file_path: Path, doc_type: DocumentType, **kwargs):
    """Parse a file end-to-end using RamSafeIngestor → StructuralParser, returns NormalizedDocument."""
    ingestor = RamSafeIngestor(file_path=str(file_path), chunk_size=100)
    parser = StructuralParser(
        file_path=str(file_path),
        use_advanced_parser=False,
        course_id=kwargs.get("course_id", "course-btc-001"),
        document_id=kwargs.get("document_id", "doc-001"),
        document_type=doc_type,
        title=kwargs.get("title", "Test Doc"),
        source_filename=file_path.name,
        lecture_id=kwargs.get("lecture_id"),
        tags=kwargs.get("tags"),
        prerequisites=kwargs.get("prerequisites"),
    )
    result = {}

    def _callback(pages):
        result["doc"] = parser.parse_pages(pages, ingestor.total_pages)

    ingestor.process_in_batches(_callback)
    return result["doc"]


# ---------------------------------------------------------------------------
# PDF — bitcoin_technical_document.pdf (4 pages)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_pdf_parser_returns_normalized_document():
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    assert doc.doc_id == "doc-001"
    assert doc.course_id == "course-btc-001"
    assert doc.document_type == DocumentType.TEXTBOOK_EXCERPT
    assert len(doc.blocks) > 0


@pytest.mark.unit
def test_pdf_parser_extracts_headings():
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    headings = [b for b in doc.blocks if b.block_type == BlockType.HEADING]
    # PDF has sections: Introduction, Blockchain Structure, Transactions, Consensus, Network Protocol
    assert len(headings) >= 3


@pytest.mark.unit
def test_pdf_parser_extracts_paragraphs():
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    paras = [b for b in doc.blocks if b.block_type == BlockType.PARAGRAPH]
    assert len(paras) > 0


@pytest.mark.unit
def test_pdf_parser_page_count():
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    assert doc.page_count == 4


@pytest.mark.unit
def test_pdf_parser_all_blocks_have_text():
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    for block in doc.blocks:
        assert isinstance(block.text, str)
        assert len(block.text.strip()) > 0


@pytest.mark.unit
def test_pdf_parser_blocks_have_page_numbers():
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    blocks_with_page = [b for b in doc.blocks if b.position.page is not None]
    assert len(blocks_with_page) > 0
    for b in blocks_with_page:
        assert 1 <= b.position.page <= 4


@pytest.mark.unit
def test_pdf_parser_propagates_lecture_id():
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT, lecture_id="L99")
    assert doc.lecture_id == "L99"


@pytest.mark.unit
def test_pdf_parser_propagates_tags_and_prerequisites():
    _require_fixture(PDF_PATH)
    doc = _parse_file(
        PDF_PATH, DocumentType.TEXTBOOK_EXCERPT,
        tags=["blockchain", "consensus"],
        prerequisites=["cryptography"],
    )
    assert doc.tags == ["blockchain", "consensus"]
    assert doc.prerequisites == ["cryptography"]


@pytest.mark.unit
def test_pdf_parser_contains_bitcoin_content():
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    all_text = " ".join(b.text for b in doc.blocks).lower()
    assert "bitcoin" in all_text or "blockchain" in all_text or "block" in all_text


# ---------------------------------------------------------------------------
# PPTX — bitcoin_creative_commons_en.pptx (5 slides)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_pptx_parser_returns_normalized_document():
    _require_fixture(PPTX_PATH)
    doc = _parse_file(PPTX_PATH, DocumentType.LECTURE_SLIDES)
    assert doc.doc_id == "doc-001"
    assert doc.document_type == DocumentType.LECTURE_SLIDES
    assert len(doc.blocks) > 0


@pytest.mark.unit
def test_pptx_parser_slide_count():
    _require_fixture(PPTX_PATH)
    doc = _parse_file(PPTX_PATH, DocumentType.LECTURE_SLIDES)
    assert doc.slide_count == 5


@pytest.mark.unit
def test_pptx_parser_slide_blocks_have_slide_numbers():
    _require_fixture(PPTX_PATH)
    doc = _parse_file(PPTX_PATH, DocumentType.LECTURE_SLIDES)
    slide_blocks = [
        b for b in doc.blocks
        if b.block_type in (BlockType.SLIDE_TITLE, BlockType.SLIDE_BODY)
    ]
    assert len(slide_blocks) > 0
    for b in slide_blocks:
        assert b.position.slide is not None
        assert 1 <= b.position.slide <= 5


@pytest.mark.unit
def test_pptx_parser_contains_bitcoin_content():
    _require_fixture(PPTX_PATH)
    doc = _parse_file(PPTX_PATH, DocumentType.LECTURE_SLIDES)
    all_text = " ".join(b.text for b in doc.blocks).lower()
    assert "bitcoin" in all_text


@pytest.mark.unit
def test_pptx_parser_blocks_all_have_nonempty_text():
    _require_fixture(PPTX_PATH)
    doc = _parse_file(PPTX_PATH, DocumentType.LECTURE_SLIDES)
    for block in doc.blocks:
        assert block.text.strip() != "", f"Empty block: {block}"


# ---------------------------------------------------------------------------
# Ligature sanitization
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_ligature_fi_sanitized():
    """'昀椀' (corrupted 'fi' ligature) must be replaced with plain ASCII 'fi'."""
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    for block in doc.blocks:
        assert "昀椀" not in block.text, f"Ligature corruption found in: {block.text[:100]}"


@pytest.mark.unit
def test_ligature_fl_sanitized():
    """'昀氀' (corrupted 'fl' ligature) must not appear in output."""
    _require_fixture(PDF_PATH)
    doc = _parse_file(PDF_PATH, DocumentType.TEXTBOOK_EXCERPT)
    for block in doc.blocks:
        assert "昀氀" not in block.text
