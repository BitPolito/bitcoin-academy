"""Certificates API controller - issue and verify certificates."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel

from app.middleware.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["Certificates"])


class CertificateSummary(BaseModel):
    id: str
    course_id: str
    issued_at: str
    code: str
    grade_pct: Optional[int]
    hours: Optional[int]


class CertificateVerification(BaseModel):
    valid: bool
    course_id: Optional[str]
    issued_at: Optional[str]
    code: str


@router.get(
    "/users/me/certificates",
    response_model=List[CertificateSummary],
    summary="List certificates for the current user",
)
def list_my_certificates(
    _current_user: CurrentUser = Depends(get_current_user),
) -> List[CertificateSummary]:
    # TODO: implement once certificate_service is built
    return []


@router.get(
    "/certificates/verify/{code}",
    response_model=CertificateVerification,
    summary="Publicly verify a certificate by its unique code",
)
def verify_certificate(
    code: str = Path(..., description="Certificate code"),
) -> CertificateVerification:
    # TODO: implement certificate verification
    return CertificateVerification(valid=False, course_id=None, issued_at=None, code=code)
