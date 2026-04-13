"""Unit tests for progress_service — no HTTP, direct service calls."""
import pytest

from app.services import progress_service
from tests.conftest import make_course_with_lessons, make_user


@pytest.mark.unit
def test_get_course_progress_default(db):
    """A user with no activity gets 0% progress."""
    user = make_user(db)
    course, _ = make_course_with_lessons(db, n_lessons=2)

    result = progress_service.get_course_progress(db, user.id, course.id)

    assert result.percent == 0
    assert result.status == "not_started"
    assert result.lesson_count == 2
    assert result.completed_count == 0


@pytest.mark.unit
def test_update_lesson_progress_in_progress(db):
    """Marking a lesson as in_progress updates lesson and course progress."""
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    result = progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "in_progress"
    )

    assert result.lesson_progress.status == "in_progress"
    assert result.course_progress.status == "in_progress"
    assert result.course_progress.percent == 0  # not completed yet
    assert result.new_badges == []


@pytest.mark.unit
def test_update_lesson_progress_completed(db):
    """Completing a lesson recalculates course percent and awards lesson badge."""
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    result = progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "completed"
    )

    assert result.lesson_progress.status == "completed"
    assert result.course_progress.percent == 50
    assert result.course_progress.completed_count == 1
    # First lesson completion → lesson_complete badge
    assert len(result.new_badges) == 1
    assert result.new_badges[0].slug == "lesson_complete"


@pytest.mark.unit
def test_lesson_badge_awarded_only_once(db):
    """lesson_complete badge is not awarded a second time."""
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    # Complete first lesson → badge awarded
    progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "completed"
    )

    # Complete second lesson → badge NOT awarded again
    result = progress_service.update_lesson_progress(
        db, user.id, lessons[1].id, course.id, "completed"
    )

    lesson_badges = [b for b in result.new_badges if b.slug == "lesson_complete"]
    assert lesson_badges == []


@pytest.mark.unit
def test_course_completion_awards_course_badge(db):
    """Completing all lessons awards course_complete badge and sets percent=100."""
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=2)

    progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "completed"
    )
    result = progress_service.update_lesson_progress(
        db, user.id, lessons[1].id, course.id, "completed"
    )

    assert result.course_progress.percent == 100
    assert result.course_progress.status == "completed"
    course_badges = [b for b in result.new_badges if b.slug == "course_complete"]
    assert len(course_badges) == 1


@pytest.mark.unit
def test_course_badge_awarded_only_once(db):
    """course_complete badge is not awarded twice."""
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=1)

    # Complete the only lesson → course badge awarded
    progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "completed"
    )

    # Mark as in_progress then completed again
    progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "in_progress"
    )
    result = progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "completed"
    )

    course_badges = [b for b in result.new_badges if b.slug == "course_complete"]
    assert course_badges == []


@pytest.mark.unit
def test_update_saves_score(db):
    """Score is stored in lesson progress."""
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=1)

    result = progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "completed", score=85
    )

    assert result.lesson_progress.last_score == 85


@pytest.mark.unit
def test_list_badges_returns_defaults(db):
    """list_badges returns at least the two seeded default badges."""
    badges = progress_service.list_badges(db)
    slugs = {b.slug for b in badges}
    assert "lesson_complete" in slugs
    assert "course_complete" in slugs


@pytest.mark.unit
def test_get_user_badges_empty(db):
    """A new user has no badges."""
    user = make_user(db)
    badges = progress_service.get_user_badges(db, user.id)
    assert badges == []


@pytest.mark.unit
def test_get_user_badges_after_completion(db):
    """After completing a lesson the user has one badge."""
    user = make_user(db)
    course, lessons = make_course_with_lessons(db, n_lessons=1)

    progress_service.update_lesson_progress(
        db, user.id, lessons[0].id, course.id, "completed"
    )

    badges = progress_service.get_user_badges(db, user.id)
    slugs = {b["badge"].slug for b in badges}
    # lesson + course badge (only 1 lesson → 100%)
    assert "lesson_complete" in slugs
    assert "course_complete" in slugs


@pytest.mark.unit
def test_course_with_no_lessons_is_zero_percent(db):
    """A course with no lessons has 0% progress and no division-by-zero error."""
    from app.db.models import Course, Section
    import uuid

    section = Section(id=str(uuid.uuid4()), title="S")
    db.add(section)
    course = Course(id=str(uuid.uuid4()), section_id=section.id, title="Empty")
    db.add(course)
    db.commit()

    user = make_user(db)
    result = progress_service.get_course_progress(db, user.id, course.id)

    assert result.percent == 0
    assert result.lesson_count == 0
