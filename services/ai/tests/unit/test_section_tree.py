"""Unit tests for section-tree extraction (course builder Fase 1).

Covers the section events collected by build_parent_child_chunks, the
nesting logic of build_section_tree, and the chunk_parent backfill path.
All functions are pure — no DB or services involved.
"""
from types import SimpleNamespace

import pytest

import app.workers.pipeline as pipeline_mod

# Long enough that every block clears the chunker's minimum word thresholds.
_PARA = "Bitcoin transactions consume unspent outputs and create new ones. " * 12


def _pages_with_headings() -> list[dict]:
    return [
        {"page": 1, "text": f"{_PARA}\n\n# Chapter One\n\n{_PARA}"},
        {"page": 2, "text": f"## Section 1.1\n\n{_PARA}\n\n### Detail 1.1.1\n\n{_PARA}"},
        {"page": 3, "text": f"# Chapter Two\n\n{_PARA}"},
    ]


# ---------------------------------------------------------------------------
# Section events from the chunker
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chunker_collects_section_events_with_levels_and_pages():
    _, _, events = pipeline_mod.build_parent_child_chunks(_pages_with_headings(), "DOC1")
    titled = [e for e in events if e["title"]]
    assert [(e["title"], e["level"], e["page_start"]) for e in titled] == [
        ("Chapter One", 1, 1),
        ("Section 1.1", 2, 2),
        ("Detail 1.1.1", 3, 2),
        ("Chapter Two", 1, 3),
    ]


@pytest.mark.unit
def test_chunker_preamble_before_first_heading_gets_untitled_section():
    _, _, events = pipeline_mod.build_parent_child_chunks(_pages_with_headings(), "DOC1")
    assert events[0]["title"] == ""
    assert events[0]["level"] == 1
    assert len(events[0]["parent_chunk_ids"]) > 0


@pytest.mark.unit
def test_chunker_section_parent_ids_reference_real_parents():
    parents, _, events = pipeline_mod.build_parent_child_chunks(_pages_with_headings(), "DOC1")
    parent_ids = {p["id"] for p in parents}
    collected = [pid for e in events for pid in e["parent_chunk_ids"]]
    assert len(collected) == len(parents)
    assert set(collected) == parent_ids


@pytest.mark.unit
def test_chunker_no_headings_yields_single_untitled_event():
    pages = [{"page": 1, "text": _PARA}]
    _, _, events = pipeline_mod.build_parent_child_chunks(pages, "DOC1")
    assert len(events) == 1
    assert events[0]["title"] == ""


@pytest.mark.unit
def test_chunker_spurious_headings_do_not_create_sections():
    pages = [{"page": 1, "text": f"# 32\n\n# P R O L O G U E\n\n# Real Heading\n\n{_PARA}"}]
    _, _, events = pipeline_mod.build_parent_child_chunks(pages, "DOC1")
    assert [e["title"] for e in events] == ["Real Heading"]


# ---------------------------------------------------------------------------
# build_section_tree
# ---------------------------------------------------------------------------

def _event(title: str, level: int, page: int, ids: list[str] | None = None) -> dict:
    return {
        "title": title,
        "level": level,
        "page_start": page,
        "page_end": page,
        "parent_chunk_ids": ids or [],
    }


@pytest.mark.unit
def test_tree_nests_by_heading_level():
    tree = pipeline_mod.build_section_tree([
        _event("Ch 1", 1, 1),
        _event("Sec 1.1", 2, 2),
        _event("Sub 1.1.1", 3, 3),
        _event("Sec 1.2", 2, 4),
        _event("Ch 2", 1, 5),
    ])
    assert [n["title"] for n in tree] == ["Ch 1", "Ch 2"]
    ch1 = tree[0]
    assert [n["title"] for n in ch1["children"]] == ["Sec 1.1", "Sec 1.2"]
    assert [n["title"] for n in ch1["children"][0]["children"]] == ["Sub 1.1.1"]


@pytest.mark.unit
def test_tree_page_end_propagates_from_descendants():
    tree = pipeline_mod.build_section_tree([
        _event("Ch 1", 1, 1),
        _event("Sec 1.1", 2, 2),
        {"title": "Sub", "level": 3, "page_start": 3, "page_end": 9, "parent_chunk_ids": []},
        _event("Ch 2", 1, 10),
    ])
    assert tree[0]["page_end"] == 9
    assert tree[0]["children"][0]["page_end"] == 9


@pytest.mark.unit
def test_tree_skipped_level_attaches_to_nearest_shallower_ancestor():
    # "### Sub" directly under "# Ch" (no ## in between) must still nest.
    tree = pipeline_mod.build_section_tree([
        _event("Ch", 1, 1),
        _event("Sub", 3, 2),
        _event("Sec", 2, 3),
    ])
    ch = tree[0]
    assert [n["title"] for n in ch["children"]] == ["Sub", "Sec"]


@pytest.mark.unit
def test_tree_empty_events_gives_empty_tree():
    assert pipeline_mod.build_section_tree([]) == []


@pytest.mark.unit
def test_tree_end_to_end_from_chunker():
    parents, _, events = pipeline_mod.build_parent_child_chunks(_pages_with_headings(), "DOC1")
    tree = pipeline_mod.build_section_tree(events)
    # Preamble + Chapter One + Chapter Two at root level.
    assert [n["title"] for n in tree] == ["", "Chapter One", "Chapter Two"]
    ch1 = tree[1]
    assert ch1["children"][0]["title"] == "Section 1.1"
    assert ch1["children"][0]["children"][0]["title"] == "Detail 1.1.1"
    # Chapter One spans through its subsections' pages.
    assert ch1["page_start"] == 1
    assert ch1["page_end"] >= 2
    # Every parent chunk is anchored somewhere in the tree.
    def _collect(nodes):
        for n in nodes:
            yield from n["parent_chunk_ids"]
            yield from _collect(n["children"])
    assert set(_collect(tree)) == {p["id"] for p in parents}


# ---------------------------------------------------------------------------
# build_section_events_from_parents (backfill for legacy documents)
# ---------------------------------------------------------------------------

def _row(pid: str, section: str, page: int) -> SimpleNamespace:
    return SimpleNamespace(id=pid, citation_section=section, citation_page=page)


@pytest.mark.unit
def test_backfill_groups_consecutive_sections():
    rows = [
        _row("d_p0000", "Intro", 1),
        _row("d_p0001", "Intro", 2),
        _row("d_p0002", "Mining", 5),
        _row("d_p0003", "Intro", 9),  # same title later → new run, not merged
    ]
    events = pipeline_mod.build_section_events_from_parents(rows)
    assert [(e["title"], e["page_start"], e["page_end"]) for e in events] == [
        ("Intro", 1, 2),
        ("Mining", 5, 5),
        ("Intro", 9, 9),
    ]
    assert events[0]["parent_chunk_ids"] == ["d_p0000", "d_p0001"]
    assert all(e["level"] == 1 for e in events)


@pytest.mark.unit
def test_backfill_handles_missing_section_and_page():
    rows = [_row("d_p0000", None, None), _row("d_p0001", "", 0)]
    events = pipeline_mod.build_section_events_from_parents(rows)
    assert len(events) == 1
    assert events[0]["title"] == ""
    assert events[0]["parent_chunk_ids"] == ["d_p0000", "d_p0001"]


@pytest.mark.unit
def test_backfill_empty_rows():
    assert pipeline_mod.build_section_events_from_parents([]) == []
