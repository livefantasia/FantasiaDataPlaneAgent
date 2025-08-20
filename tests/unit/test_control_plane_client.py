"""Unit tests for ControlPlane client service."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import HTTPStatusError, RequestError, Response

from models import (
    EnrichedUsageRecord,
    HeartbeatData,
    RemoteCommand,
    ServerRegistration,
    SessionLifecycleEvent,
    SessionEventType,
    QuotaRefreshRequest,
    CommandResult,
)
from models.enums import ProductCode
from services.control_plane_client import ControlPlaneClient


class TestControlPlaneClient:
    """Test cases for ControlPlaneClient class."""

    @pytest.fixture
    def control_plane_client(self, mock_config) -> ControlPlaneClient:
        """Create a ControlPlane client instance for testing."""
        return ControlPlaneClient(mock_config)

    @pytest.mark.asyncio
    async def test_start(self, control_plane_client, mock_config) -> None:
        """Test starting the ControlPlane client."""
        with patch("services.control_plane_client.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            await control_plane_client.start()
            
            assert control_plane_client._client == mock_client
            mock_client_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self, control_plane_client) -> None:
        """Test stopping the ControlPlane client."""
        mock_client = AsyncMock()
        control_plane_client._client = mock_client
        
        await control_plane_client.stop()
        
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_success(self, control_plane_client) -> None:
        """Test successful HTTP request."""
        from unittest.mock import Mock
        
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_response.raise_for_status.return_value = None
        
        mock_client.request = AsyncMock(return_value=mock_response)
        control_plane_client._client = mock_client
        
        result = await control_plane_client._make_request("GET", "/test")
        
        assert result == {"status": "success"}
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_http_error_4xx_no_retry(self, control_plane_client) -> None:
        """Test HTTP request with 4xx error (no retry)."""
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 400
        
        http_error = HTTPStatusError("Bad Request", request=AsyncMock(), response=mock_response)
        mock_client.request = AsyncMock(side_effect=http_error)
        control_plane_client._client = mock_client
        
        with pytest.raises(HTTPStatusError):
            await control_plane_client._make_request("GET", "/test")
        
        # Should not retry on 4xx errors
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_http_error_5xx_with_retry(self, control_plane_client, mock_config) -> None:
        """Test HTTP request with 5xx error (with retry)."""
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 500
        
        http_error = HTTPStatusError("Server Error", request=AsyncMock(), response=mock_response)
        mock_client.request = AsyncMock(side_effect=http_error)
        control_plane_client._client = mock_client
        
        with pytest.raises(HTTPStatusError):
            await control_plane_client._make_request("GET", "/test")
        
        # Should retry on 5xx errors
        assert mock_client.request.call_count == mock_config.control_plane_retry_attempts

    @pytest.mark.asyncio
    async def test_make_request_network_error_with_retry(self, control_plane_client, mock_config) -> None:
        """Test HTTP request with network error (with retry)."""
        mock_client = AsyncMock()
        network_error = RequestError("Network error", request=AsyncMock())
        mock_client.request = AsyncMock(side_effect=network_error)
        control_plane_client._client = mock_client
        
        with pytest.raises(RequestError):
            await control_plane_client._make_request("GET", "/test")
        
        # Should retry on network errors
        assert mock_client.request.call_count == mock_config.control_plane_retry_attempts

    @pytest.mark.asyncio
    async def test_submit_usage_records(self, control_plane_client) -> None:
        """Test submitting usage records."""
        usage_record = EnrichedUsageRecord(
            transaction_id="test-transaction-001",
            api_session_id="test-session",
            customer_id="test-customer",
            connection_duration_seconds=120.0,
            data_bytes_processed=1024,
            audio_duration_seconds=110.0,
            request_count=0,
            request_timestamp=datetime.utcnow(),
            response_timestamp=datetime.utcnow(),
            server_instance_id="test-server",
            api_server_region="test-region",
            agent_version="1.0.0"
        )
        
        expected_response = {"status": "success", "credits_consumed": 10}
        
        with patch.object(control_plane_client, "submit_usage_record", return_value=expected_response) as mock_submit:
            result = await control_plane_client.submit_usage_records([usage_record])
            
            expected_result = {"submitted_count": 1, "total_count": 1}
            assert result == expected_result
            mock_submit.assert_called_once_with(usage_record, None)

    @pytest.mark.asyncio
    async def test_notify_session_start(self, control_plane_client) -> None:
        """Test notifying session start."""
        session_event = SessionLifecycleEvent(
            api_session_id="test-session",
            customer_id="test-customer",
            event_type=SessionEventType.START
        )
        
        expected_response = {"status": "success"}
        
        with patch.object(control_plane_client, "_make_request", return_value=expected_response) as mock_request:
            result = await control_plane_client.notify_session_start(session_event)
            
            assert result == expected_response
            mock_request.assert_called_once_with(
                method="POST",
                endpoint="/api/v1/sessions/test-session/started",
                data={
                    "started_at": session_event.timestamp.isoformat(),
                    "client_info": session_event.metadata or {},
                    "timestamp": session_event.timestamp.isoformat(),
                },
                correlation_id=None
            )

    @pytest.mark.asyncio
    async def test_request_quota_refresh(self, control_plane_client) -> None:
        """Test requesting quota refresh."""
        quota_request = QuotaRefreshRequest(
            transaction_id="test-transaction-002",
            api_session_id="test-session",
            customer_id="test-customer",
            product_code=ProductCode.SPEECH_SYNTHESIS,
        )

        expected_response = {"status": "success", "additional_quota": 100.0}

        with patch.object(control_plane_client, "_make_request", return_value=expected_response) as mock_request:
            result = await control_plane_client.request_quota_refresh(quota_request)

            assert result == expected_response
            mock_request.assert_called_once_with(
                method="POST",
                endpoint="/api/v1/sessions/test-session/refresh",
                data={
                    "transaction_id": "test-transaction-002",
                    "product_code": "speech_synthesis",
                    "timestamp": quota_request.timestamp.isoformat(),
                },
                correlation_id=None,
            )

    @pytest.mark.asyncio
    async def test_notify_session_complete(self, control_plane_client) -> None:
        """Test notifying session completion."""
        session_event = SessionLifecycleEvent(
            api_session_id="test-session",
            customer_id="test-customer",
            event_type=SessionEventType.COMPLETE
        )
        
        expected_response = {"status": "success"}
        
        with patch.object(control_plane_client, "_make_request", return_value=expected_response) as mock_request:
            result = await control_plane_client.notify_session_complete(session_event)
            
            assert result == expected_response
            mock_request.assert_called_once_with(
                method="POST",
                endpoint="/api/v1/sessions/test-session/completed",
                data={
                    "completed_at": session_event.timestamp.isoformat(),
                    "disconnect_reason": session_event.disconnect_reason,
                    "final_usage_summary": session_event.final_usage_summary or {},
                    "timestamp": session_event.timestamp.isoformat(),
                },
                correlation_id=None
            )

    @pytest.mark.asyncio
    async def test_register_server(self, control_plane_client) -> None:
        """Test server registration."""
        registration_data = ServerRegistration(
            server_id="test-server",
            region="test-region",
            version="1.0.0",
            ip_address="192.168.1.100",
            port=8081,
            capabilities=["usage_tracking", "session_management"]
        )
        
        expected_response = {"status": "success", "server_registered": True}
        
        with patch.object(control_plane_client, "_make_request", return_value=expected_response) as mock_request:
            result = await control_plane_client.register_server(registration_data)
            
            assert result == expected_response
            mock_request.assert_called_once_with(
                method="POST",
                endpoint="/api/v1/servers/register",
                data=registration_data.model_dump(),
                correlation_id=None
            )

    @pytest.mark.asyncio
    async def test_send_heartbeat(self, control_plane_client) -> None:
        """Test sending heartbeat."""
        heartbeat_data = HeartbeatData(
            server_id="test-server",
            status="healthy",
            metrics={"uptime": 3600}
        )
        
        expected_response = {"status": "success"}
        
        with patch.object(control_plane_client, "_make_request", return_value=expected_response) as mock_request:
            result = await control_plane_client.send_heartbeat(heartbeat_data)
            
            assert result == expected_response
            mock_request.assert_called_once_with(
                method="PUT",
                endpoint="/api/v1/servers/test-server/heartbeat",
                data=heartbeat_data.model_dump(),
                correlation_id=None
            )

    @pytest.mark.asyncio
    async def test_poll_commands(self, control_plane_client) -> None:
        """Test polling for commands."""
        commands_response = {
            "commands": [
                {
                    "command_id": "cmd-001",
                    "command_type": "health_check",
                    "timestamp": "2024-01-15T10:00:00Z"
                }
            ]
        }
        
        with patch.object(control_plane_client, "_make_request", return_value=commands_response) as mock_request:
            result = await control_plane_client.poll_commands("test-server")
            
            assert len(result) == 1
            assert isinstance(result[0], RemoteCommand)
            assert result[0].command_id == "cmd-001"
            
            mock_request.assert_called_once_with(
                method="GET",
                endpoint="/api/v1/servers/test-server/commands",
                correlation_id=None
            )

    @pytest.mark.asyncio
    async def test_poll_commands_empty(self, control_plane_client) -> None:
        """Test polling for commands when none are available."""
        commands_response = {"commands": []}
        
        with patch.object(control_plane_client, "_make_request", return_value=commands_response) as mock_request:
            result = await control_plane_client.poll_commands("test-server")
            
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_report_command_result(self, control_plane_client) -> None:
        """Test reporting command execution result."""
        command_result = CommandResult(
            command_id="cmd-001",
            success=True,
            result={"output": "success"}
        )
        
        expected_response = {"status": "success"}
        
        with patch.object(control_plane_client, "_make_request", return_value=expected_response) as mock_request:
            result = await control_plane_client.report_command_result("test-server", command_result)
            
            assert result == expected_response
            mock_request.assert_called_once_with(
                method="POST",
                endpoint="/api/v1/servers/test-server/command-results",
                data=command_result.model_dump(),
                correlation_id=None
            )

    @pytest.mark.asyncio
    async def test_fetch_jwt_public_keys_cache_miss(self, control_plane_client) -> None:
        """Test fetching JWT public keys when cache is empty."""
        keys_response = {"keys": [{"kid": "key1", "key": "public_key_data"}]}
        
        with patch.object(control_plane_client, "_make_request", return_value=keys_response) as mock_request:
            result = await control_plane_client.fetch_jwt_public_keys()
            
            assert result == keys_response
            assert control_plane_client._jwt_keys_cache == keys_response
            assert control_plane_client._jwt_keys_cached_at is not None
            
            mock_request.assert_called_once_with(
                method="GET",
                endpoint="/api/v1/auth/public-keys",
                correlation_id=None
            )

    @pytest.mark.asyncio
    async def test_fetch_jwt_public_keys_cache_hit(self, control_plane_client) -> None:
        """Test fetching JWT public keys when cache is valid."""
        cached_keys = {"keys": [{"kid": "cached_key", "key": "cached_data"}]}
        control_plane_client._jwt_keys_cache = cached_keys
        control_plane_client._jwt_keys_cached_at = datetime.utcnow()
        
        with patch.object(control_plane_client, "_make_request") as mock_request:
            result = await control_plane_client.fetch_jwt_public_keys()
            
            assert result == cached_keys
            mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_check_success(self, control_plane_client, mock_config) -> None:
        """Test health check when ControlPlane is healthy."""
        health_response = {"status": "healthy"}
        
        with patch.object(control_plane_client, "_make_request", return_value=health_response) as mock_request:
            control_plane_client._client = AsyncMock()  # Simulate started client
            
            result = await control_plane_client.health_check()
            
            assert result["status"] == "healthy"
            assert result["response"] == health_response
            assert result["base_url"] == mock_config.control_plane_url
            
            mock_request.assert_called_once_with("GET", "/api/v1/health")

    @pytest.mark.asyncio
    async def test_health_check_client_not_started(self, control_plane_client, mock_config) -> None:
        """Test health check when client is not started."""
        result = await control_plane_client.health_check()
        
        assert result["status"] == "unhealthy"
        assert "Client not started" in result["error"]
        assert result["base_url"] == mock_config.control_plane_url

    @pytest.mark.asyncio
    async def test_health_check_request_failure(self, control_plane_client, mock_config) -> None:
        """Test health check when request fails."""
        control_plane_client._client = AsyncMock()  # Simulate started client
        
        with patch.object(control_plane_client, "_make_request", side_effect=Exception("Connection failed")) as mock_request:
            result = await control_plane_client.health_check()
            
            assert result["status"] == "unhealthy"
            assert "Connection failed" in result["error"]
            assert result["base_url"] == mock_config.control_plane_url
