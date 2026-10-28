import pytest
from app.services.study_service import _parse_citations
from app.schemas.evidence_pack import EvidencePack, EvidenceChunk, CitationAnchor

def test_parse_citations_remaps_inline_markers_and_reorders_sources():
    # 1. Setup mock evidence chunks with all required Pydantic fields
    anchor1 = CitationAnchor(doc_id="d1", doc_name="Doc 1", page=1, slide=None, section="", chunk_id="c1", chunk_type="text")
    anchor2 = CitationAnchor(doc_id="d2", doc_name="Doc 2", page=2, slide=None, section="", chunk_id="c2", chunk_type="text")
    anchor3 = CitationAnchor(doc_id="d3", doc_name="Doc 3", page=3, slide=None, section="", chunk_id="c3", chunk_type="text")
    
    chunks = [
        EvidenceChunk(chunk_id="c1", text="Chunk 1 text", score=0.9, anchor=anchor1),
        EvidenceChunk(chunk_id="c2", text="Chunk 2 text", score=0.8, anchor=anchor2),
        EvidenceChunk(chunk_id="c3", text="Chunk 3 text", score=0.7, anchor=anchor3),
    ]
    
    pack = EvidencePack(
        query="test query",
        action="explain",
        total_candidates=3,
        ordering=[],
        deduped_passages=[],
        chunks=chunks
    )
    
    # 2. Mock an LLM response that cites out of order (Chunk 3, then Chunk 1), 
    # plus an out-of-bounds hallucinated citation (Chunk 99)
    original_text = (
        "Here is the most important point [ref_3]. "
        "It is supported by earlier context [ref_1]. "
        "This hallucinated citation doesn't exist [ref_99]."
    )
    
    remapped_text, sources = _parse_citations(original_text, pack)
    
    # 3. Assert sources were extracted and reordered based on first appearance
    assert len(sources) == 2
    assert sources[0].snippet == "Chunk 3 text"
    assert sources[1].snippet == "Chunk 1 text"
    
    # 4. Assert text was remapped sequentially (1-based) to match the new sources array
    expected_text = (
        "Here is the most important point [ref_1]. "
        "It is supported by earlier context [ref_2]. "
        "This hallucinated citation doesn't exist [ref_99]."
    )
    assert remapped_text == expected_text