"""Integration tests for DELETE /courses/{id} and certificate revocation — P4."""
from unittest.mock import patch

import pytest

from app.core.config import create_access_token
from app.db.models import Certificate, Course, UserRole
from tests.conftest import make_course_with_lessons, make_user


def _auth(user_id: str, role: str = "student") -> dict:
    token = create_access_token(user_id, "u@test.com", role)
    return {"Authorization": f"Bearer {token}"}


class TestDeleteCourse:
    @pytest.mark.integration
    def test_delete_requires_auth(self, client, db):
        course, _ = make_course_with_lessons(db)
        resp = client.delete(f"/api/courses/{course.id}")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_delete_rejects_student_role(self, client, db):
        user = make_user(db, role=UserRole.STUDENT)
        course, _ = make_course_with_lessons(db)
        resp = client.delete(
            f"/api/courses/{course.id}",
            headers=_auth(user.id, "student"),
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_delete_allows_instructor(self, client, db):
        user = make_user(db, role=UserRole.INSTRUCTOR)
        course, lessons = make_course_with_lessons(db)

        with patch("app.services.document_service._qvac_delete_workspace_chunks"):
            resp = client.delete(
                f"/api/courses/{course.id}",
                headers=_auth(user.id, "instructor"),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Course deleted"
        assert "counts" in body
        assert body["counts"]["lessons"] == len(lessons)

        # Soft-deleted — no longer returned by GET
        get_resp = client.get(f"/api/courses/{course.id}")
        assert get_resp.status_code == 404

    @pytest.mark.integration
    def test_delete_returns_404_for_unknown_course(self, client, db):
        import uuid

        user = make_user(db, role=UserRole.ADMIN)
        resp = client.delete(
            f"/api/courses/{uuid.uuid4()}",
            headers=_auth(user.id, "admin"),
        )
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_delete_revokes_certificates_not_deletes(self, client, db):
        import uuid

        user = make_user(db, role=UserRole.ADMIN)
        course, _ = make_course_with_lessons(db)
        cert = Certificate(
            id=str(uuid.uuid4()), user_id=user.id, course_id=course.id, code="ZZZ999",
            verification_hash="zzz-hash", revoked=False,
        )
        db.add(cert)
        db.commit()

        with patch("app.services.document_service._qvac_delete_workspace_chunks"):
            resp = client.delete(
                f"/api/courses/{course.id}",
                headers=_auth(user.id, "admin"),
            )
        assert resp.status_code == 200

        db.refresh(cert)
        assert cert.revoked is True

        verify_resp = client.get(f"/api/certificates/verify/{cert.code}")
        assert verify_resp.json()["valid"] is False


class TestRevokeCertificate:
    @pytest.mark.integration
    def test_revoke_requires_auth(self, client, db):
        resp = client.post("/api/admin/certificates/some-id/revoke")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_revoke_rejects_non_admin(self, client, db):
        user = make_user(db, role=UserRole.INSTRUCTOR)
        resp = client.post(
            "/api/admin/certificates/some-id/revoke",
            headers=_auth(user.id, "instructor"),
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_revoke_returns_404_for_unknown_certificate(self, client, db):
        user = make_user(db, role=UserRole.ADMIN)
        resp = client.post(
            "/api/admin/certificates/nonexistent-id/revoke",
            headers=_auth(user.id, "admin"),
        )
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_revoke_sets_revoked_true(self, client, db):
        import uuid

        admin = make_user(db, role=UserRole.ADMIN)
        student = make_user(db, role=UserRole.STUDENT)
        course, _ = make_course_with_lessons(db)
        cert = Certificate(
            id=str(uuid.uuid4()), user_id=student.id, course_id=course.id, code="REV001",
            verification_hash="rev-hash", revoked=False,
        )
        db.add(cert)
        db.commit()

        resp = client.post(
            f"/api/admin/certificates/{cert.id}/revoke",
            headers=_auth(admin.id, "admin"),
        )
        assert resp.status_code == 200
        assert resp.json()["revoked"] is True

        db.refresh(cert)
        assert cert.revoked is True
        assert cert.revoked_at is not None
