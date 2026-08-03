"""Upload queueing degradation — no ARQ worker pool configured.

The README documents a real symptom: "Document stuck in processing forever —
Redis not running -> ARQ worker not started." The half of that covered here
is the code path the symptom depends on: when `request.app.state.arq_pool` is
absent (the state this app is in before an ARQ worker connects, or when Redis
itself is unreachable), the upload endpoint must fall back to running the
pipeline via FastAPI's in-process BackgroundTasks rather than silently
dropping the document.

This does not reproduce the full "stuck forever" scenario — that requires a
job sitting unconsumed in a real Redis queue, which is an infrastructure state
rather than a code path. What is testable, and what this file covers, is that
the fallback branch itself is correct: no arq_pool configured must still
result in the pipeline running, not in a document silently left in
`processing`.
"""
from unittest.mock import patch

import pytest

from tests.conftest import make_course_with_lessons, make_user


def _auth_header(user) -> dict:
    from app.core.config import create_access_token
    role = getattr(user.role, "value", user.role)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, role)}"}


@pytest.mark.integration
def test_upload_falls_back_to_in_process_pipeline_when_no_arq_pool_is_configured(client, db):
    """No arq_pool on app.state (the default in these tests, and the real
    state of a deployment before the ARQ worker connects) must still run the
    ingestion pipeline — via BackgroundTasks — rather than leaving the
    document parked in `processing` with nothing ever picking it up."""
    course, _ = make_course_with_lessons(db)
    user = make_user(db)

    assert not hasattr(client.app.state, "arq_pool") or client.app.state.arq_pool is None, (
        "Test assumes no ARQ pool is configured; if this changes, the "
        "fallback branch below is no longer being exercised."
    )

    with patch("app.workers.pipeline.run") as mock_run:
        response = client.post(
            f"/api/courses/{course.id}/documents",
            files={"file": ("lecture.pdf", b"%PDF-1.4\nsome bytes", "application/pdf")},
            headers=_auth_header(user),
        )

    assert response.status_code == 201
    assert mock_run.called, (
        "Without an ARQ pool, the endpoint must fall back to "
        "background_tasks.add_task(pipeline.run, ...) — it did not run at all."
    )


@pytest.mark.integration
def test_upload_enqueues_via_arq_when_a_pool_is_configured(client, db):
    """The other side of the same branch: when arq_pool IS present, the job
    must be enqueued through it rather than run in-process — otherwise
    production deployments would silently stop using the queue."""
    from unittest.mock import AsyncMock

    course, _ = make_course_with_lessons(db)
    user = make_user(db)

    fake_pool = AsyncMock()
    client.app.state.arq_pool = fake_pool
    try:
        with patch("app.workers.pipeline.run") as mock_run:
            response = client.post(
                f"/api/courses/{course.id}/documents",
                files={"file": ("lecture.pdf", b"%PDF-1.4\nsome bytes", "application/pdf")},
                headers=_auth_header(user),
            )
    finally:
        client.app.state.arq_pool = None

    assert response.status_code == 201
    fake_pool.enqueue_job.assert_called_once()
    assert fake_pool.enqueue_job.call_args[0][0] == "ingest_document"
    mock_run.assert_not_called()
