"""Authentication security behaviour — lockout, revocation, and dev seeding.

These are the paths an attacker exercises, and the ones least likely to be hit
by ordinary manual testing: nobody logs in wrong five times by accident, and
nobody checks that a logged-out token really stopped working.

Follows the conventions in test_auth_api.py: module-level client, per-test
schema, rate limiting disabled so the lockout logic is what is under test
rather than the IP rate limiter.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.core.config import settings
from app.core.token_blacklist import token_blacklist
from app.db.models import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.middleware.security import lockout_manager

client = TestClient(app)

VALID_PASSWORD = "SecureP@ss123!"


@pytest.fixture(autouse=True)
def setup_database():
    limiter.enabled = False
    token_blacklist.clear()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    token_blacklist.clear()
    limiter.enabled = True


@pytest.fixture(autouse=True)
def clear_lockout_state():
    """Lockout state is process-global; leaking it between tests would make
    results depend on execution order."""
    lockout_manager.clear_attempts("locktest@example.com")
    lockout_manager.clear_attempts("other@example.com")
    yield
    lockout_manager.clear_attempts("locktest@example.com")
    lockout_manager.clear_attempts("other@example.com")


def _register(email: str, password: str = VALID_PASSWORD) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------------------
# Account lockout — brute-force resistance
# ---------------------------------------------------------------------------

class TestAccountLockout:

    def test_wrong_password_is_rejected(self):
        _register("locktest@example.com")
        assert _login("locktest@example.com", "WrongP@ssword1!").status_code >= 400

    def test_account_locks_after_repeated_failures(self):
        """Without this, an attacker can try passwords indefinitely."""
        _register("locktest@example.com")

        statuses = [
            _login("locktest@example.com", "WrongP@ssword1!").status_code
            for _ in range(lockout_manager.MAX_FAILED_ATTEMPTS + 1)
        ]

        assert 429 in statuses, (
            f"Account was never locked after {len(statuses)} failed logins. "
            f"Statuses: {statuses}"
        )

    def test_lockout_blocks_even_the_correct_password(self):
        """A lockout that the real password bypasses protects nothing: the
        attacker's eventual correct guess would still succeed."""
        _register("locktest@example.com")

        for _ in range(lockout_manager.MAX_FAILED_ATTEMPTS + 1):
            _login("locktest@example.com", "WrongP@ssword1!")

        response = _login("locktest@example.com", VALID_PASSWORD)
        assert response.status_code == 429, (
            f"Correct password succeeded ({response.status_code}) while the "
            f"account was locked."
        )

    def test_lockout_response_tells_the_user_when_to_retry(self):
        _register("locktest@example.com")
        for _ in range(lockout_manager.MAX_FAILED_ATTEMPTS + 1):
            _login("locktest@example.com", "WrongP@ssword1!")

        body = _login("locktest@example.com", VALID_PASSWORD).json()
        assert "minute" in str(body).lower(), (
            f"Lockout response gives the user no idea how long to wait: {body}"
        )

    def test_a_successful_login_clears_the_failure_count(self):
        """Otherwise occasional typos accumulate across weeks and lock out a
        legitimate user for no reason."""
        _register("locktest@example.com")

        for _ in range(lockout_manager.MAX_FAILED_ATTEMPTS - 1):
            _login("locktest@example.com", "WrongP@ssword1!")

        assert _login("locktest@example.com", VALID_PASSWORD).status_code == 200

        for _ in range(lockout_manager.MAX_FAILED_ATTEMPTS - 1):
            _login("locktest@example.com", "WrongP@ssword1!")
        assert _login("locktest@example.com", VALID_PASSWORD).status_code == 200

    def test_locking_one_account_does_not_lock_another(self):
        """Otherwise one attacker locks out every user in the system."""
        _register("locktest@example.com")
        _register("other@example.com")

        for _ in range(lockout_manager.MAX_FAILED_ATTEMPTS + 1):
            _login("locktest@example.com", "WrongP@ssword1!")

        assert _login("other@example.com", VALID_PASSWORD).status_code == 200


# ---------------------------------------------------------------------------
# Credential disclosure
# ---------------------------------------------------------------------------

class TestCredentialDisclosure:

    def test_login_failure_does_not_reveal_whether_the_account_exists(self):
        """Differing responses let an attacker enumerate registered emails."""
        _register("locktest@example.com")

        wrong_password = _login("locktest@example.com", "WrongP@ssword1!")
        unknown_account = _login("nosuchuser@example.com", "WrongP@ssword1!")

        assert wrong_password.status_code == unknown_account.status_code, (
            f"Status differs for existing vs unknown account "
            f"({wrong_password.status_code} vs {unknown_account.status_code}) — "
            f"this enables account enumeration."
        )
        assert wrong_password.json() == unknown_account.json(), (
            f"Response body differs for existing vs unknown account:\n"
            f"  existing: {wrong_password.json()}\n"
            f"  unknown:  {unknown_account.json()}"
        )

    def test_password_hash_is_never_returned(self):
        """A leaked hash is offline-crackable."""
        registered = _register("locktest@example.com")
        assert "password" not in str(registered).lower() or "password_hash" not in str(registered)

        token = registered["tokens"]["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        body = str(me.json())
        assert "password_hash" not in body
        assert VALID_PASSWORD not in body

    def test_registering_a_duplicate_email_is_rejected(self):
        _register("locktest@example.com")
        duplicate = client.post(
            "/api/auth/register",
            json={
                "email": "locktest@example.com",
                "password": VALID_PASSWORD,
                "display_name": "Impostor",
            },
        )
        assert duplicate.status_code >= 400
        assert duplicate.status_code != 201


# ---------------------------------------------------------------------------
# Token lifecycle
# ---------------------------------------------------------------------------

class TestTokenLifecycle:

    def test_me_identifies_the_token_holder(self):
        registered = _register("locktest@example.com")
        token = registered["tokens"]["access_token"]

        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["email"] == "locktest@example.com"

    def test_refresh_issues_a_usable_access_token(self):
        registered = _register("locktest@example.com")
        refresh_token = registered["tokens"]["refresh_token"]

        refreshed = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert refreshed.status_code == 200, refreshed.text

        new_access = refreshed.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"})
        assert me.status_code == 200

    def test_refresh_rotates_and_concurrent_retry_returns_same_tokens(self):
        registered = _register("locktest@example.com")
        original = registered["tokens"]["refresh_token"]

        first = client.post("/api/auth/refresh", json={"refresh_token": original})
        concurrent = client.post("/api/auth/refresh", json={"refresh_token": original})

        assert first.status_code == concurrent.status_code == 200
        assert concurrent.json() == first.json()
        assert first.json()["refresh_token"] != original

    def test_reuse_after_grace_revokes_the_entire_family(self, monkeypatch):
        registered = _register("locktest@example.com")
        original = registered["tokens"]["refresh_token"]
        first = client.post("/api/auth/refresh", json={"refresh_token": original})
        replacement = first.json()["refresh_token"]
        replacement_access = first.json()["access_token"]
        monkeypatch.setattr(settings, "REFRESH_TOKEN_GRACE_SECONDS", -1)

        reused = client.post("/api/auth/refresh", json={"refresh_token": original})
        family_member = client.post(
            "/api/auth/refresh", json={"refresh_token": replacement}
        )
        protected_request = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {replacement_access}"}
        )

        assert reused.status_code == 401
        assert family_member.status_code == 401
        assert protected_request.status_code == 401

    def test_an_access_token_cannot_be_used_to_refresh(self):
        """Token types must not be interchangeable: an access token leaked from
        a log would otherwise mint unlimited new sessions."""
        registered = _register("locktest@example.com")
        access_token = registered["tokens"]["access_token"]

        response = client.post("/api/auth/refresh", json={"refresh_token": access_token})

        assert response.status_code >= 400, (
            f"An access token was accepted at the refresh endpoint "
            f"(status {response.status_code})."
        )

    def test_logout_revokes_the_refresh_token(self):
        """The point of logout: the refresh token must stop working."""
        registered = _register("locktest@example.com")
        access_token = registered["tokens"]["access_token"]
        refresh_token = registered["tokens"]["refresh_token"]

        logout = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"refresh_token": refresh_token},
        )
        assert logout.status_code == 200, logout.text

        reused = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert reused.status_code >= 400, (
            f"A refresh token revoked by logout was still accepted "
            f"(status {reused.status_code})."
        )

    def test_garbage_refresh_token_is_rejected(self):
        assert client.post(
            "/api/auth/refresh", json={"refresh_token": "not-a-jwt"}
        ).status_code >= 400


# ---------------------------------------------------------------------------
# Registration input validation
# ---------------------------------------------------------------------------

class TestRegistrationValidation:

    @pytest.mark.parametrize(
        "password,reason",
        [
            ("short", "too short"),
            ("alllowercase123!", "no uppercase"),
            ("ALLUPPERCASE123!", "no lowercase"),
            ("NoDigitsHere!!!!", "no digit"),
            ("NoSpecialChar123", "no special character"),
            ("password", "common password"),
        ],
    )
    def test_weak_passwords_are_rejected(self, password: str, reason: str):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "weakpass@example.com",
                "password": password,
                "display_name": "Test",
            },
        )
        assert response.status_code >= 400, (
            f"A password with {reason} was accepted: {password!r}"
        )

    @pytest.mark.parametrize(
        "email",
        ["not-an-email", "@example.com", "user@", "", "user example@test.com"],
    )
    def test_malformed_emails_are_rejected(self, email: str):
        response = client.post(
            "/api/auth/register",
            json={"email": email, "password": VALID_PASSWORD, "display_name": "Test"},
        )
        assert response.status_code >= 400, f"Malformed email accepted: {email!r}"

    def test_registration_requires_every_field(self):
        assert client.post("/api/auth/register", json={}).status_code == 422


# ---------------------------------------------------------------------------
# Development seeding must never run in production
# ---------------------------------------------------------------------------

class TestDevelopmentSeeding:

    def test_seeding_is_refused_in_production(self, monkeypatch):
        """The dev accounts have published passwords (they are in the README).
        Seeding them into a production database would be a critical hole."""
        from app.core import config as config_module
        from app.db import init_db as init_db_module

        monkeypatch.setattr(config_module.settings, "ENVIRONMENT", "production", raising=False)

        created = init_db_module.seed_test_users(engine)

        session = SessionLocal()
        try:
            from app.db.models import User

            seeded = (
                session.query(User)
                .filter(User.email.in_(["admin@bitpolito.it", "student@bitpolito.it"]))
                .all()
            )
        finally:
            session.close()

        assert seeded == [], (
            "Development accounts with known passwords were seeded while "
            f"ENVIRONMENT=production: {[u.email for u in seeded]}"
        )
        assert created is None

    def test_seeding_creates_the_dev_accounts_in_development(self, monkeypatch):
        from app.core import config as config_module
        from app.db import init_db as init_db_module
        from app.db.models import User

        monkeypatch.setattr(config_module.settings, "ENVIRONMENT", "development", raising=False)

        init_db_module.seed_test_users(engine)

        session = SessionLocal()
        try:
            emails = {
                u.email
                for u in session.query(User)
                .filter(User.email.in_(["admin@bitpolito.it", "student@bitpolito.it"]))
                .all()
            }
        finally:
            session.close()

        assert emails == {"admin@bitpolito.it", "student@bitpolito.it"}

    def test_seeding_twice_does_not_duplicate_accounts(self, monkeypatch):
        """setup-dev.sh may be run repeatedly; a unique-constraint crash on the
        second run would be a poor first experience."""
        from app.core import config as config_module
        from app.db import init_db as init_db_module
        from app.db.models import User

        monkeypatch.setattr(config_module.settings, "ENVIRONMENT", "development", raising=False)

        init_db_module.seed_test_users(engine)
        init_db_module.seed_test_users(engine)

        session = SessionLocal()
        try:
            count = (
                session.query(User).filter(User.email == "admin@bitpolito.it").count()
            )
        finally:
            session.close()

        assert count == 1, f"Seeding twice produced {count} admin accounts"
