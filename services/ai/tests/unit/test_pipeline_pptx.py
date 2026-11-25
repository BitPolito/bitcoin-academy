"""Unit tests for PPTX text extraction and file-type-aware empty-text errors (Issue #297)."""
import pytest
from pptx import Presentation
from pptx.util import Inches

from app.workers.pipeline import (
    NO_TEXT_ERROR,
    _no_text_error_for_ext,
    parse_pptx_pages,
)


@pytest.mark.unit
def test_parse_pptx_pages_extracts_ordinary_text_boxes(tmp_path):
    """Slides with zero placeholders and only ordinary text boxes must extract text and slide numbers."""
    prs = Presentation()
    blank_layout = prs.slide_layouts[6]

    slide1 = prs.slides.add_slide(blank_layout)
    tb1 = slide1.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    tb1.text_frame.text = "Bitcoin uses proof-of-work to order transactions."

    slide2 = prs.slides.add_slide(blank_layout)
    tb2 = slide2.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    tb2.text_frame.text = "UTXOs represent unspent transaction outputs."

    pptx_path = tmp_path / "textboxes_only.pptx"
    prs.save(pptx_path)

    pages, slide_count = parse_pptx_pages(str(pptx_path))

    assert slide_count == 2
    assert len(pages) == 2
    assert pages[0]["page"] == 1
    assert "Bitcoin uses proof-of-work to order transactions." in pages[0]["text"]
    assert pages[1]["page"] == 2
    assert "UTXOs represent unspent transaction outputs." in pages[1]["text"]


@pytest.mark.unit
def test_parse_pptx_pages_deduplicates_title_and_reads_notes(tmp_path):
    """Standard title + body placeholders should not duplicate the title, and speaker notes are kept."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Merkle Trees"
    slide.placeholders[1].text = "Hash trees enable SPV proofs."
    slide.notes_slide.notes_text_frame.text = "Mention O(log n) verification."

    pptx_path = tmp_path / "standard_layout.pptx"
    prs.save(pptx_path)

    pages, slide_count = parse_pptx_pages(str(pptx_path))

    assert slide_count == 1
    assert pages[0]["page"] == 1
    assert pages[0]["text"].count("Merkle Trees") == 1
    assert "Hash trees enable SPV proofs." in pages[0]["text"]
    assert "*Notes: Mention O(log n) verification.*" in pages[0]["text"]


@pytest.mark.unit
def test_parse_pptx_pages_extracts_table_text(tmp_path):
    """Tables inside slides should be extracted alongside text boxes."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    table = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(5), Inches(2)).table
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Block Interval"
    table.cell(1, 1).text = "10 minutes"

    pptx_path = tmp_path / "table_slide.pptx"
    prs.save(pptx_path)

    pages, _ = parse_pptx_pages(str(pptx_path))

    assert "Metric | Value" in pages[0]["text"]
    assert "Block Interval | 10 minutes" in pages[0]["text"]


@pytest.mark.unit
def test_no_text_error_for_ext_matches_file_type():
    assert _no_text_error_for_ext(".pdf") == NO_TEXT_ERROR
    assert "PDF" in _no_text_error_for_ext(".pdf")

    pptx_err = _no_text_error_for_ext(".pptx")
    assert "presentation" in pptx_err.lower() or "pptx" in pptx_err.lower()
    assert "PDF" not in pptx_err
    assert "OCR" not in pptx_err

    docx_err = _no_text_error_for_ext(".docx")
    assert "Word" in docx_err or "DOCX" in docx_err
    assert "PDF" not in docx_err

    txt_err = _no_text_error_for_ext(".txt")
    assert "PDF" not in txt_err