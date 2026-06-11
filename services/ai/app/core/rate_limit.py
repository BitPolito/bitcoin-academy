"""Shared rate limiter instance.

Import from here to ensure a single Limiter is used across the application.
Avoids creating multiple independent rate limit counters.

Key function: uses the authenticated user's sub/user_id claim when a valid
Bearer token is present, so each user has an independent quota regardless of
shared IPs (classrooms, VPNs, NAT). Falls back to remote IP for unauthenticated
requests.  The JWT is decoded without signature verification here because the
auth middleware has already validated it upstream; we only need the subject claim
as a stable bucket key.
"""
import logging

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def _get_user_or_ip(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(
                auth[7:],
                options={"verify_signature": False},
                algorithms=["HS256"],
            )
            uid = payload.get("sub") or payload.get("user_id")
            if uid:
                return f"user:{uid}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_user_or_ip)
