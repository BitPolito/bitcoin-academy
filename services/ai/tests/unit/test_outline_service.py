"""Unit tests for outline_service — map/reduce/persist pipeline.

All /generate_json calls are mocked; no LLM or DB I/O in these tests.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import (
    Chapter,
    ChunkParent,
    CourseDocument,
    DocumentStatus,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
)
from app.services import outline_service
from app.services.outline_service import (
    _collect_chunk_ids,
    _map_section,
    _reduce,
    _persist_outline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _doc(doc_id="doc1", status=DocumentStatus.READY, tree=None):
    d = MagicMock(spec=CourseDocument)
    d.id = doc_id
    d.status = status
    d.section_tree_json = json.dumps(tree) if tree is not None else None
    return d


def _parent(cid, text="word " * 50, section="Intro", page=1):
    p = MagicMock(spec=ChunkParent)
    p.id = cid
    p.text = text
    p.citation_section = section
    p.citation_page = page
    return p


_SECTION = {
    "title": "Chapter One",
    "level": 1,
    "page_start": 1,
    "page_end": 10,
    "parent_chunk_ids": ["p1", "p2"],
    "children": [
        {
            "title": "Section 1.1",
            "level": 2,
            "page_start": 2,
            "page_end": 5,
            "parent_chunk_ids": ["p3"],
            "children": [],
        }
    ],
}

_MAP_RESULT = {
    "lessons": [
        {
            "title": "What is Bitcoin",
            "key_concepts": ["blockchain", "mining"],
            "difficulty": "beginner",
        }
    ]
}

_REDUCE_RESULT = {
    "chapters": [
        {
            "title": "Introduction",
            "description": "Foundations",
            "lessons": [
                {
                    "title": "What is Bitcoin",
                    "description": "Overview",
                    "objectives": ["Understand basics"],
                    "candidate_indices": [0],
                }
            ],
        }
    ]
}


# ---------------------------------------------------------------------------
# _collect_chunk_ids
# ---------------------------------------------------------------------------

def test_collect_chunk_ids_bfs_order():
    ids = _collect_chunk_ids(_SECTION)
    # p1, p2 from the top level, then p3 from child
    assert ids == ["p1", "p2", "p3"]


def test_collect_chunk_ids_respects_max():
    ids = _collect_chunk_ids(_SECTION, max_chunks=2)
    assert ids == ["p1", "p2"]


def test_collect_chunk_ids_empty_section():
    ids = _collect_chunk_ids({"title": "Empty", "parent_chunk_ids": [], "children": []})
    assert ids == []


# ---------------------------------------------------------------------------
# _map_section
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_map_section_returns_candidates():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        _parent("p1"), _parent("p2"), _parent("p3")
    ]

    with patch(
        "app.services.outline_service.generate_json", new_callable=AsyncMock
    ) as mock_gj:
        mock_gj.return_value = _MAP_RESULT
        result = await _map_section(_SECTION, "doc1", db)

    assert len(result) == 1
    assert result[0]["title"] == "What is Bitcoin"
    assert result[0]["source_chunk_ids"] == ["p1", "p2", "p3"]
    assert result[0]["source_doc_id"] == "doc1"


@pytest.mark.asyncio
async def test_map_section_no_chunks_returns_empty():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    section_no_chunks = {**_SECTION, "parent_chunk_ids": [], "children": []}
    result = await _map_section(section_no_chunks, "doc1", db)
    assert result == []


# ---------------------------------------------------------------------------
# _reduce
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reduce_returns_outline():
    candidates = [
        {
            "title": "What is Bitcoin",
            "key_concepts": ["blockchain"],
            "difficulty": "beginner",
            "source_chunk_ids": ["p1"],
            "source_doc_id": "doc1",
        }
    ]

    with patch(
        "app.services.outline_service.generate_json", new_callable=AsyncMock
    ) as mock_gj:
        mock_gj.return_value = _REDUCE_RESULT
        result = await _reduce(candidates)

    assert "chapters" in result
    assert result["chapters"][0]["title"] == "Introduction"
    # Verify the prompt included the candidate title
    call_prompt = mock_gj.call_args[0][0]
    assert "What is Bitcoin" in call_prompt


# ---------------------------------------------------------------------------
# _persist_outline
# ---------------------------------------------------------------------------

def test_persist_outline_creates_chapters_and_lessons():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.models import Base, Course, Section

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    section = Section(id=str(uuid.uuid4()), title="Test")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), title="Test Course", section_id=section.id)
    db.add(course)
    db.commit()

    candidates = [
        {
            "title": "Candidate A",
            "key_concepts": ["bitcoin"],
            "difficulty": "beginner",
            "source_chunk_ids": ["chunk1", "chunk2"],
            "source_doc_id": "doc1",
        },
        {
            "title": "Candidate B",
            "key_concepts": ["mining"],
            "difficulty": "intermediate",
            "source_chunk_ids": ["chunk3"],
            "source_doc_id": "doc1",
        },
    ]
    outline = {
        "chapters": [
            {
                "title": "Chapter 1",
                "description": "First chapter",
                "lessons": [
                    {
                        "title": "Lesson 1",
                        "description": "First lesson",
                        "objectives": ["Learn basics"],
                        "candidate_indices": [0, 1],
                    }
                ],
            }
        ]
    }

    _persist_outline(course.id, outline, candidates, db)

    chapters = db.query(Chapter).filter(Chapter.course_id == course.id).all()
    assert len(chapters) == 1
    assert chapters[0].title == "Chapter 1"
    assert chapters[0].status == "draft"

    lessons = db.query(Lesson).filter(Lesson.chapter_id == chapters[0].id).all()
    assert len(lessons) == 1
    assert lessons[0].title == "Lesson 1"
    assert lessons[0].status == "draft"

    refs = json.loads(lessons[0].source_refs_json)
    # chunk1, chunk2 from candidate 0; chunk3 from candidate 1; deduped
    assert refs == ["chunk1", "chunk2", "chunk3"]

    db.close()


def test_persist_outline_replaces_previous_drafts():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.models import Base, Course, Section

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    section = Section(id=str(uuid.uuid4()), title="Test")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), title="Test Course", section_id=section.id)
    db.add(course)
    db.commit()

    # Pre-existing draft chapter
    old_chapter = Chapter(
        id=str(uuid.uuid4()),
        course_id=course.id,
        title="Old Chapter",
        order_index=0,
        status="draft",
    )
    db.add(old_chapter)
    db.commit()

    outline = {
        "chapters": [
            {
                "title": "New Chapter",
                "description": "",
                "lessons": [
                    {
                        "title": "New Lesson",
                        "description": "",
                        "objectives": ["obj"],
                        "candidate_indices": [0],
                    }
                ],
            }
        ]
    }
    candidates = [
        {
            "title": "X",
            "source_chunk_ids": ["c1"],
            "source_doc_id": "d1",
            "key_concepts": [],
            "difficulty": "beginner",
        }
    ]

    _persist_outline(course.id, outline, candidates, db)

    chapters = db.query(Chapter).filter(Chapter.course_id == course.id).all()
    assert len(chapters) == 1
    assert chapters[0].title == "New Chapter"

    db.close()


# ---------------------------------------------------------------------------
# generate_outline (full pipeline, integration with mocked LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_outline_full_pipeline():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.models import Base, Course, Section

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    section_row = Section(id=str(uuid.uuid4()), title="Test")
    db.add(section_row)
    course = Course(id=str(uuid.uuid4()), title="Course", section_id=section_row.id)
    db.add(course)
    db.commit()

    tree = [_SECTION]
    doc = CourseDocument(
        id=str(uuid.uuid4()),
        course_id=course.id,
        filename="test.pdf",
        size=1000,
        status=DocumentStatus.READY,
        section_tree_json=json.dumps(tree),
    )
    db.add(doc)

    run = GenerationRun(
        id=str(uuid.uuid4()),
        course_id=course.id,
        doc_ids_json=json.dumps([doc.id]),
        status=GenerationRunStatus.QUEUED,
        prompt_version="v1",
        created_at="2026-01-01T00:00:00",
    )
    db.add(run)

    parent = ChunkParent(
        id="p1",
        doc_id=doc.id,
        course_id=course.id,
        text="Bitcoin is a decentralized digital currency. " * 30,
        citation_section="Chapter One",
        citation_page=1,
    )
    db.add(parent)
    db.commit()

    with patch(
        "app.services.outline_service.generate_json", new_callable=AsyncMock
    ) as mock_gj:
        # First call = map, subsequent calls = reduce (only one doc/section here)
        mock_gj.side_effect = [_MAP_RESULT, _REDUCE_RESULT]
        await outline_service.generate_outline(
            course_id=course.id,
            doc_ids=[doc.id],
            db=db,
            run_id=run.id,
        )

    db.refresh(run)
    assert run.status == GenerationRunStatus.DONE
    assert run.finished_at is not None

    chapters = db.query(Chapter).filter(Chapter.course_id == course.id).all()
    assert len(chapters) == 1
    assert chapters[0].title == "Introduction"

    lessons = db.query(Lesson).all()
    assert len(lessons) == 1
    assert lessons[0].title == "What is Bitcoin"
    assert lessons[0].status == "draft"
    assert lessons[0].source_refs_json is not None

    db.close()


@pytest.mark.asyncio
async def test_generate_outline_marks_error_on_no_candidates():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.models import Base, Course, Section

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    section_row = Section(id=str(uuid.uuid4()), title="Test")
    db.add(section_row)
    course = Course(id=str(uuid.uuid4()), title="Course", section_id=section_row.id)
    db.add(course)
    db.commit()

    # Document with no parent chunks → no candidates
    doc = CourseDocument(
        id=str(uuid.uuid4()),
        course_id=course.id,
        filename="empty.pdf",
        size=100,
        status=DocumentStatus.READY,
        section_tree_json=None,  # forces rebuild → empty
    )
    db.add(doc)

    run = GenerationRun(
        id=str(uuid.uuid4()),
        course_id=course.id,
        doc_ids_json=json.dumps([doc.id]),
        status=GenerationRunStatus.QUEUED,
        prompt_version="v1",
        created_at="2026-01-01T00:00:00",
    )
    db.add(run)
    db.commit()

    await outline_service.generate_outline(
        course_id=course.id,
        doc_ids=[doc.id],
        db=db,
        run_id=run.id,
    )

    db.refresh(run)
    assert run.status == GenerationRunStatus.ERROR
    assert run.error_message is not None

    db.close()
