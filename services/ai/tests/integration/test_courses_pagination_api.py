"""Cursor pagination for GET /api/courses (issue #73).

Course.created_at didn't exist before this; these tests seed it explicitly
with distinct, increasing timestamps so page ordering is deterministic,
rather than relying on insertion order (which an ORDER BY-less query never
guaranteed, and even a correct ORDER BY shouldn't need to assume).
"""
import base64
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import create_access_token
from app.db.models import Course, Section
from tests.conftest import make_user

_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _b64(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _auth_header(user) -> dict:
    role = getattr(user.role, "value", user.role)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, role)}"}


def _seed_courses(db, n: int, start_offset: int = 0) -> list[Course]:
    """n courses, created one second apart starting at start_offset seconds
    past _BASE_TIME, oldest first in the DB but expected newest-first in the
    API response. start_offset lets a second seeding call produce courses
    strictly newer than an earlier call's."""
    section = Section(id=str(uuid.uuid4()), title="Pagination Test Section")
    db.add(section)
    db.flush()

    courses = []
    for i in range(n):
        course = Course(
            id=str(uuid.uuid4()),
            section_id=section.id,
            title=f"Course {start_offset + i:03d}",
            created_at=(_BASE_TIME + timedelta(seconds=start_offset + i)).isoformat(),
        )
        db.add(course)
        courses.append(course)
    db.commit()
    return courses


@pytest.mark.integration
class TestCoursesPagination:
    def test_first_page_returns_newest_first_with_cursor(self, client, db):
        user = make_user(db)
        # 60 courses: genuinely an order of magnitude above the 5-10 expected
        # at MVP (the issue's own acceptance criterion), not just "more".
        seeded = _seed_courses(db, 60)

        resp = client.get("/api/courses?limit=10", headers=_auth_header(user))

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 10
        assert body["has_more"] is True
        assert body["next_cursor"] is not None
        # Newest-first: the 60th seeded course (index 59, latest created_at) leads.
        assert body["items"][0]["title"] == seeded[59].title
        assert body["items"][9]["title"] == seeded[50].title

    def test_pages_traverse_every_course_without_duplicates_or_gaps(self, client, db):
        user = make_user(db)
        seeded = _seed_courses(db, 60)
        headers = _auth_header(user)

        seen_ids: list[str] = []
        cursor = None
        for _ in range(20):  # generous upper bound — real loop ends via has_more
            url = "/api/courses?limit=7"
            if cursor:
                url += f"&cursor={cursor}"
            resp = client.get(url, headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            seen_ids.extend(item["id"] for item in body["items"])
            if not body["has_more"]:
                assert body["next_cursor"] is None
                break
            cursor = body["next_cursor"]
        else:
            pytest.fail("pagination did not terminate within 20 pages")

        assert len(seen_ids) == len(set(seen_ids)) == 60
        assert set(seen_ids) == {c.id for c in seeded}

    def test_last_page_has_more_false_and_no_next_cursor(self, client, db):
        user = make_user(db)
        _seed_courses(db, 5)

        resp = client.get("/api/courses?limit=10", headers=_auth_header(user))

        body = resp.json()
        assert len(body["items"]) == 5
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_exact_limit_count_has_no_more_pages(self, client, db):
        """A page that comes back with exactly `limit` rows (not limit + 1)
        must not be mistaken for a full extra page — has_more must be False."""
        user = make_user(db)
        _seed_courses(db, 10)

        resp = client.get("/api/courses?limit=10", headers=_auth_header(user))

        body = resp.json()
        assert len(body["items"]) == 10
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    def test_tied_created_at_breaks_ties_by_id_deterministically(self, client, db):
        """Every backfilled pre-migration row shares one sentinel created_at —
        this is the only scenario that exercises the id tie-break branch of
        the keyset predicate, and it's exactly what those rows hit."""
        user = make_user(db)
        section = Section(id=str(uuid.uuid4()), title="Tie Section")
        db.add(section)
        db.flush()
        tied_at = _BASE_TIME.isoformat()
        courses = [
            Course(id=f"id-{i}", section_id=section.id, title=f"Tied {i}", created_at=tied_at)
            for i in range(5)
        ]
        db.add_all(courses)
        db.commit()
        expected_order = sorted((c.id for c in courses), reverse=True)

        first = client.get("/api/courses?limit=3", headers=_auth_header(user)).json()
        second = client.get(
            f"/api/courses?limit=3&cursor={first['next_cursor']}", headers=_auth_header(user),
        ).json()

        assert [c["id"] for c in first["items"]] == expected_order[:3]
        assert [c["id"] for c in second["items"]] == expected_order[3:]

    def test_inactive_courses_stay_excluded_across_pages(self, client, db):
        user = make_user(db)
        seeded = _seed_courses(db, 6)
        seeded[2].is_active = False  # a course in the middle of the range
        db.commit()

        first = client.get("/api/courses?limit=3", headers=_auth_header(user)).json()
        second = client.get(
            f"/api/courses?limit=3&cursor={first['next_cursor']}", headers=_auth_header(user),
        ).json()

        all_ids = {c["id"] for c in first["items"]} | {c["id"] for c in second["items"]}
        assert seeded[2].id not in all_ids
        assert len(all_ids) == 5

    @pytest.mark.parametrize(
        "cursor",
        [
            "not-valid-base64!!!",  # fails base64 decoding
            _b64("not json"),  # valid base64, invalid JSON
            _b64('{"created_at": "2026-01-01T00:00:00+00:00"}'),  # missing "id"
            _b64('["2026-01-01T00:00:00+00:00", "abc"]'),  # not a dict at all
            _b64('{"created_at": 123, "id": "abc"}'),  # wrong type for created_at
            _b64('{"created_at": "2026-01-01T00:00:00+00:00", "id": ["abc"]}'),  # wrong type for id
        ],
    )
    def test_malformed_cursor_shapes_return_422_not_500(self, client, db, cursor):
        user = make_user(db)

        resp = client.get(f"/api/courses?cursor={cursor}", headers=_auth_header(user))

        assert resp.status_code == 422

    def test_a_course_inserted_between_pages_does_not_shift_already_seen_rows(self, client, db):
        """The concurrent-insert case the issue specifically calls out for
        cursor (vs. offset) pagination: a new row created between two page
        requests must not cause the second page to repeat or skip a course
        the first page already returned."""
        user = make_user(db)
        seeded = _seed_courses(db, 10)
        headers = _auth_header(user)

        first = client.get("/api/courses?limit=5", headers=headers).json()
        assert [c["title"] for c in first["items"]] == [seeded[i].title for i in (9, 8, 7, 6, 5)]

        # A new, newest course is inserted after the first page was fetched —
        # with offset pagination this would shift index 4 (seeded[5]) back
        # into page 1's range and duplicate it on page 2.
        _seed_courses(db, 1, start_offset=1000)

        second = client.get(
            f"/api/courses?limit=5&cursor={first['next_cursor']}", headers=headers,
        ).json()
        assert [c["title"] for c in second["items"]] == [seeded[i].title for i in (4, 3, 2, 1, 0)]
