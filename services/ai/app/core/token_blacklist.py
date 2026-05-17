import logging
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Optional

import redis as _redis_module

logger = logging.getLogger(__name__)

_KEY_PREFIX = "bl:"


class TokenBlacklist:
    """
    Redis-backed token blacklist for JWT revocation.

    Falls back to in-memory storage when REDIS_URL is not configured (dev only).
    """

    def __init__(self):
        self._redis: Optional[_redis_module.Redis] = None
        self._fallback: Dict[str, float] = {}
        self._lock = Lock()
        self._init_redis()

    def _init_redis(self) -> None:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.warning(
                "TokenBlacklist: REDIS_URL not set — using in-memory storage "
                "(not suitable for production)"
            )
            return
        try:
            client = _redis_module.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            logger.info("TokenBlacklist: Redis backend connected")
        except Exception as exc:
            logger.warning(
                "TokenBlacklist: Redis unavailable (%s) — falling back to in-memory storage",
                exc,
            )

    def add(self, token_id: str, expires_at: datetime) -> None:
        if self._redis is not None:
            ttl = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
            self._redis.setex(f"{_KEY_PREFIX}{token_id}", ttl, "1")
        else:
            with self._lock:
                self._fallback[token_id] = expires_at.timestamp()
        logger.info("Token blacklisted: %s...", token_id[:8])

    def is_blacklisted(self, token_id: str) -> bool:
        if self._redis is not None:
            return bool(self._redis.exists(f"{_KEY_PREFIX}{token_id}"))
        with self._lock:
            exp = self._fallback.get(token_id)
            if exp is None:
                return False
            if exp < datetime.now(timezone.utc).timestamp():
                del self._fallback[token_id]
                return False
            return True

    def remove(self, token_id: str) -> bool:
        if self._redis is not None:
            return bool(self._redis.delete(f"{_KEY_PREFIX}{token_id}"))
        with self._lock:
            return self._fallback.pop(token_id, None) is not None

    def size(self) -> int:
        if self._redis is not None:
            return sum(1 for _ in self._redis.scan_iter(f"{_KEY_PREFIX}*"))
        with self._lock:
            now = datetime.now(timezone.utc).timestamp()
            return sum(1 for exp in self._fallback.values() if exp >= now)

    def clear(self) -> None:
        if self._redis is not None:
            for key in self._redis.scan_iter(f"{_KEY_PREFIX}*"):
                self._redis.delete(key)
        else:
            with self._lock:
                self._fallback.clear()
        logger.warning("Token blacklist cleared")


token_blacklist = TokenBlacklist()


def blacklist_token(token_id: str, expires_at: datetime) -> None:
    token_blacklist.add(token_id, expires_at)


def is_token_blacklisted(token_id: str) -> bool:
    return token_blacklist.is_blacklisted(token_id)
