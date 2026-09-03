"""Cursor pagination against data well beyond the MVP-sized fixtures."""
import uuid

import pytest

from app.core.config import create_access_token
from app.db.models import Course, CourseDocument, Section
from tests.conftest import make_user


@pytest.fixture
def auth_headers(db) -> dict[str, str]:
    user = make_user(db)
    role = getattr(user.role, "value", user.role)
    token = create_access_token(user.id, user.email, role)
    return {"Authorization": f"Bearer {token}"}


def _collect_pages(client, path: str, headers: dict[str, str], limit: int) -> list[dict]:
    items: list[dict] = []
    cursor = None
    while True:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        response = client.get(path, headers=headers, params=params)
        assert response.status_code == 200
        page = response.json()
        assert len(page["items"]) <= limit
        items.extend(page["items"])
        cursor = page["next_cursor"]
        assert page["has_more"] is (cursor is not None)
        if cursor is None:
            return items


@pytest.mark.integration
def test_courses_paginate_across_large_seed(client, db, auth_headers):
    section = Section(id=str(uuid.uuid4()), title="Pagination")
    db.add(section)
    expected_ids = []
    for index in range(65):
        course_id = f"00000000-0000-0000-0000-{index:012d}"
        expected_ids.append(course_id)
        db.add(Course(id=course_id, section_id=section.id, title=f"Course {index}"))
    db.commit()

    items = _collect_pages(client, "/api/courses", auth_headers, limit=17)

    assert [item["id"] for item in items] == expected_ids
    assert len({item["id"] for item in items}) == 65


@pytest.mark.integration
def test_course_cursor_does_not_duplicate_rows_after_concurrent_insert(client, db, auth_headers):
    section = Section(id=str(uuid.uuid4()), title="Concurrent pagination")
    db.add(section)
    for index in range(1, 6):
        db.add(
            Course(
                id=f"00000000-0000-0000-0000-{index:012d}",
                section_id=section.id,
                title=f"Course {index}",
            )
        )
    db.commit()

    first = client.get("/api/courses", headers=auth_headers, params={"limit": 2}).json()
    db.add(
        Course(
            id="00000000-0000-0000-0000-000000000000",
            section_id=section.id,
            title="Inserted concurrently",
        )
    )
    db.commit()
    remaining = []
    cursor = first["next_cursor"]
    while cursor:
        page = client.get(
            "/api/courses",
            headers=auth_headers,
            params={"limit": 2, "cursor": cursor},
        ).json()
        remaining.extend(page["items"])
        cursor = page["next_cursor"]

    ids = [item["id"] for item in first["items"] + remaining]
    assert len(ids) == len(set(ids)) == 5


@pytest.mark.integration
def test_documents_paginate_across_large_seed(client, db, auth_headers):
    section = Section(id=str(uuid.uuid4()), title="Pagination")
    course = Course(id=str(uuid.uuid4()), section_id=section.id, title="Large course")
    db.add_all([section, course])
    expected_ids = []
    for index in range(65):
        document_id = f"doc-{index:03d}"
        expected_ids.append(document_id)
        db.add(
            CourseDocument(
                id=document_id,
                course_id=course.id,
                filename=f"document-{index}.pdf",
                mime_type="application/pdf",
                size=index,
                created_at="2026-01-01 00:00:00",
            )
        )
    db.commit()

    items = _collect_pages(
        client, f"/api/courses/{course.id}/documents", auth_headers, limit=13
    )

    assert [item["id"] for item in items] == sorted(expected_ids, reverse=True)
    assert len({item["id"] for item in items}) == 65


@pytest.mark.integration
@pytest.mark.parametrize("path", ["/api/courses", "/api/courses/any/documents"])
def test_listing_page_size_is_capped(client, auth_headers, path):
    response = client.get(path, headers=auth_headers, params={"limit": 101})
    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.parametrize("path", ["/api/courses", "/api/courses/any/documents"])
def test_listing_rejects_invalid_cursor(client, auth_headers, path):
    response = client.get(path, headers=auth_headers, params={"cursor": "not-a-cursor"})
    assert response.status_code == 422
