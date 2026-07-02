"""Unit tests for lesson_service — Phase 3 course builder.

All LLM calls mocked; uses in-memory SQLite for DB assertions.
"""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import (
    Base,
    Chapter,
    ChunkParent,
    Course,
    GenerationRun,
    GenerationRunStatus,
    Lesson,
    OptionChoice,
    Question,
    Quiz,
    QuizScope,
    Section,
)
from app.services.lesson_service import (
    CONTENT_PROMPT_VERSION,
    compute_content_hash,
    _load_context,
    _persist_quiz,
    process_lesson,
    publish_course,
)


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------

def _make_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

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
    return db, course


def _add_chapter(db, course_id, status="draft"):
    ch = Chapter(
        id=str(uuid.uuid4()),
        course_id=course_id,
        title="Chapter",
        order_index=0,
        status=status,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _add_lesson(db, chapter_id, source_refs=None, status="draft", content=""):
    ls = Lesson(
        id=str(uuid.uuid4()),
        chapter_id=chapter_id,
        title="Lesson",
        content=content,
        order_index=0,
        status=status,
        source_refs_json=json.dumps(source_refs) if source_refs is not None else None,
    )
    db.add(ls)
    db.commit()
    db.refresh(ls)
    return ls


def _add_parent(db, cid, course_id, doc_id="doc1", text="Bitcoin is X. " * 100):
    p = ChunkParent(
        id=cid,
        doc_id=doc_id,
        course_id=course_id,
        text=text,
        citation_section="Intro",
        citation_page=1,
    )
    db.add(p)
    db.commit()
    return p


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------

def test_compute_content_hash_deterministic():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    ls = _add_lesson(db, ch.id, source_refs=["c1", "c2"])
    h1 = compute_content_hash(ls)
    h2 = compute_content_hash(ls)
    assert h1 == h2
    assert len(h1) == 64  # SHA256 hex


def test_compute_content_hash_changes_with_refs():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    ls_a = _add_lesson(db, ch.id, source_refs=["c1"])
    ls_b = _add_lesson(db, ch.id, source_refs=["c2"])
    assert compute_content_hash(ls_a) != compute_content_hash(ls_b)


def test_compute_content_hash_order_independent():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    ls1 = _add_lesson(db, ch.id, source_refs=["c1", "c2"])
    ls2 = _add_lesson(db, ch.id, source_refs=["c2", "c1"])
    # sorted refs → same hash
    assert compute_content_hash(ls1) == compute_content_hash(ls2)


# ---------------------------------------------------------------------------
# _load_context
# ---------------------------------------------------------------------------

def test_load_context_returns_items():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    _add_parent(db, "p1", course.id, text="Bitcoin block chain.")
    _add_parent(db, "p2", course.id, text="Mining difficulty.")
    ls = _add_lesson(db, ch.id, source_refs=["p1", "p2"])
    ids, items = _load_context(ls, db)
    assert ids == ["p1", "p2"]
    assert len(items) == 2
    assert items[0]["label"] == "p1"
    assert "Bitcoin" in items[0]["text"]


def test_load_context_caps_at_max():
    from app.services.lesson_service import MAX_CONTEXT_CHUNKS
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    refs = [f"p{i}" for i in range(MAX_CONTEXT_CHUNKS + 2)]
    for r in refs:
        _add_parent(db, r, course.id)
    ls = _add_lesson(db, ch.id, source_refs=refs)
    ids, items = _load_context(ls, db)
    assert len(ids) <= MAX_CONTEXT_CHUNKS
    assert len(items) <= MAX_CONTEXT_CHUNKS


def test_load_context_empty_when_no_refs():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    ls = _add_lesson(db, ch.id, source_refs=None)
    ids, items = _load_context(ls, db)
    assert ids == []
    assert items == []


# ---------------------------------------------------------------------------
# _persist_quiz
# ---------------------------------------------------------------------------

def test_persist_quiz_creates_db_rows():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    ls = _add_lesson(db, ch.id)

    quiz_data = {
        "questions": [
            {
                "prompt": "What is Bitcoin?",
                "options": [
                    {"key": "A", "text": "A digital currency"},
                    {"key": "B", "text": "A database"},
                    {"key": "C", "text": "An email protocol"},
                    {"key": "D", "text": "A social network"},
                ],
                "correct_key": "A",
            }
        ]
    }
    quiz_id = _persist_quiz(ls, quiz_data, db)
    assert quiz_id is not None

    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    assert quiz is not None
    assert quiz.lesson_id == ls.id
    assert quiz.scope == QuizScope.LESSON

    questions = db.query(Question).filter(Question.quiz_id == quiz_id).all()
    assert len(questions) == 1

    opts = db.query(OptionChoice).filter(OptionChoice.question_id == questions[0].id).all()
    assert len(opts) == 4
    correct = [o for o in opts if o.is_correct]
    assert len(correct) == 1
    assert "A digital currency" in correct[0].label


def test_persist_quiz_replaces_existing():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    ls = _add_lesson(db, ch.id)

    qdata = {
        "questions": [
            {
                "prompt": "Q1",
                "options": [{"key": k, "text": f"opt{k}"} for k in ["A", "B", "C", "D"]],
                "correct_key": "A",
            }
        ]
    }
    id1 = _persist_quiz(ls, qdata, db)
    id2 = _persist_quiz(ls, qdata, db)

    # Second call replaced the first
    quizzes = db.query(Quiz).filter(Quiz.lesson_id == ls.id).all()
    assert len(quizzes) == 1
    assert quizzes[0].id == id2


# ---------------------------------------------------------------------------
# process_lesson — full pipeline (LLM mocked)
# ---------------------------------------------------------------------------

_CONTENT_RESULT = {
    "content": "Bitcoin is a decentralized currency [ref_1].",
    "objectives": ["Understand Bitcoin basics"],
    "glossary": [{"term": "Bitcoin", "definition": "A decentralized digital currency"}],
    "self_check": ["What is Bitcoin?", "Why is it decentralized?"],
}

_JUDGE_PASS = {"faithful": True, "issues": []}
_JUDGE_FAIL = {"faithful": False, "issues": ["Claim X not in source"]}

_QUIZ_RESULT = {
    "questions": [
        {
            "prompt": "What is Bitcoin?",
            "options": [{"key": k, "text": f"opt{k}"} for k in ["A", "B", "C", "D"]],
            "correct_key": "A",
        }
    ]
}


@pytest.mark.asyncio
async def test_process_lesson_published_when_faithful():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    _add_parent(db, "p1", course.id)
    ls = _add_lesson(db, ch.id, source_refs=["p1"])

    with patch(
        "app.services.lesson_service.generate_json", new_callable=AsyncMock
    ) as mock_gj, patch(
        "app.services.quiz_generation.generate_json", new_callable=AsyncMock
    ) as mock_quiz_gj:
        mock_gj.side_effect = [_CONTENT_RESULT, _JUDGE_PASS]
        mock_quiz_gj.return_value = _QUIZ_RESULT
        status = await process_lesson(ls.id, db)

    assert status == "published"
    db.refresh(ls)
    assert ls.status == "published"
    assert "Bitcoin" in ls.content
    assert "Learning Objectives" in ls.content
    assert ls.content_hash is not None

    # Quiz persisted
    quiz = db.query(Quiz).filter(Quiz.lesson_id == ls.id).first()
    assert quiz is not None


@pytest.mark.asyncio
async def test_process_lesson_needs_review_when_unfaithful():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    _add_parent(db, "p1", course.id)
    ls = _add_lesson(db, ch.id, source_refs=["p1"])

    with patch(
        "app.services.lesson_service.generate_json", new_callable=AsyncMock
    ) as mock_gj, patch(
        "app.services.quiz_generation.generate_json", new_callable=AsyncMock
    ) as mock_quiz_gj:
        mock_gj.side_effect = [_CONTENT_RESULT, _JUDGE_FAIL]
        mock_quiz_gj.return_value = _QUIZ_RESULT
        status = await process_lesson(ls.id, db)

    assert status == "needs_review"
    db.refresh(ls)
    assert ls.status == "needs_review"
    # Issues embedded in content
    assert "groundedness_issues" in ls.content


@pytest.mark.asyncio
async def test_process_lesson_skips_on_cache_hit():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    _add_parent(db, "p1", course.id)
    ls = _add_lesson(db, ch.id, source_refs=["p1"], content="Existing content")
    ls.content_hash = compute_content_hash(ls)
    db.commit()

    with patch(
        "app.services.lesson_service.generate_json", new_callable=AsyncMock
    ) as mock_gj:
        status = await process_lesson(ls.id, db)

    assert status == "skipped"
    mock_gj.assert_not_called()


@pytest.mark.asyncio
async def test_process_lesson_needs_review_when_no_source_refs():
    db, course = _make_db()
    ch = _add_chapter(db, course.id)
    ls = _add_lesson(db, ch.id, source_refs=None)

    with patch(
        "app.services.lesson_service.generate_json", new_callable=AsyncMock
    ) as mock_gj:
        status = await process_lesson(ls.id, db)

    assert status == "needs_review"
    mock_gj.assert_not_called()
    db.refresh(ls)
    assert ls.status == "needs_review"


# ---------------------------------------------------------------------------
# publish_course
# ---------------------------------------------------------------------------

def test_publish_course_publishes_all_lessons():
    db, course = _make_db()
    ch = _add_chapter(db, course.id, status="draft")
    ls1 = _add_lesson(db, ch.id, status="published", content="content")
    ls2 = _add_lesson(db, ch.id, status="published", content="content")

    result = publish_course(course.id, db)
    assert result["published_chapters"] == 1
    assert result["published_lessons"] == 2
    assert result["skipped_chapters"] == 0

    db.refresh(ch)
    assert ch.status == "published"


def test_publish_course_skips_chapters_with_needs_review():
    db, course = _make_db()
    ch = _add_chapter(db, course.id, status="draft")
    _add_lesson(db, ch.id, status="published", content="ok")
    _add_lesson(db, ch.id, status="needs_review", content="problematic")

    result = publish_course(course.id, db)
    assert result["published_chapters"] == 0
    assert result["skipped_chapters"] == 1

    db.refresh(ch)
    assert ch.status == "draft"


def test_publish_course_skips_already_published():
    db, course = _make_db()
    ch = _add_chapter(db, course.id, status="published")  # already published
    _add_lesson(db, ch.id, status="published", content="ok")

    result = publish_course(course.id, db)
    # Chapter already published → not in draft → not touched
    assert result["published_chapters"] == 0
