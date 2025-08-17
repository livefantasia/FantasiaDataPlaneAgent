"""Test utilities and fixtures for DataPlane Agent tests."""

import asyncio
from typing import Any, Dict, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from config import ApplicationConfig
from main import create_app


@pytest.fixture
def mock_config() -> ApplicationConfig:
    """Create a mock configuration for testing."""
    import os
    # Set environment variables for testing
    os.environ["SERVER_ID"] = "test-server-001"
    os.environ["SERVER_REGION"] = "test-region"
    os.environ["SERVER_PORT"] = "8081"
    os.environ["SERVER_HOST"] = "0.0.0.0"
    os.environ["REDIS_HOST"] = "localhost"
    os.environ["REDIS_PORT"] = "6379"
    os.environ["REDIS_DB"] = "0"
    os.environ["CONTROL_PLANE_URL"] = "https://test-control.example.com"
    os.environ["CONTROL_PLANE_API_KEY"] = "test-api-key"
    os.environ["LOG_LEVEL"] = "DEBUG"
    
    return ApplicationConfig(
        control_plane_url=os.environ["CONTROL_PLANE_URL"],
        control_plane_api_key=os.environ["CONTROL_PLANE_API_KEY"],
        server_id=os.environ["SERVER_ID"],
        server_region=os.environ["SERVER_REGION"]
    )


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create a mock Redis client."""
    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.is_connected = AsyncMock(return_value=True)
    mock_client.push_message = AsyncMock()
    mock_client.pop_message = AsyncMock(return_value=None)
    mock_client.reliable_pop_message = AsyncMock(return_value=None)
    mock_client.acknowledge_message = AsyncMock()
    mock_client.move_to_dead_letter_queue = AsyncMock()
    mock_client.get_queue_length = AsyncMock(return_value=0)
    mock_client.get_all_queue_lengths = AsyncMock(return_value={})
    mock_client.set_cache = AsyncMock()
    mock_client.get_cache = AsyncMock(return_value=None)
    mock_client.delete_cache = AsyncMock()
    mock_client.health_check = AsyncMock(return_value={"status": "healthy"})
    return mock_client


@pytest.fixture
def mock_control_plane_client() -> AsyncMock:
    """Create a mock ControlPlane client."""
    mock_client = AsyncMock()
    mock_client.start = AsyncMock()
    mock_client.stop = AsyncMock()
    mock_client.submit_usage_records = AsyncMock(return_value={"status": "success"})
    mock_client.notify_session_start = AsyncMock(return_value={"status": "success"})
    mock_client.request_quota_refresh = AsyncMock(return_value={"status": "success"})
    mock_client.notify_session_complete = AsyncMock(return_value={"status": "success"})
    mock_client.register_server = AsyncMock(return_value={"status": "success"})
    mock_client.send_heartbeat = AsyncMock(return_value={"status": "success"})
    mock_client.poll_commands = AsyncMock(return_value=[])
    mock_client.report_command_result = AsyncMock(return_value={"status": "success"})
    mock_client.fetch_jwt_public_keys = AsyncMock(return_value={"keys": []})
    mock_client.health_check = AsyncMock(return_value={"status": "healthy"})
    return mock_client


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_client() -> Any:
    """Create a test HTTP client."""
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


def create_mock_usage_record() -> Dict[str, Any]:
    """Create a mock usage record for testing."""
    return {
        "api_session_id": "test-session-001",
        "customer_id": "test-customer-001",
        "product_code": "SPEECH_TO_TEXT_STANDARD",
        "connection_duration_seconds": 120.5,
        "data_bytes_processed": 1024000,
        "audio_duration_seconds": 110.0,
        "request_timestamp": "2024-01-15T10:00:00Z",
        "response_timestamp": "2024-01-15T10:02:00Z",
    }


def create_mock_session_event() -> Dict[str, Any]:
    """Create a mock session lifecycle event for testing."""
    return {
        "api_session_id": "test-session-001",
        "customer_id": "test-customer-001",
        "event_type": "start",
        "timestamp": "2024-01-15T10:00:00Z",
        "metadata": {"test": "data"},
    }


def create_mock_quota_request() -> Dict[str, Any]:
    """Create a mock quota refresh request for testing."""
    return {
        "api_session_id": "test-session-001",
        "customer_id": "test-customer-001",
        "current_usage": 50.0,
        "requested_quota": 100.0,
        "timestamp": "2024-01-15T10:00:00Z",
    }
