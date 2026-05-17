"""Certificates API controller - issue and verify certificates."""
from typing import Optional

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
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
    summary="List certificates for the current user",
)
def list_my_certificates(
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(status_code=200, content=[])


@router.get(
    "/certificates/verify/{code}",
    summary="Publicly verify a certificate by its unique code",
)
def verify_certificate(
    code: str = Path(..., description="Certificate code"),
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"valid": False, "code": code, "course_id": None, "issued_at": None},
    )
