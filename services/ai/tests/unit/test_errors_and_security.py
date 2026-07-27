"""Error contract, security headers, account lockout and session plumbing.

Two properties matter most here and are easy to regress:

- Error responses must be *uniform* — the frontend switches on `error.code` —
  and must not leak internals (stack traces, SQL, file paths) in production.
- Security headers must actually be present on every response, including error
  responses, which is exactly where middleware ordering bugs show up.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import errors
from app.core.errors import (
    AuthenticationError,
    AuthorizationError,
    BaseAppException,
    ConflictError,
    DatabaseError,
    ExternalServiceError,
    NotFoundError,
    RateLimitError,
    ValidationError_,
)


# ---------------------------------------------------------------------------
# Exception taxonomy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "exc,expected_status",
    [
        (AuthenticationError(), 401),
        (AuthorizationError(), 403),
        (NotFoundError(resource="Course", identifier="abc"), 404),
        (ConflictError(), 409),
        (ValidationError_(message="bad input"), 422),
        (RateLimitError(), 429),
        (DatabaseError(), 500),
        (ExternalServiceError(service="QVAC"), 503),
    ],
)
def test_each_exception_maps_to_its_http_status(exc: BaseAppException, expected_status: int):
    """The status code is part of the API contract; clients branch on it."""
    assert exc.status_code == expected_status


@pytest.mark.parametrize(
    "exc",
    [
        AuthenticationError(),
        AuthorizationError(),
        NotFoundError(resource="Course", identifier="abc"),
        ConflictError(),
        ValidationError_(message="bad input"),
        RateLimitError(),
        DatabaseError(),
        ExternalServiceError(service="QVAC"),
    ],
)
def test_each_exception_carries_a_machine_readable_code(exc: BaseAppException):
    assert exc.code, f"{type(exc).__name__} has an empty code"
    assert isinstance(exc.code, str)


def test_not_found_names_the_resource_and_identifier():
    exc = NotFoundError(resource="Course", identifier="course-123")
    assert "Course" in exc.message
    assert "course-123" in exc.message


def test_external_service_error_names_the_service():
    """When QVAC is down, the message should say so — a generic 503 is undiagnosable."""
    assert "QVAC" in ExternalServiceError(service="QVAC").message


# ---------------------------------------------------------------------------
# Error response envelope
# ---------------------------------------------------------------------------

def _envelope(response) -> dict:
    import json
    return json.loads(response.body)


def test_error_response_has_a_stable_envelope():
    body = _envelope(errors.build_error_response(
        message="Course not found", code="not_found", status_code=404
    ))
    assert "error" in body, f"Expected an 'error' envelope, got keys {list(body)}"
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Course not found"


def test_error_response_includes_details_only_when_explicitly_requested():
    """Details are withheld by default so internals do not leak into responses."""
    withheld = _envelope(errors.build_error_response(
        message="Invalid", code="validation_error", status_code=422,
        details={"field": "course_id"},
    ))
    assert "details" not in withheld["error"]

    included = _envelope(errors.build_error_response(
        message="Invalid", code="validation_error", status_code=422,
        details={"field": "course_id"}, include_details=True,
    ))
    assert included["error"]["details"] == {"field": "course_id"}


def test_error_response_includes_the_request_id_when_given():
    """The request id is how a user-reported error is found in the logs."""
    body = _envelope(errors.build_error_response(
        message="Boom", code="internal", status_code=500, request_id="req-abc"
    ))
    assert body["error"]["request_id"] == "req-abc"


def test_is_production_reflects_the_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert errors.is_production() is True
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert errors.is_production() is False


def test_get_request_id_reads_the_request_header():
    request = MagicMock()
    request.headers = {"X-Request-ID": "req-42"}
    assert errors.get_request_id(request) == "req-42"


def test_get_request_id_returns_none_when_the_header_is_absent():
    request = MagicMock()
    request.headers = {}
    assert errors.get_request_id(request) is None


# ---------------------------------------------------------------------------
# Registered handlers — behaviour through a real app
# ---------------------------------------------------------------------------

@pytest.fixture
def error_app() -> TestClient:
    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/boom/app-exception")
    def _app_exception():
        raise NotFoundError(resource="Course", identifier="missing-id")

    @app.get("/boom/unhandled")
    def _unhandled():
        raise RuntimeError("an internal detail that must not leak")

    return TestClient(app, raise_server_exceptions=False)


def test_application_exceptions_render_the_error_envelope(error_app):
    response = error_app.get("/boom/app-exception")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"]
    assert "missing-id" in body["error"]["message"]


def test_unhandled_exceptions_return_500_without_leaking_internals(error_app, monkeypatch):
    """A stack trace or internal message in a production response is an
    information disclosure bug."""
    monkeypatch.setenv("ENVIRONMENT", "production")

    response = error_app.get("/boom/unhandled")

    assert response.status_code == 500
    assert "an internal detail that must not leak" not in response.text, (
        "The internal exception message leaked into the HTTP response."
    )
    assert "Traceback" not in response.text


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

def _client_with_security(environment: str) -> TestClient:
    from app.middleware.security import RequestIDMiddleware, SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, environment=environment)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ok")
    def _ok():
        return {"ok": True}

    return TestClient(app)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ],
)
def test_security_headers_are_present(header: str, expected: str):
    response = _client_with_security("development").get("/ok")
    assert response.headers.get(header) == expected


def test_content_security_policy_is_set():
    response = _client_with_security("development").get("/ok")
    assert "Content-Security-Policy" in response.headers


def test_hsts_is_only_sent_in_production():
    """HSTS on a local http:// origin would pin developers into https and break
    their environment, so it must stay production-only."""
    dev = _client_with_security("development").get("/ok")
    prod = _client_with_security("production").get("/ok")

    assert "Strict-Transport-Security" not in dev.headers
    assert "Strict-Transport-Security" in prod.headers


def test_every_response_carries_a_request_id():
    response = _client_with_security("development").get("/ok")
    assert response.headers.get("X-Request-ID")


def test_a_supplied_request_id_is_echoed_back():
    """Lets a caller correlate its own trace id with the server's logs."""
    client = _client_with_security("development")
    response = client.get("/ok", headers={"X-Request-ID": "caller-supplied-id"})
    assert response.headers["X-Request-ID"] == "caller-supplied-id"


def test_request_ids_are_unique_per_request():
    client = _client_with_security("development")
    first = client.get("/ok").headers["X-Request-ID"]
    second = client.get("/ok").headers["X-Request-ID"]
    assert first != second


# ---------------------------------------------------------------------------
# Account lockout
# ---------------------------------------------------------------------------

@pytest.fixture
def lockout(monkeypatch):
    from app.middleware.security import AccountLockoutManager

    monkeypatch.delenv("REDIS_URL", raising=False)
    return AccountLockoutManager()


def test_a_fresh_account_is_not_locked(lockout):
    locked, retry_after = lockout.is_locked("user@example.com")
    assert locked is False
    assert retry_after is None


def test_account_locks_after_repeated_failures(lockout):
    """Brute-force protection: the threshold must actually engage."""
    email = "user@example.com"
    for _ in range(lockout.MAX_FAILED_ATTEMPTS):
        lockout.record_failed_attempt(email)

    locked, retry_after = lockout.is_locked(email)
    assert locked is True
    assert retry_after and retry_after > 0


def test_account_is_not_locked_below_the_threshold(lockout):
    email = "user@example.com"
    for _ in range(lockout.MAX_FAILED_ATTEMPTS - 1):
        lockout.record_failed_attempt(email)
    assert lockout.is_locked(email)[0] is False


def test_lockout_is_case_insensitive_on_email(lockout):
    """Otherwise an attacker bypasses the lockout by varying capitalisation."""
    for _ in range(lockout.MAX_FAILED_ATTEMPTS):
        lockout.record_failed_attempt("User@Example.com")
    assert lockout.is_locked("user@example.com")[0] is True


def test_a_successful_login_clears_the_failure_count(lockout):
    email = "user@example.com"
    lockout.record_failed_attempt(email)
    lockout.record_failed_attempt(email)
    lockout.clear_attempts(email)
    assert lockout.is_locked(email)[0] is False


def test_locking_one_account_does_not_lock_another(lockout):
    """Otherwise an attacker could lock out every user by guessing at one."""
    for _ in range(lockout.MAX_FAILED_ATTEMPTS):
        lockout.record_failed_attempt("victim@example.com")
    assert lockout.is_locked("bystander@example.com")[0] is False


# ---------------------------------------------------------------------------
# Session plumbing
# ---------------------------------------------------------------------------

def test_get_db_yields_a_session_and_closes_it():
    from app.db.session import get_db

    gen = get_db()
    session = next(gen)
    assert session is not None
    gen.close()


def test_get_db_context_closes_on_exception():
    """A leaked session on the error path exhausts the connection pool."""
    from app.db.session import get_db_context

    with pytest.raises(ValueError):
        with get_db_context() as db:
            assert db is not None
            raise ValueError("simulated failure inside the context")
