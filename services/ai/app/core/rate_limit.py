"""Shared rate limiter instance.

Import from here to ensure a single Limiter is used across the application.
Avoids creating multiple independent rate limit counters.

Key function: uses the authenticated user's sub/user_id claim when a valid,
*signature-verified* Bearer token is present, so each user has an independent
quota regardless of shared IPs (classrooms, VPNs, NAT). Falls back to remote IP
for unauthenticated or invalid-token requests — a forged/unsigned token must not
be able to mint fresh rate-limit buckets or exhaust another user's quota, and
this key function runs before any route-level auth dependency.
"""
import logging

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import decode_token

logger = logging.getLogger(__name__)


def _get_user_or_ip(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = decode_token(auth[7:])
        if payload:
            uid = payload.get("sub") or payload.get("user_id")
            if uid:
                return f"user:{uid}"
    return get_remote_address(request)


limiter = Limiter(key_func=_get_user_or_ip)
