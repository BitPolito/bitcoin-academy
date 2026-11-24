"""Unit tests for the QVAC call in app.services.document_service — issue #160.

_qvac_delete_workspace_chunks must resolve its endpoint through
app.services.qvac_router rather than a QVAC_SERVICE_URL env read baked in at
call time.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services import document_service, qvac_router


@pytest.mark.unit
def test_qvac_delete_workspace_chunks_resolves_retrieval_task_type():
    fake_route = qvac_router.Route(
        task_type="retrieval", target="local", base_url="http://diverging-local:9999", model="",
    )
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch.object(qvac_router, "resolve", return_value=fake_route) as mock_resolve, \
         patch("httpx.Client", return_value=mock_client):
        document_service._qvac_delete_workspace_chunks("COURSE1", "DOC1")

    mock_resolve.assert_called_once_with("retrieval")
    url = mock_client.delete.call_args[0][0]
    assert url == "http://diverging-local:9999/documents/DOC1"


@pytest.mark.unit
def test_qvac_delete_workspace_chunks_degrades_silently_on_http_error():
    import httpx

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.delete.side_effect = httpx.ConnectError("refused")

    with patch("httpx.Client", return_value=mock_client):
        # Must not raise.
        document_service._qvac_delete_workspace_chunks("COURSE1", "DOC1")
