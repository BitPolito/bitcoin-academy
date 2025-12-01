"""Token blacklist for JWT revocation.

This module provides an in-memory token blacklist for revoking JWT tokens.
In production, this should be replaced with a Redis-based implementation
for persistence and distributed systems support.
"""
import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


class TokenBlacklist:
    """
    In-memory token blacklist for JWT revocation.

    Features:
    - Blacklist tokens by JTI (JWT ID) or raw token hash
    - Automatic cleanup of expired entries
    - Thread-safe operations

    Note: For production, consider using Redis for:
    - Persistence across restarts
    - Distributed deployment support
    - Better memory management
    """

    CLEANUP_INTERVAL_SECONDS = 300  # Cleanup every 5 minutes

    def __init__(self):
        # Store: token_id -> expiration_timestamp
        self._blacklist: Dict[str, float] = {}
        self._lock = Lock()
        self._last_cleanup = datetime.now(timezone.utc)

    def _cleanup_expired(self) -> None:
        """Remove expired tokens from the blacklist."""
        now = datetime.now(timezone.utc)

        # Only cleanup periodically
        if (now - self._last_cleanup).total_seconds() < self.CLEANUP_INTERVAL_SECONDS:
            return

        self._last_cleanup = now
        now_timestamp = now.timestamp()

        # Remove expired entries
        expired = [
            token_id for token_id, exp in self._blacklist.items()
            if exp < now_timestamp
        ]

        for token_id in expired:
            del self._blacklist[token_id]

        if expired:
            logger.debug(
                f"Cleaned up {len(expired)} expired tokens from blacklist")

    def add(self, token_id: str, expires_at: datetime) -> None:
        """
        Add a token to the blacklist.

        Args:
            token_id: The JTI or hashed token to blacklist
            expires_at: When the token would naturally expire
        """
        with self._lock:
            self._cleanup_expired()
            self._blacklist[token_id] = expires_at.timestamp()
            logger.info(f"Token blacklisted: {token_id[:8]}...")

    def is_blacklisted(self, token_id: str) -> bool:
        """
        Check if a token is blacklisted.

        Args:
            token_id: The JTI or hashed token to check

        Returns:
            True if the token is blacklisted
        """
        with self._lock:
            self._cleanup_expired()

            if token_id not in self._blacklist:
                return False

            # Check if still valid (not expired)
            exp = self._blacklist[token_id]
            if exp < datetime.now(timezone.utc).timestamp():
                # Expired, remove and return False
                del self._blacklist[token_id]
                return False

            return True

    def remove(self, token_id: str) -> bool:
        """
        Remove a token from the blacklist.

        Args:
            token_id: The JTI or hashed token to remove

        Returns:
            True if the token was in the blacklist
        """
        with self._lock:
            if token_id in self._blacklist:
                del self._blacklist[token_id]
                return True
            return False

    def size(self) -> int:
        """Get the current number of blacklisted tokens."""
        with self._lock:
            self._cleanup_expired()
            return len(self._blacklist)

    def clear(self) -> None:
        """Clear all blacklisted tokens (useful for testing)."""
        with self._lock:
            self._blacklist.clear()
            logger.warning("Token blacklist cleared")


# Global token blacklist instance
token_blacklist = TokenBlacklist()


def blacklist_token(token_id: str, expires_at: datetime) -> None:
    """Convenience function to blacklist a token."""
    token_blacklist.add(token_id, expires_at)


def is_token_blacklisted(token_id: str) -> bool:
    """Convenience function to check if a token is blacklisted."""
    return token_blacklist.is_blacklisted(token_id)
