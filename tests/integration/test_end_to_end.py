"""End-to-end integration tests for the DataPlane Agent system."""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from models import (
    CommandType,
    RemoteCommand,
    SessionEventType,
    UsageRecord,
)
from services import (
    CommandProcessor,
    RedisConsumerService,
)


class TestEndToEndIntegration:
    """
    Comprehensive integration tests for service interactions.
    Note: These are integration tests, not true end-to-end tests,
    as they mock the external service boundaries (Redis/ControlPlane raw clients).
    """

    @pytest.mark.asyncio
    async def test_complete_usage_record_flow(
        self, mock_config: Any, mock_redis_client: Any, mock_control_plane_client: Any
    ) -> None:
        """Test complete flow from Redis queue to ControlPlane for usage records."""
        # Prepare test data
        usage_record_data = {
            "transaction_id": "txn-session456-001",
            "api_session_id": "session456",
            "customer_id": "customer123",
            "product_code": "speech_transcription",
            "connection_duration_seconds": 30.0,
            "data_bytes_processed": 1024000,
            "audio_duration_seconds": 25.5,
            "request_count": 1,
            "request_timestamp": "2024-01-15T10:00:00Z",
            "response_timestamp": "2024-01-15T10:00:30Z",
        }

        # Mock Redis to return our test message
        mock_redis_client.reliable_pop_message.return_value = (
            "msg1",
            usage_record_data,
        )

        # Initialize the consumer service with mocks
        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mock_redis_client,
            control_plane_client=mock_control_plane_client,
        )

        # Simulate processing a single message
        await consumer._process_usage_record(usage_record_data, "test-correlation-id")

        # Verify ControlPlane was called with enriched data
        mock_control_plane_client.submit_usage_records.assert_called_once()
        call_args = mock_control_plane_client.submit_usage_records.call_args[0]
        enriched_records = call_args[0]

        assert len(enriched_records) == 1
        enriched_record = enriched_records[0]
        assert enriched_record.api_session_id == "session456"
        assert enriched_record.customer_id == "customer123"
        assert enriched_record.server_instance_id == mock_config.server_id
        assert enriched_record.agent_version == mock_config.app_version

    @pytest.mark.asyncio
    async def test_session_lifecycle_complete_flow(
        self, mock_config: Any, mock_redis_client: Any, mock_control_plane_client: Any
    ) -> None:
        """Test complete session lifecycle event processing."""
        # Test session start event
        start_event_data = {
            "transaction_id": "test-transaction-001",
            "api_session_id": "session789",
            "customer_id": "customer456",
            "event_type": "start",
            "timestamp": "2024-01-15T10:00:00Z",
            "metadata": {"client_version": "1.2.0"},
        }

        mock_redis_client.reliable_pop_message.return_value = ("msg1", start_event_data)

        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mock_redis_client,
            control_plane_client=mock_control_plane_client,
        )

        # Simulate processing
        await consumer._process_session_lifecycle_event(
            start_event_data, "test-correlation-id"
        )

        # Verify event was sent to ControlPlane
        mock_control_plane_client.notify_session_start.assert_called_once()
        call_args = mock_control_plane_client.notify_session_start.call_args[0]
        session_event = call_args[0]

        assert session_event.api_session_id == "session789"
        assert session_event.event_type == SessionEventType.START

    @pytest.mark.asyncio
    async def test_remote_command_execution_flow(
        self, mock_config: Any, mock_redis_client: Any, mock_control_plane_client: Any
    ) -> None:
        """Test remote command polling and execution."""
        # Prepare remote command
        health_command = RemoteCommand(
            command_id="cmd001",
            command_type=CommandType.HEALTH_CHECK,
            timestamp=datetime.utcnow(),
            parameters={},
        )

        # Mock ControlPlane to return the command
        mock_control_plane_client.poll_commands.return_value = [health_command]
        # Mock Redis to show command has not been executed
        mock_redis_client.get_cache.return_value = None

        # Mock ThreadPoolExecutor for the processor
        from concurrent.futures import ThreadPoolExecutor
        mock_executor = AsyncMock(spec=ThreadPoolExecutor)
        
        processor = CommandProcessor(
            config=mock_config,
            redis_client=mock_redis_client,
            control_plane_client=mock_control_plane_client,
            executor=mock_executor,
        )

        # Since CommandProcessor is now synchronous, we'll test the sync methods directly
        # Mock the synchronous poll_commands_sync method
        mock_control_plane_client.poll_commands_sync.return_value = [health_command]
        
        # Mock Redis cache operations
        mock_redis_client.get_cache.return_value = None
        
        # Mock the report_command_result_sync method
        mock_control_plane_client.report_command_result_sync = AsyncMock()
        
        # Test the command processing directly
        processor._process_command_sync(health_command, "test-correlation-id")

        # Verify checks and actions
        mock_redis_client.get_cache.assert_called_once_with("executed_commands:cmd001")
        mock_redis_client.set_cache.assert_called_once()
        mock_control_plane_client.report_command_result_sync.assert_called_once()

        # Check that the result reported was successful
        result_call_args = mock_control_plane_client.report_command_result_sync.call_args[0]
        server_id = result_call_args[0]
        command_result = result_call_args[1]
        assert server_id == mock_config.server_id
        assert command_result.success is True
        assert command_result.command_id == "cmd001"
        assert "overall_status" in command_result.result

    @pytest.mark.asyncio
    async def test_graceful_shutdown(
        self, mock_config: Any, mock_redis_client: Any, mock_control_plane_client: Any
    ) -> None:
        """Test graceful system shutdown."""
        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mock_redis_client,
            control_plane_client=mock_control_plane_client,
        )

        # Mock ThreadPoolExecutor for the processor
        from concurrent.futures import ThreadPoolExecutor
        mock_executor = AsyncMock(spec=ThreadPoolExecutor)
        
        processor = CommandProcessor(
            config=mock_config,
            redis_client=mock_redis_client,
            control_plane_client=mock_control_plane_client,
            executor=mock_executor,
        )

        # Start services (consumer is async, processor is sync)
        await consumer.start()
        processor.start()  # This is synchronous now

        # Verify services are running and tasks are created
        assert consumer._running
        assert len(consumer._tasks) > 0

        # Stop services
        await consumer.stop()
        processor.stop()  # This is synchronous now

        # Verify consumer stopped gracefully
        assert not consumer._running
        # Ensure tasks were cancelled
        for task in consumer._tasks:
            assert task.cancelled()