"""Test utilities and fixtures for DataPlane Agent tests."""

import asyncio
import os
import sys
from typing import Any, AsyncGenerator, Dict, Generator
from unittest.mock import AsyncMock

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pytest_asyncio
from httpx import AsyncClient

from main import app as fastapi_app
from config import ApplicationConfig


@pytest.fixture(scope="session")
def mock_config() -> ApplicationConfig:
    """Create a mock configuration for testing."""
    import os
    # Set environment variables for testing
    os.environ["SERVER_ID"] = "test-server-001"
    os.environ["SERVER_REGION"] = "test-region"
    os.environ["CONTROL_PLANE_URL"] = "http://localhost:8080"
    os.environ["CONTROL_PLANE_API_KEY"] = "test-api-key"
    
    # Instantiate the config object, which will load from the environment
    return ApplicationConfig()


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
    asyncio.set_event_loop(loop)  # Set as the current event loop
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client for the app."""
    async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
        yield client


def create_mock_usage_record() -> Dict[str, Any]:
    """Create a mock usage record for testing."""
    return {
        "transaction_id": "txn-test-001",
        "api_session_id": "test-session-001",
        "customer_id": "test-customer-001",
        "product_code": "SPEECH_TRANSCRIPTION",
        "connection_duration_seconds": 120.5,
        "data_bytes_processed": 1024000,
        "audio_duration_seconds": 110.0,
        "request_count": 1,
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
