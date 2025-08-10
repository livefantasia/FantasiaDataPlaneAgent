"""Integration tests for DataPlane Agent."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from models import SessionEventType, UsageRecord
from services import (
    ControlPlaneClient,
    RedisClient,
    RedisConsumerService,
)


class TestRedisConsumerIntegration:
    """Integration tests for Redis consumer service."""

    @pytest.fixture
    async def services(self, mock_config):
        """Create service instances for testing."""
        redis_client = RedisClient(mock_config)
        control_plane_client = ControlPlaneClient(mock_config)
        consumer_service = RedisConsumerService(
            mock_config, redis_client, control_plane_client
        )
        
        # Mock the underlying clients
        redis_client.connect = AsyncMock()
        redis_client.disconnect = AsyncMock()
        redis_client.reliable_pop_message = AsyncMock(return_value=None)
        redis_client.acknowledge_message = AsyncMock()
        redis_client.move_to_dead_letter_queue = AsyncMock()
        
        control_plane_client.start = AsyncMock()
        control_plane_client.stop = AsyncMock()
        control_plane_client.submit_usage_records = AsyncMock(
            return_value={"status": "success"}
        )
        control_plane_client.notify_session_start = AsyncMock(
            return_value={"status": "success"}
        )
        control_plane_client.notify_session_complete = AsyncMock(
            return_value={"status": "success"}
        )
        control_plane_client.request_quota_refresh = AsyncMock(
            return_value={"status": "success"}
        )
        
        return redis_client, control_plane_client, consumer_service

    @pytest.mark.asyncio
    async def test_usage_record_processing_flow(self, services, mock_config):
        """Test end-to-end usage record processing."""
        redis_client, control_plane_client, consumer_service = services
        
        # Create test usage record
        usage_record_data = {
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "product_code": "SPEECH_TO_TEXT_STANDARD",
            "connection_duration_seconds": 120.5,
            "data_bytes_processed": 1024000,
            "audio_duration_seconds": 110.0,
            "request_timestamp": "2024-01-15T10:00:00Z",
            "response_timestamp": "2024-01-15T10:02:00Z",
        }
        
        message_id = "test-msg-001"
        serialized_data = json.dumps(usage_record_data)
        
        # Mock Redis pop to return our test message once, then None
        call_count = 0
        async def mock_pop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (message_id, usage_record_data)
            return None
        
        redis_client.reliable_pop_message.side_effect = mock_pop
        
        # Start consumer
        await consumer_service.start()
        
        # Let it process one message
        await asyncio.sleep(0.1)
        
        # Stop consumer
        await consumer_service.stop()
        
        # Verify message was processed
        control_plane_client.submit_usage_records.assert_called_once()
        call_args = control_plane_client.submit_usage_records.call_args[0]
        enriched_records = call_args[0]
        
        assert len(enriched_records) == 1
        enriched_record = enriched_records[0]
        assert enriched_record.api_session_id == "test-session-001"
        assert enriched_record.server_instance_id == mock_config.server_id
        assert enriched_record.api_server_region == mock_config.server_region
        assert enriched_record.agent_version == mock_config.app_version
        
        # Verify message was acknowledged
        redis_client.acknowledge_message.assert_called_once_with(
            f"{mock_config.usage_records_queue}:processing",
            serialized_data
        )

    @pytest.mark.asyncio
    async def test_session_lifecycle_processing_flow(self, services, mock_config):
        """Test end-to-end session lifecycle event processing."""
        redis_client, control_plane_client, consumer_service = services
        
        # Create test session start event
        session_event_data = {
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "event_type": "start",
            "timestamp": "2024-01-15T10:00:00Z",
            "metadata": {"test": "data"},
        }
        
        message_id = "test-msg-002"
        
        # Mock Redis pop for session lifecycle queue
        call_count = 0
        async def mock_pop(source_queue, *args, **kwargs):
            nonlocal call_count
            if source_queue == mock_config.session_lifecycle_queue:
                call_count += 1
                if call_count == 1:
                    return (message_id, session_event_data)
            return None
        
        redis_client.reliable_pop_message.side_effect = mock_pop
        
        # Start consumer
        await consumer_service.start()
        
        # Let it process one message
        await asyncio.sleep(0.1)
        
        # Stop consumer
        await consumer_service.stop()
        
        # Verify session start was notified
        control_plane_client.notify_session_start.assert_called_once()
        call_args = control_plane_client.notify_session_start.call_args[0]
        session_event = call_args[0]
        
        assert session_event.api_session_id == "test-session-001"
        assert session_event.event_type == SessionEventType.START

    @pytest.mark.asyncio
    async def test_quota_refresh_processing_flow(self, services, mock_config):
        """Test end-to-end quota refresh processing."""
        redis_client, control_plane_client, consumer_service = services
        
        # Create test quota refresh request
        quota_request_data = {
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "current_usage": 50.0,
            "requested_quota": 100.0,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        
        message_id = "test-msg-003"
        
        # Mock Redis pop for quota refresh queue
        call_count = 0
        async def mock_pop(source_queue, *args, **kwargs):
            nonlocal call_count
            if source_queue == mock_config.quota_refresh_queue:
                call_count += 1
                if call_count == 1:
                    return (message_id, quota_request_data)
            return None
        
        redis_client.reliable_pop_message.side_effect = mock_pop
        
        # Start consumer
        await consumer_service.start()
        
        # Let it process one message
        await asyncio.sleep(0.1)
        
        # Stop consumer
        await consumer_service.stop()
        
        # Verify quota refresh was requested
        control_plane_client.request_quota_refresh.assert_called_once()
        call_args = control_plane_client.request_quota_refresh.call_args[0]
        quota_request = call_args[0]
        
        assert quota_request.api_session_id == "test-session-001"
        assert quota_request.requested_quota == 100.0

    @pytest.mark.asyncio
    async def test_message_processing_failure_handling(self, services, mock_config):
        """Test handling of message processing failures."""
        redis_client, control_plane_client, consumer_service = services
        
        # Create invalid usage record (missing required fields)
        invalid_usage_record = {
            "api_session_id": "test-session-001",
            # Missing required fields to trigger validation error
        }
        
        message_id = "test-msg-004"
        serialized_data = json.dumps(invalid_usage_record)
        
        # Mock Redis pop to return invalid message
        call_count = 0
        async def mock_pop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (message_id, invalid_usage_record)
            return None
        
        redis_client.reliable_pop_message.side_effect = mock_pop
        
        # Start consumer
        await consumer_service.start()
        
        # Let it process the invalid message
        await asyncio.sleep(0.1)
        
        # Stop consumer
        await consumer_service.stop()
        
        # Verify message was moved to dead letter queue
        redis_client.move_to_dead_letter_queue.assert_called_once_with(
            f"{mock_config.usage_records_queue}:processing",
            serialized_data,
            error_info=redis_client.move_to_dead_letter_queue.call_args[1]["error_info"]
        )
        
        # Verify ControlPlane was not called for invalid message
        control_plane_client.submit_usage_records.assert_not_called()

    @pytest.mark.asyncio
    async def test_control_plane_failure_handling(self, services, mock_config):
        """Test handling of ControlPlane communication failures."""
        redis_client, control_plane_client, consumer_service = services
        
        # Create valid usage record
        usage_record_data = {
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "product_code": "SPEECH_TO_TEXT_STANDARD",
            "connection_duration_seconds": 120.5,
            "data_bytes_processed": 1024000,
            "audio_duration_seconds": 110.0,
            "request_timestamp": "2024-01-15T10:00:00Z",
            "response_timestamp": "2024-01-15T10:02:00Z",
        }
        
        message_id = "test-msg-005"
        serialized_data = json.dumps(usage_record_data)
        
        # Mock ControlPlane to fail
        control_plane_client.submit_usage_records.side_effect = Exception(
            "ControlPlane communication failed"
        )
        
        # Mock Redis pop to return test message
        call_count = 0
        async def mock_pop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (message_id, usage_record_data)
            return None
        
        redis_client.reliable_pop_message.side_effect = mock_pop
        
        # Start consumer
        await consumer_service.start()
        
        # Let it process the message
        await asyncio.sleep(0.1)
        
        # Stop consumer
        await consumer_service.stop()
        
        # Verify message was moved to dead letter queue due to ControlPlane failure
        redis_client.move_to_dead_letter_queue.assert_called_once_with(
            f"{mock_config.usage_records_queue}:processing",
            serialized_data,
            error_info="ControlPlane communication failed"
        )

    @pytest.mark.asyncio
    async def test_consumer_stats(self, services):
        """Test consumer statistics reporting."""
        redis_client, control_plane_client, consumer_service = services
        
        # Mock queue lengths
        queue_lengths = {
            "queue:usage_records": 5,
            "queue:session_lifecycle": 2,
            "queue:quota_refresh": 1,
            "queue:dead_letter": 0,
        }
        redis_client.get_all_queue_lengths.return_value = queue_lengths
        
        # Start consumer
        await consumer_service.start()
        
        # Get stats
        stats = await consumer_service.get_consumer_stats()
        
        assert stats["running"] is True
        assert stats["active_tasks"] >= 0
        assert stats["total_tasks"] == 3  # Three consumer tasks
        assert stats["queue_lengths"] == queue_lengths
        
        # Stop consumer
        await consumer_service.stop()
        
        # Get stats after stopping
        stats = await consumer_service.get_consumer_stats()
        assert stats["running"] is False
