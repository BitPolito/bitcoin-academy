"""Certificates API — issue and verify course completion certificates."""
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import UserRole
from app.db.session import get_db
from app.middleware.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["Certificates"])

ISSUER_NAME = "BitPolito Academy"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CertificateOut(BaseModel):
    id: str
    course_id: str
    course_name: str
    issued_at: str
    code: str
    verify_url: str
    grade_pct: Optional[int] = None


class VerifyOut(BaseModel):
    valid: bool
    code: str
    course_name: Optional[str] = None
    issued_at: Optional[str] = None
    revoked: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_verify_hash(user_id: str, course_id: str, code: str) -> str:
    raw = f"{user_id}:{course_id}:{code}:{ISSUER_NAME}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue_certificate(db: Session, user_id: str, course_id: str, grade_pct: int) -> dict:
    from app.db.models import Certificate, Course

    existing = (
        db.query(Certificate)
        .filter_by(user_id=user_id, course_id=course_id, revoked=False)
        .first()
    )
    if existing:
        course = db.get(Course, course_id)
        return _to_dict(existing, course.title if course else course_id)

    code = uuid.uuid4().hex[:16].upper()
    verification_hash = _make_verify_hash(user_id, course_id, code)
    cert = Certificate(
        id=str(uuid.uuid4()),
        user_id=user_id,
        course_id=course_id,
        issued_at=datetime.now(timezone.utc).isoformat(),
        code=code,
        verification_hash=verification_hash,
        grade_pct=grade_pct,
        hours=20,
        issuer_name=ISSUER_NAME,
        revoked=False,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)

    course = db.get(Course, course_id)
    return _to_dict(cert, course.title if course else course_id)


def _to_dict(cert, course_name: str) -> dict:
    return {
        "id": cert.id,
        "course_id": cert.course_id,
        "course_name": course_name,
        "issued_at": cert.issued_at if isinstance(cert.issued_at, str) else cert.issued_at.isoformat(),
        "code": cert.code,
        "verify_url": f"/api/certificates/verify/{cert.code}",
        "grade_pct": cert.grade_pct,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/certificates/issue",
    summary="Issue a certificate for a completed course",
    status_code=status.HTTP_201_CREATED,
)
def issue_certificate(
    course_id: str = Path(..., description="Course ID"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    from app.db.models import UserCourseProgress

    progress = (
        db.query(UserCourseProgress)
        .filter_by(user_id=current_user.sub, course_id=course_id)
        .first()
    )
    if not progress or progress.percent < 100:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Course not yet completed. Finish all lessons to earn a certificate.",
        )

    cert = _issue_certificate(db, current_user.sub, course_id, grade_pct=progress.percent)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=cert)


@router.get(
    "/users/me/certificates",
    summary="List certificates for the current user",
)
def list_my_certificates(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    from app.db.models import Certificate, Course

    certs = (
        db.query(Certificate)
        .filter_by(user_id=current_user.sub, revoked=False)
        .order_by(Certificate.issued_at.desc())
        .all()
    )

    items = []
    for cert in certs:
        course = db.get(Course, cert.course_id)
        items.append(_to_dict(cert, course.title if course else cert.course_id))

    return JSONResponse(status_code=200, content={"items": items})


@router.get(
    "/certificates/verify/{code}",
    summary="Publicly verify a certificate by its unique code",
)
def verify_certificate(
    code: str = Path(..., description="Certificate verification code"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    from app.db.models import Certificate, Course

    cert = db.query(Certificate).filter_by(code=code).first()
    if not cert:
        return JSONResponse(
            status_code=200,
            content=VerifyOut(valid=False, code=code).model_dump(),
        )

    course = db.get(Course, cert.course_id)
    return JSONResponse(
        status_code=200,
        content=VerifyOut(
            valid=not cert.revoked,
            code=code,
            course_name=course.title if course else cert.course_id,
            issued_at=cert.issued_at if isinstance(cert.issued_at, str) else cert.issued_at.isoformat(),
            revoked=cert.revoked,
        ).model_dump(),
    )


@router.post(
    "/admin/certificates/{certificate_id}/revoke",
    summary="Revoke a certificate (admin only)",
)
def revoke_certificate(
    certificate_id: str = Path(..., description="Certificate ID"),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(CurrentUser(roles=[UserRole.ADMIN])),
) -> JSONResponse:
    from app.db.models import Certificate

    cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if cert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")

    if not cert.revoked:
        cert.revoked = True
        cert.revoked_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        db.refresh(cert)

    return JSONResponse(
        status_code=200,
        content={"id": cert.id, "revoked": cert.revoked, "revoked_at": cert.revoked_at},
    )
