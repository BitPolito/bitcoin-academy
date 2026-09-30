"""Security middleware for headers, request ID, and account lockout."""
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Lock
from typing import Callable, Dict, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# =============================================================================
# Request ID Middleware
# =============================================================================

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a unique request ID to each request.

    The request ID is added to:
    - Request state (accessible via request.state.request_id)
    - Response headers (X-Request-ID)

    If the client provides an X-Request-ID header, it will be used instead.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Use client-provided ID or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state for access in handlers
        request.state.request_id = request_id

        # Process request
        response: Response = await call_next(request)

        # Add to response headers
        response.headers["X-Request-ID"] = request_id

        return response


# =============================================================================
# Security Headers Middleware
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy: default-src 'self'
    - Permissions-Policy: geolocation=(), microphone=(), camera=()

    In production, also adds:
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    """

    def __init__(self, app, environment: str = "development"):
        super().__init__(app)
        self.environment = environment

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)

        # Basic security headers (always applied)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # CSP - restrictive by default, can be adjusted per-route if needed
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        # Permissions Policy - disable sensitive features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        # HSTS - only in production (requires HTTPS)
        if self.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        return response


# =============================================================================
# Account Lockout Manager
# =============================================================================

class AccountLockoutManager:
    """
    Manager for tracking failed login attempts and account lockouts.

    Uses Redis when REDIS_URL is set so that state is shared across multiple
    workers and survives restarts. Falls back to in-memory when Redis is
    unavailable (not suitable for multi-worker production).
    """

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15
    ATTEMPT_WINDOW_MINUTES = 15
    CLEANUP_INTERVAL_MINUTES = 30  # in-memory fallback only

    def __init__(self):
        self._redis = None
        self._fallback_attempts: Dict[str, list] = defaultdict(list)
        self._fallback_lockouts: Dict[str, datetime] = {}
        self._lock = Lock()
        self._last_cleanup = datetime.now()
        self._init_redis()

    def _init_redis(self) -> None:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.warning(
                "AccountLockoutManager: REDIS_URL not set — using in-memory storage "
                "(not suitable for multi-worker production)"
            )
            return
        try:
            import redis as _redis_module
            client = _redis_module.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            logger.info("AccountLockoutManager: Redis backend connected")
        except Exception as exc:
            logger.warning(
                "AccountLockoutManager: Redis unavailable (%s) — falling back to in-memory", exc
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_locked(self, email: str) -> Tuple[bool, Optional[int]]:
        email_lower = email.lower()
        if self._redis is not None:
            ttl = self._redis.ttl(f"lockout:{email_lower}")
            return (True, int(ttl)) if ttl > 0 else (False, None)

        with self._lock:
            self._cleanup_old_entries()
            if email_lower not in self._fallback_lockouts:
                return False, None
            lockout_until = self._fallback_lockouts[email_lower]
            now = datetime.now()
            if now >= lockout_until:
                del self._fallback_lockouts[email_lower]
                return False, None
            return True, int((lockout_until - now).total_seconds())

    def record_failed_attempt(self, email: str) -> Tuple[bool, int, Optional[int]]:
        email_lower = email.lower()
        if self._redis is not None:
            attempts_key = f"attempts:{email_lower}"
            count = int(self._redis.incr(attempts_key))
            if count == 1:
                self._redis.expire(attempts_key, self.ATTEMPT_WINDOW_MINUTES * 60)
            if count >= self.MAX_FAILED_ATTEMPTS:
                self._redis.setex(
                    f"lockout:{email_lower}", self.LOCKOUT_DURATION_MINUTES * 60, "1"
                )
                self._redis.delete(attempts_key)
                logger.warning(
                    "Account locked after %d failed attempts: %s", count, email_lower
                )
                return True, count, self.LOCKOUT_DURATION_MINUTES * 60
            logger.info(
                "Failed login attempt recorded",
                extra={"email": email_lower, "attempts": count,
                       "remaining": self.MAX_FAILED_ATTEMPTS - count},
            )
            return False, count, None

        with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(minutes=self.ATTEMPT_WINDOW_MINUTES)
            self._fallback_attempts[email_lower] = [
                t for t in self._fallback_attempts[email_lower] if t > cutoff
            ]
            self._fallback_attempts[email_lower].append(now)
            attempts = len(self._fallback_attempts[email_lower])
            if attempts >= self.MAX_FAILED_ATTEMPTS:
                lockout_until = now + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)
                self._fallback_lockouts[email_lower] = lockout_until
                self._fallback_attempts[email_lower] = []
                logger.warning(
                    "Account locked after %d failed attempts: %s", attempts, email_lower
                )
                return True, attempts, self.LOCKOUT_DURATION_MINUTES * 60
            logger.info(
                "Failed login attempt recorded",
                extra={"email": email_lower, "attempts": attempts,
                       "remaining": self.MAX_FAILED_ATTEMPTS - attempts},
            )
            return False, attempts, None

    def clear_attempts(self, email: str) -> None:
        email_lower = email.lower()
        if self._redis is not None:
            self._redis.delete(f"attempts:{email_lower}", f"lockout:{email_lower}")
            return
        with self._lock:
            self._fallback_attempts.pop(email_lower, None)
            self._fallback_lockouts.pop(email_lower, None)

    def get_attempt_count(self, email: str) -> int:
        email_lower = email.lower()
        if self._redis is not None:
            count = self._redis.get(f"attempts:{email_lower}")
            return int(count) if count else 0
        with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(minutes=self.ATTEMPT_WINDOW_MINUTES)
            return sum(
                1 for t in self._fallback_attempts.get(email_lower, []) if t > cutoff
            )

    # ------------------------------------------------------------------
    # In-memory fallback helpers
    # ------------------------------------------------------------------

    def _cleanup_old_entries(self) -> None:
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() < self.CLEANUP_INTERVAL_MINUTES * 60:
            return
        self._last_cleanup = now
        cutoff = now - timedelta(minutes=self.ATTEMPT_WINDOW_MINUTES)
        for email in list(self._fallback_attempts.keys()):
            self._fallback_attempts[email] = [
                t for t in self._fallback_attempts[email] if t > cutoff
            ]
            if not self._fallback_attempts[email]:
                del self._fallback_attempts[email]
        for email in list(self._fallback_lockouts.keys()):
            if self._fallback_lockouts[email] < now:
                del self._fallback_lockouts[email]


# Global lockout manager instance
lockout_manager = AccountLockoutManager()


# =============================================================================
# Body Size Limit Middleware
# =============================================================================

class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds the limit before reading the body."""

    _MAX_BODY_BYTES = 52 * 1024 * 1024  # 52 MB — covers 50 MB file + multipart envelope

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self._MAX_BODY_BYTES:
            return Response(
                content='{"detail": "Request body exceeds the 50 MB size limit."}',
                status_code=413,
                media_type="application/json",
            )
        response: Response = await call_next(request)
        return response
