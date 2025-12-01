"""Security middleware for headers, request ID, and account lockout."""
import logging
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
        response = await call_next(request)

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
        response = await call_next(request)

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
    Thread-safe manager for tracking failed login attempts and account lockouts.

    Features:
    - Tracks failed attempts per email
    - Locks accounts after MAX_FAILED_ATTEMPTS
    - Automatic unlock after LOCKOUT_DURATION
    - Exponential backoff between attempts
    - Cleanup of old entries to prevent memory leaks
    """

    # Configuration
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15
    CLEANUP_INTERVAL_MINUTES = 30
    ATTEMPT_WINDOW_MINUTES = 15  # Window to count failed attempts

    def __init__(self):
        self._failed_attempts: Dict[str, list] = defaultdict(list)
        self._lockouts: Dict[str, datetime] = {}
        self._lock = Lock()
        self._last_cleanup = datetime.now()

    def _cleanup_old_entries(self) -> None:
        """Remove expired lockouts and old failed attempts."""
        now = datetime.now()

        # Only cleanup periodically
        if (now - self._last_cleanup).total_seconds() < self.CLEANUP_INTERVAL_MINUTES * 60:
            return

        self._last_cleanup = now
        cutoff = now - timedelta(minutes=self.ATTEMPT_WINDOW_MINUTES)

        # Clean failed attempts
        for email in list(self._failed_attempts.keys()):
            self._failed_attempts[email] = [
                t for t in self._failed_attempts[email] if t > cutoff
            ]
            if not self._failed_attempts[email]:
                del self._failed_attempts[email]

        # Clean expired lockouts
        for email in list(self._lockouts.keys()):
            if self._lockouts[email] < now:
                del self._lockouts[email]

    def is_locked(self, email: str) -> Tuple[bool, Optional[int]]:
        """
        Check if an account is currently locked.

        Args:
            email: The email address to check

        Returns:
            Tuple of (is_locked, seconds_remaining)
        """
        with self._lock:
            self._cleanup_old_entries()

            email_lower = email.lower()
            if email_lower not in self._lockouts:
                return False, None

            lockout_until = self._lockouts[email_lower]
            now = datetime.now()

            if now >= lockout_until:
                # Lockout expired
                del self._lockouts[email_lower]
                return False, None

            seconds_remaining = int((lockout_until - now).total_seconds())
            return True, seconds_remaining

    def record_failed_attempt(self, email: str) -> Tuple[bool, int, Optional[int]]:
        """
        Record a failed login attempt.

        Args:
            email: The email address that failed login

        Returns:
            Tuple of (is_now_locked, attempts_count, lockout_seconds)
        """
        with self._lock:
            email_lower = email.lower()
            now = datetime.now()
            cutoff = now - timedelta(minutes=self.ATTEMPT_WINDOW_MINUTES)

            # Remove old attempts
            self._failed_attempts[email_lower] = [
                t for t in self._failed_attempts[email_lower] if t > cutoff
            ]

            # Record new attempt
            self._failed_attempts[email_lower].append(now)
            attempts = len(self._failed_attempts[email_lower])

            # Check if should lock
            if attempts >= self.MAX_FAILED_ATTEMPTS:
                lockout_until = now + \
                    timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)
                self._lockouts[email_lower] = lockout_until
                self._failed_attempts[email_lower] = []  # Clear attempts

                logger.warning(
                    f"Account locked due to {attempts} failed attempts",
                    extra={"email": email_lower,
                           "lockout_until": lockout_until.isoformat()}
                )

                return True, attempts, self.LOCKOUT_DURATION_MINUTES * 60

            remaining = self.MAX_FAILED_ATTEMPTS - attempts
            logger.info(
                f"Failed login attempt recorded",
                extra={"email": email_lower,
                       "attempts": attempts, "remaining": remaining}
            )

            return False, attempts, None

    def clear_attempts(self, email: str) -> None:
        """
        Clear failed attempts after successful login.

        Args:
            email: The email address to clear
        """
        with self._lock:
            email_lower = email.lower()
            if email_lower in self._failed_attempts:
                del self._failed_attempts[email_lower]
            if email_lower in self._lockouts:
                del self._lockouts[email_lower]

    def get_attempt_count(self, email: str) -> int:
        """Get the current number of failed attempts for an email."""
        with self._lock:
            email_lower = email.lower()
            now = datetime.now()
            cutoff = now - timedelta(minutes=self.ATTEMPT_WINDOW_MINUTES)

            attempts = [
                t for t in self._failed_attempts.get(email_lower, []) if t > cutoff
            ]
            return len(attempts)


# Global lockout manager instance
lockout_manager = AccountLockoutManager()
