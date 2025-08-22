"""Tests for ControlPlane client shutdown notification functionality."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Import from the parent directory structure 
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from services.control_plane_client import ControlPlaneClient
from config import ApplicationConfig


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock(spec=ApplicationConfig)
    config.control_plane_url = "https://control.fantasia.ai"
    config.control_plane_timeout = 30
    config.control_plane_api_key = "test-api-key"
    config.api_key_header = "X-API-Key"
    config.app_version = "1.0.0"
    config.control_plane_retry_attempts = 2
    return config


@pytest.fixture
def control_plane_client(mock_config):
    """Create a ControlPlane client for testing."""
    return ControlPlaneClient(mock_config)


@pytest.mark.asyncio
async def test_notify_server_shutdown_success(control_plane_client):
    """Test successful server shutdown notification."""
    # Mock the HTTP client
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "success": True,
        "message": "Server shutdown notification received"
    }
    mock_client.request.return_value = mock_response
    control_plane_client._client = mock_client

    # Call the shutdown notification method
    server_id = "test-server-001"
    result = await control_plane_client.notify_server_shutdown(
        server_id=server_id,
        correlation_id="test-correlation-123"
    )

    # Verify the result
    assert result["success"] is True
    assert "shutdown notification received" in result["message"]

    # Verify the HTTP request was made correctly
    mock_client.request.assert_called_once_with(
        method="POST",
        url="/api/v1/servers/test-server-001/shutdown",
        json={},
        params=None,
        headers={"X-Correlation-ID": "test-correlation-123"}
    )


@pytest.mark.asyncio
async def test_notify_server_shutdown_without_correlation_id(control_plane_client):
    """Test server shutdown notification without correlation ID."""
    # Mock the HTTP client
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "success": True,
        "message": "Server shutdown notification received"
    }
    mock_client.request.return_value = mock_response
    control_plane_client._client = mock_client

    # Call the shutdown notification method without correlation ID
    server_id = "test-server-002"
    result = await control_plane_client.notify_server_shutdown(server_id=server_id)

    # Verify the result
    assert result["success"] is True

    # Verify the HTTP request was made without correlation ID header
    mock_client.request.assert_called_once_with(
        method="POST",
        url="/api/v1/servers/test-server-002/shutdown",
        json={},
        params=None,
        headers={}
    )


@pytest.mark.asyncio
async def test_notify_server_shutdown_client_not_started(control_plane_client):
    """Test shutdown notification when client is not started."""
    # Ensure client is not started
    control_plane_client._client = None

    # Call the shutdown notification method
    server_id = "test-server-003"
    
    with pytest.raises(RuntimeError, match="ControlPlane client not started"):
        await control_plane_client.notify_server_shutdown(server_id=server_id)


@pytest.mark.asyncio
async def test_notify_server_shutdown_with_retry_on_server_error(control_plane_client):
    """Test shutdown notification with retry on server error."""
    from httpx import HTTPStatusError, Response, Request
    
    # Mock the HTTP client
    mock_client = AsyncMock()
    control_plane_client._client = mock_client

    # Create mock response for server error (500)
    mock_error_response = MagicMock(spec=Response)
    mock_error_response.status_code = 500
    mock_request = MagicMock(spec=Request)
    
    # Create mock success response
    mock_success_response = AsyncMock()
    mock_success_response.json.return_value = {
        "success": True,
        "message": "Server shutdown notification received"
    }

    # First call fails with 500, second call succeeds
    mock_client.request.side_effect = [
        HTTPStatusError("Server error", request=mock_request, response=mock_error_response),
        mock_success_response
    ]

    # Call the shutdown notification method
    server_id = "test-server-004"
    result = await control_plane_client.notify_server_shutdown(server_id=server_id)

    # Verify the result (should succeed after retry)
    assert result["success"] is True

    # Verify that the request was called twice (original + 1 retry)
    assert mock_client.request.call_count == 2


@pytest.mark.asyncio
async def test_notify_server_shutdown_no_retry_on_client_error(control_plane_client):
    """Test shutdown notification with no retry on client error (4xx)."""
    from httpx import HTTPStatusError, Response, Request
    
    # Mock the HTTP client
    mock_client = AsyncMock()
    control_plane_client._client = mock_client

    # Create mock response for client error (404)
    mock_error_response = MagicMock(spec=Response)
    mock_error_response.status_code = 404
    mock_request = MagicMock(spec=Request)
    
    # First call fails with 404
    mock_client.request.side_effect = HTTPStatusError(
        "Not found", request=mock_request, response=mock_error_response
    )

    # Call the shutdown notification method
    server_id = "test-server-005"
    
    with pytest.raises(HTTPStatusError):
        await control_plane_client.notify_server_shutdown(server_id=server_id)

    # Verify that the request was called only once (no retry on 4xx)
    assert mock_client.request.call_count == 1
