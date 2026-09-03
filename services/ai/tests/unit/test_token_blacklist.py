"""Token blacklist — JWT revocation.

Exercised against the in-memory fallback, which is the path taken whenever
REDIS_URL is unset. That is also the dev default, so this is the behaviour most
contributors actually run.

Revocation is a security control: a failure here means a logged-out token keeps
working.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.token_blacklist import TokenBlacklist


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def setex(self, key, ttl, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def exists(self, key):
        return key in self.values

    def scan_iter(self, pattern):
        prefix = pattern.removesuffix("*")
        return (key for key in list(self.values) if key.startswith(prefix))

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)


@pytest.fixture
def blacklist(monkeypatch) -> TokenBlacklist:
    """A blacklist with no Redis configured, so the in-memory path is used."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    return TokenBlacklist()


def _future(minutes: int = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _past(minutes: int = 5) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def test_unknown_token_is_not_blacklisted(blacklist):
    assert blacklist.is_blacklisted("never-seen") is False


def test_added_token_is_blacklisted(blacklist):
    blacklist.add("token-1", _future())
    assert blacklist.is_blacklisted("token-1") is True


def test_blacklisting_one_token_does_not_affect_another(blacklist):
    blacklist.add("token-1", _future())
    assert blacklist.is_blacklisted("token-2") is False


def test_expired_entry_stops_being_blacklisted(blacklist):
    """Entries expire with the token itself; keeping them forever would leak memory."""
    blacklist.add("expired", _past())
    assert blacklist.is_blacklisted("expired") is False


def test_expired_entry_is_purged_on_lookup(blacklist):
    blacklist.add("expired", _past())
    blacklist.is_blacklisted("expired")
    assert blacklist.size() == 0


def test_remove_returns_true_for_a_known_token(blacklist):
    blacklist.add("token-1", _future())
    assert blacklist.remove("token-1") is True
    assert blacklist.is_blacklisted("token-1") is False


def test_remove_returns_false_for_an_unknown_token(blacklist):
    assert blacklist.remove("never-added") is False


def test_size_counts_only_unexpired_entries(blacklist):
    blacklist.add("live-1", _future())
    blacklist.add("live-2", _future())
    blacklist.add("dead", _past())
    assert blacklist.size() == 2


def test_clear_empties_the_blacklist(blacklist):
    blacklist.add("token-1", _future())
    blacklist.add("token-2", _future())
    blacklist.clear()
    assert blacklist.size() == 0
    assert blacklist.is_blacklisted("token-1") is False


def test_readding_a_token_refreshes_its_expiry(blacklist):
    blacklist.add("token-1", _past())
    blacklist.add("token-1", _future())
    assert blacklist.is_blacklisted("token-1") is True


def test_falls_back_to_memory_when_redis_is_unreachable(monkeypatch):
    """A Redis outage must not take authentication down with it — the blacklist
    degrades to in-memory rather than raising at construction."""
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390/0")  # nothing listening

    bl = TokenBlacklist()

    bl.add("token-1", _future())
    assert bl.is_blacklisted("token-1") is True


def test_rotation_state_survives_store_restart(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis = FakeRedis()
    first_process = TokenBlacklist()
    first_process._redis = redis
    replacement = {"access_token": "a", "refresh_token": "r"}

    status, _ = first_process.consume_refresh_token(
        "token-1", "family-1", _future(), replacement, grace_seconds=10
    )

    restarted_process = TokenBlacklist()
    restarted_process._redis = redis
    replay_status, replay = restarted_process.consume_refresh_token(
        "token-1", "family-1", _future(), {"different": True}, grace_seconds=10
    )
    restarted_process.revoke_family("family-1", _future())
    third_process = TokenBlacklist()
    third_process._redis = redis

    assert status == "rotated"
    assert replay_status == "grace"
    assert replay == replacement
    assert third_process.is_family_revoked("family-1")
