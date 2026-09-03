import logging
import json
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Optional

import redis as _redis_module

logger = logging.getLogger(__name__)

_KEY_PREFIX = "bl:"
_CONSUMED_PREFIX = "rt:consumed:"
_FAMILY_PREFIX = "rt:family:"


class TokenBlacklist:
    """
    Redis-backed token blacklist for JWT revocation.

    Falls back to in-memory storage when REDIS_URL is not configured (dev only).
    """

    def __init__(self):
        self._redis: Optional[_redis_module.Redis] = None
        self._fallback: Dict[str, float] = {}
        self._consumed_fallback: Dict[str, tuple[float, float, str, dict]] = {}
        self._family_fallback: Dict[str, float] = {}
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
            for prefix in (_KEY_PREFIX, _CONSUMED_PREFIX, _FAMILY_PREFIX):
                for key in self._redis.scan_iter(f"{prefix}*"):
                    self._redis.delete(key)
        else:
            with self._lock:
                self._fallback.clear()
                self._consumed_fallback.clear()
                self._family_fallback.clear()
        logger.warning("Token blacklist cleared")

    def is_family_revoked(self, family_id: str) -> bool:
        if self._redis is not None:
            return bool(self._redis.exists(f"{_FAMILY_PREFIX}{family_id}"))
        with self._lock:
            expiry = self._family_fallback.get(family_id)
            if expiry is None:
                return False
            if expiry < datetime.now(timezone.utc).timestamp():
                del self._family_fallback[family_id]
                return False
            return True

    def is_refresh_token_consumed(self, token_id: str) -> bool:
        if self._redis is not None:
            return bool(self._redis.exists(f"{_CONSUMED_PREFIX}{token_id}"))
        with self._lock:
            record = self._consumed_fallback.get(token_id)
            return bool(record and record[0] >= datetime.now(timezone.utc).timestamp())

    def revoke_family(self, family_id: str, expires_at: datetime) -> None:
        ttl = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        if self._redis is not None:
            self._redis.setex(f"{_FAMILY_PREFIX}{family_id}", ttl, "1")
        else:
            with self._lock:
                self._family_fallback[family_id] = expires_at.timestamp()
        logger.warning("Refresh token family revoked: %s...", family_id[:8])

    def consume_refresh_token(
        self,
        token_id: str,
        family_id: str,
        expires_at: datetime,
        replacement: dict,
        grace_seconds: int,
    ) -> tuple[str, dict | None]:
        """Atomically consume a refresh token or classify its reuse.

        A concurrent retry inside the grace window receives the first rotation's
        response. A later reuse revokes the family.
        """
        now = datetime.now(timezone.utc).timestamp()
        ttl = max(1, int(expires_at.timestamp() - now))
        record = {
            "consumed_at": now,
            "family_id": family_id,
            "replacement": replacement,
        }

        if self._redis is not None:
            key = f"{_CONSUMED_PREFIX}{token_id}"
            created = self._redis.set(key, json.dumps(record), ex=ttl, nx=True)
            if created:
                self.add(token_id, expires_at)
                return "rotated", replacement
            raw = self._redis.get(key)
            existing = json.loads(raw) if raw else None
        else:
            with self._lock:
                existing_record = self._consumed_fallback.get(token_id)
                if existing_record is None or existing_record[0] < now:
                    self._consumed_fallback[token_id] = (
                        expires_at.timestamp(),
                        now,
                        family_id,
                        replacement,
                    )
                    self._fallback[token_id] = expires_at.timestamp()
                    return "rotated", replacement
                _, consumed_at, existing_family, stored_replacement = existing_record
                existing = {
                    "consumed_at": consumed_at,
                    "family_id": existing_family,
                    "replacement": stored_replacement,
                }

        if existing and existing.get("family_id") == family_id:
            if now - float(existing["consumed_at"]) <= grace_seconds:
                logger.info("Concurrent refresh replay accepted: %s...", token_id[:8])
                return "grace", existing["replacement"]

        self.revoke_family(family_id, expires_at)
        logger.warning("Refresh token reuse detected: %s...", token_id[:8])
        return "reused", None


token_blacklist = TokenBlacklist()


def blacklist_token(token_id: str, expires_at: datetime) -> None:
    token_blacklist.add(token_id, expires_at)


def is_token_blacklisted(token_id: str) -> bool:
    return token_blacklist.is_blacklisted(token_id)


def is_token_family_revoked(family_id: str) -> bool:
    return token_blacklist.is_family_revoked(family_id)


def is_refresh_token_consumed(token_id: str) -> bool:
    return token_blacklist.is_refresh_token_consumed(token_id)


def consume_refresh_token(
    token_id: str,
    family_id: str,
    expires_at: datetime,
    replacement: dict,
    grace_seconds: int,
) -> tuple[str, dict | None]:
    return token_blacklist.consume_refresh_token(
        token_id, family_id, expires_at, replacement, grace_seconds
    )
