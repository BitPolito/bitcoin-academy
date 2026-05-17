"""Certificates API — coming soon placeholder."""
from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse

from app.middleware.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["Certificates"])

_COMING_SOON = "Certificate feature coming soon."


@router.get(
    "/users/me/certificates",
    summary="List certificates for the current user",
)
def list_my_certificates(
    _current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"items": [], "coming_soon": True, "message": _COMING_SOON},
    )


@router.get(
    "/certificates/verify/{code}",
    summary="Publicly verify a certificate by its unique code",
)
def verify_certificate(
    code: str = Path(..., description="Certificate code"),
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"valid": False, "code": code, "coming_soon": True, "message": _COMING_SOON},
    )
