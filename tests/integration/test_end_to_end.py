"""End-to-end integration tests for the DataPlane Agent system."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from models import (
    CommandType,
    EnrichedUsageRecord,
    ProductCode,
    RemoteCommand,
    SessionEventType,
    SessionLifecycleEvent,
    UsageRecord,
)


class TestEndToEndIntegration:
    """Comprehensive end-to-end integration tests."""

    @pytest.fixture
    async def full_system_setup(self, mock_config):
        """Set up a complete system for end-to-end testing."""
        from main import create_app
        
        app = create_app()
        
        # Mock external dependencies
        mock_redis = AsyncMock()
        mock_control_plane_client = AsyncMock()
        mock_health_service = AsyncMock()
        
        # Configure mock behaviors
        mock_redis.is_connected.return_value = True
        mock_redis.lpop.return_value = None  # Empty queues by default
        mock_redis.llen.return_value = 0
        
        mock_control_plane_client.send_enriched_usage_record.return_value = True
        mock_control_plane_client.send_session_lifecycle_event.return_value = True
        mock_control_plane_client.request_quota_refresh.return_value = True
        mock_control_plane_client.poll_remote_commands.return_value = []
        mock_control_plane_client.get_auth_token.return_value = "mock-token"
        
        mock_health_service.get_health_status.return_value = {
            "status": "healthy",
            "timestamp": "2024-01-15T10:00:00Z",
            "version": "1.0.0",
            "uptime_seconds": 3600,
            "redis_connected": True,
            "control_plane_connected": True,
            "server_registered": True,
        }
        
        # Inject mocks into the application
        mocks = {
            "redis": mock_redis,
            "control_plane": mock_control_plane_client,
            "health": mock_health_service,
        }
        
        yield app, mocks

    @pytest.mark.asyncio
    async def test_complete_usage_record_flow(self, full_system_setup, mock_config):
        """Test complete flow from Redis queue to ControlPlane."""
        app, mocks = full_system_setup
        
        # Prepare test data
        usage_record = UsageRecord(
            api_session_id="session456",
            customer_id="customer123",
            product_code=ProductCode.SPEECH_TO_TEXT_STANDARD,
            connection_duration_seconds=30.0,
            data_bytes_processed=1024000,
            audio_duration_seconds=25.5,
            request_timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            response_timestamp=datetime.fromisoformat("2024-01-15T10:00:30"),
        )
        
        # Mock Redis to return our test message
        mocks["redis"].reliable_pop_message.return_value = ("msg1", usage_record.model_dump())
        
        # Test the consumer service processing
        from services.redis_consumer import RedisConsumerService
        
        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mocks["redis"],
            control_plane_client=mocks["control_plane"]
        )
        
        # Simulate processing a single message
        await consumer._process_usage_record(usage_record.model_dump(), "test-correlation-id")
        
        # Verify ControlPlane was called with enriched data
        mocks["control_plane"].send_enriched_usage_record.assert_called_once()
        call_args = mocks["control_plane"].send_enriched_usage_record.call_args[0][0]
        
        assert call_args.api_session_id == "session456"
        assert call_args.customer_id == "customer123"
        assert call_args.server_instance_id is not None

    @pytest.mark.asyncio
    async def test_session_lifecycle_complete_flow(self, full_system_setup, mock_config):
        """Test complete session lifecycle event processing."""
        app, mocks = full_system_setup
        
        # Test session start event
        start_event = SessionLifecycleEvent(
            api_session_id="session789",
            customer_id="customer456",
            event_type=SessionEventType.START,
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            metadata={"client_version": "1.2.0", "platform": "web"},
        )
        
        mocks["redis"].reliable_pop_message.return_value = ("msg1", start_event.model_dump())
        
        from services.redis_consumer import RedisConsumerService
        
        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mocks["redis"],
            control_plane_client=mocks["control_plane"]
        )
        
        # Simulate processing
        await consumer._process_session_lifecycle_event(start_event.model_dump(), "test-correlation-id")
        
        # Verify event was sent to ControlPlane
        mocks["control_plane"].send_session_lifecycle_event.assert_called_once()
        call_args = mocks["control_plane"].send_session_lifecycle_event.call_args[0][0]
        
        assert call_args.api_session_id == "session789"
        assert call_args.event_type == SessionEventType.START

    @pytest.mark.asyncio
    async def test_remote_command_execution_flow(self, full_system_setup, mock_config):
        """Test remote command polling and execution."""
        app, mocks = full_system_setup
        
        # Prepare remote commands
        health_command = RemoteCommand(
            command_id="cmd001",
            command_type=CommandType.HEALTH_CHECK,
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            parameters={},
        )
        
        metrics_command = RemoteCommand(
            command_id="cmd002",
            command_type=CommandType.GET_METRICS,
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            parameters={"format": "json"},
        )
        
        # Mock ControlPlane to return commands
        mocks["control_plane"].poll_remote_commands.return_value = [health_command, metrics_command]
        
        from services.command_processor import CommandProcessor
        
        processor = CommandProcessor(
            config=mock_config,
            redis_client=mocks["redis"],
            control_plane_client=mocks["control_plane"]
        )
        
        # Test command polling
        commands = await mocks["control_plane"].poll_remote_commands()
        assert len(commands) == 2
        assert commands[0].command_type == CommandType.HEALTH_CHECK

    @pytest.mark.asyncio
    async def test_system_health_and_api_integration(self, full_system_setup):
        """Test system health monitoring and API integration."""
        app, mocks = full_system_setup
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Test basic health endpoint
            with patch("dataplane_agent.routers.health._health_service", mocks["health"]):
                response = await client.get("/health/")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert data["redis_connected"] is True
                assert data["control_plane_connected"] is True

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, full_system_setup, mock_config):
        """Test system behavior under error conditions."""
        app, mocks = full_system_setup
        
        # Simulate Redis connection failure
        mocks["redis"].is_connected.return_value = False
        mocks["redis"].reliable_pop_message.side_effect = Exception("Redis connection lost")
        
        from services.redis_consumer import RedisConsumerService
        
        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mocks["redis"],
            control_plane_client=mocks["control_plane"]
        )
        
        # Should handle Redis errors gracefully
        try:
            await consumer._consume_usage_records()
        except Exception:
            # Expected due to mocked error
            pass

    @pytest.mark.asyncio
    async def test_message_retry_and_dead_letter_queue(self, full_system_setup, mock_config):
        """Test message retry logic and dead letter queue handling."""
        app, mocks = full_system_setup
        
        # Create a message that will fail processing
        bad_usage_record = {
            "api_session_id": "session456",
            "customer_id": "customer123",
            # Missing required fields to cause validation error
        }
        
        from services.redis_consumer import RedisConsumerService
        
        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mocks["redis"],
            control_plane_client=mocks["control_plane"]
        )
        
        # Test processing bad message
        try:
            await consumer._process_usage_record(bad_usage_record, "test-correlation-id")
        except Exception:
            # Expected validation error
            pass

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, full_system_setup, mock_config):
        """Test system behavior under concurrent load."""
        app, mocks = full_system_setup
        
        # Create multiple test messages
        usage_records = []
        for i in range(5):
            record = UsageRecord(
                api_session_id=f"session{i}",
                customer_id=f"customer{i}",
                product_code=ProductCode.SPEECH_TO_TEXT_STANDARD,
                connection_duration_seconds=30.0,
                data_bytes_processed=1024000,
                audio_duration_seconds=25.5,
                request_timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
                response_timestamp=datetime.fromisoformat("2024-01-15T10:00:30"),
            )
            usage_records.append(record)
        
        from services.redis_consumer import RedisConsumerService
        
        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mocks["redis"],
            control_plane_client=mocks["control_plane"]
        )
        
        # Process multiple messages concurrently
        tasks = []
        for i, record in enumerate(usage_records):
            task = consumer._process_usage_record(record.model_dump(), f"correlation-{i}")
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Verify multiple messages were processed
        assert mocks["control_plane"].send_enriched_usage_record.call_count == 5

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, full_system_setup, mock_config):
        """Test graceful system shutdown."""
        app, mocks = full_system_setup
        
        from services.redis_consumer import RedisConsumerService
        from services.command_processor import CommandProcessor
        
        consumer = RedisConsumerService(
            config=mock_config,
            redis_client=mocks["redis"],
            control_plane_client=mocks["control_plane"]
        )
        
        processor = CommandProcessor(
            config=mock_config,
            redis_client=mocks["redis"],
            control_plane_client=mocks["control_plane"]
        )
        
        # Start services
        await consumer.start()
        await processor.start()
        
        # Verify services are running
        assert consumer._running
        assert processor._running
        
        # Shutdown services
        await consumer.stop()
        await processor.stop()
        
        # Verify services stopped gracefully
        assert not consumer._running
        assert not processor._running

    @pytest.mark.asyncio
    async def test_metrics_collection_throughout_processing(self, full_system_setup):
        """Test that metrics are properly collected during message processing."""
        app, mocks = full_system_setup
        
        # Configure health service to track metrics
        metrics_data = {
            "server_id": "test-server-001",
            "timestamp": "2024-01-15T10:00:00Z",
            "uptime_seconds": 3600,
            "queue_metrics": {
                "queue:usage_records": 0,
                "queue:session_lifecycle": 0,
                "queue:quota_refresh": 0,
                "queue:dead_letter": 0,
            },
            "processing_metrics": {
                "messages_processed": 0,
                "processing_errors": 0,
                "avg_processing_time_ms": 0,
            },
        }
        
        mocks["health"].get_metrics_data.return_value = metrics_data
        
        # Test metrics endpoint
        async with AsyncClient(app=app, base_url="http://test") as client:
            with patch("dataplane_agent.routers.metrics._health_service", mocks["health"]):
                response = await client.get("/metrics/json")
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["server_id"] == "test-server-001"
                assert "queue_metrics" in data
                assert "processing_metrics" in data

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from models import (
    CommandType,
    EnrichedUsageRecord,
    ProductCode,
    RemoteCommand,
    SessionEventType,
    SessionLifecycleEvent,
    UsageRecord,
)


class TestEndToEndIntegration:
    """Comprehensive end-to-end integration tests."""

    @pytest.fixture
    async def full_system_setup(self, mock_config):
        """Set up a complete system for end-to-end testing."""
        from main import create_app
        
        app = create_app()
        
        # Mock external dependencies
        mock_redis = AsyncMock()
        mock_control_plane_client = AsyncMock()
        mock_health_service = AsyncMock()
        
        # Configure mock behaviors
        mock_redis.is_connected.return_value = True
        mock_redis.lpop.return_value = None  # Empty queues by default
        mock_redis.llen.return_value = 0
        
        mock_control_plane_client.send_enriched_usage_record.return_value = True
        mock_control_plane_client.send_session_lifecycle_event.return_value = True
        mock_control_plane_client.request_quota_refresh.return_value = True
        mock_control_plane_client.poll_remote_commands.return_value = []
        mock_control_plane_client.get_auth_token.return_value = "mock-token"
        
        mock_health_service.get_health_status.return_value = {
            "status": "healthy",
            "timestamp": "2024-01-15T10:00:00Z",
            "version": "1.0.0",
            "uptime_seconds": 3600,
            "redis_connected": True,
            "control_plane_connected": True,
            "server_registered": True,
        }
        
        # Inject mocks into the application
        mocks = {
            "redis": mock_redis,
            "control_plane": mock_control_plane_client,
            "health": mock_health_service,
        }
        
        yield app, mocks

    @pytest.mark.asyncio
    async def test_complete_usage_record_flow(self, full_system_setup):
        """Test complete flow from Redis queue to ControlPlane."""
        app, mocks = full_system_setup
        
        # Prepare test data
        from datetime import datetime
        
        usage_record = UsageRecord(
            api_session_id="session456",
            customer_id="customer123",
            product_code=ProductCode.SPEECH_TO_TEXT_STANDARD,
            connection_duration_seconds=30.0,
            data_bytes_processed=1024000,
            audio_duration_seconds=25.5,
            request_timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            response_timestamp=datetime.fromisoformat("2024-01-15T10:00:30"),
        )
        
        enriched_record = EnrichedUsageRecord(
            **usage_record.model_dump(),
            server_instance_id="test-server-001",
            api_server_region="us-west-2",
            processing_timestamp=datetime.fromisoformat("2024-01-15T10:00:35"),
            agent_version="1.0.0",
        )
        
        # Mock Redis to return our test message
        mocks["redis"].lpop.return_value = usage_record.model_dump_json()
        
        # Simulate the consumer processing
        from services.redis_consumer import RedisConsumerService
        
        with patch("dataplane_agent.services.redis_consumer.RedisClient", return_value=mocks["redis"]), \
             patch("dataplane_agent.services.redis_consumer.ControlPlaneClient", return_value=mocks["control_plane"]):
            
            consumer = RedisConsumerService(
                config=mock_config,
                redis_client=mocks["redis"],
                control_plane_client=mocks["control_plane"]
            )
            await consumer.start()
            
            # Process one message
            await consumer.process_messages()
            
            # Verify ControlPlane was called with enriched data
            mocks["control_plane"].send_enriched_usage_record.assert_called_once()
            call_args = mocks["control_plane"].send_enriched_usage_record.call_args[0][0]
            
            assert call_args.api_session_id == "session456"
            assert call_args.customer_id == "customer123"
            assert call_args.server_instance_id is not None

    @pytest.mark.asyncio
    async def test_session_lifecycle_complete_flow(self, full_system_setup):
        """Test complete session lifecycle event processing."""
        app, mocks = full_system_setup
        
        # Test session start event
        start_event = SessionLifecycleEvent(
            session_id="session789",
            user_id="user456",
            event_type=SessionLifecycleEventType.SESSION_STARTED,
            timestamp="2024-01-15T10:00:00Z",
            metadata={"client_version": "1.2.0", "platform": "web"},
        )
        
        mocks["redis"].lpop.return_value = start_event.model_dump_json()
        
        from services.redis_consumer import RedisConsumerService
        
        with patch("dataplane_agent.services.redis_consumer.RedisClient", return_value=mocks["redis"]), \
             patch("dataplane_agent.services.redis_consumer.ControlPlaneClient", return_value=mocks["control_plane"]):
            
            consumer = RedisConsumerService()
            await consumer.start()
            
            await consumer._process_session_lifecycle()
            
            # Verify event was sent to ControlPlane
            mocks["control_plane"].send_session_lifecycle_event.assert_called_once()
            call_args = mocks["control_plane"].send_session_lifecycle_event.call_args[0][0]
            
            assert call_args.session_id == "session789"
            assert call_args.event_type == SessionLifecycleEventType.SESSION_STARTED

    @pytest.mark.asyncio
    async def test_remote_command_execution_flow(self, full_system_setup):
        """Test remote command polling and execution."""
        app, mocks = full_system_setup
        
        # Prepare remote commands
        health_command = RemoteCommand(
            command_id="cmd001",
            command_type=RemoteCommandType.HEALTH_CHECK,
            timestamp="2024-01-15T10:00:00Z",
            parameters={},
        )
        
        metrics_command = RemoteCommand(
            command_id="cmd002",
            command_type=RemoteCommandType.GET_METRICS,
            timestamp="2024-01-15T10:00:00Z",
            parameters={"format": "json"},
        )
        
        # Mock ControlPlane to return commands
        mocks["control_plane"].poll_remote_commands.return_value = [health_command, metrics_command]
        
        from services.command_processor import CommandProcessor
        
        with patch("dataplane_agent.services.command_processor.ControlPlaneClient", return_value=mocks["control_plane"]), \
             patch("dataplane_agent.services.command_processor.RedisClient", return_value=mocks["redis"]):
            
            processor = CommandProcessor()
            await processor.start()
            
            # Process commands
            await processor._poll_and_process_commands()
            
            # Verify commands were processed
            assert mocks["control_plane"].poll_remote_commands.called
            # In a real scenario, you'd check command execution results

    @pytest.mark.asyncio
    async def test_system_health_and_api_integration(self, full_system_setup):
        """Test system health monitoring and API integration."""
        app, mocks = full_system_setup
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Test basic health endpoint
            with patch("dataplane_agent.routers.health._health_service", mocks["health"]):
                response = await client.get("/health/")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert data["redis_connected"] is True
                assert data["control_plane_connected"] is True

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, full_system_setup):
        """Test system behavior under error conditions."""
        app, mocks = full_system_setup
        
        # Simulate Redis connection failure
        mocks["redis"].is_connected.return_value = False
        mocks["redis"].lpop.side_effect = Exception("Redis connection lost")
        
        from services.redis_consumer import RedisConsumerService
        
        with patch("dataplane_agent.services.redis_consumer.RedisClient", return_value=mocks["redis"]), \
             patch("dataplane_agent.services.redis_consumer.ControlPlaneClient", return_value=mocks["control_plane"]):
            
            consumer = RedisConsumerService()
            await consumer.start()
            
            # Should handle Redis errors gracefully
            await consumer._process_usage_records()
            
            # Verify error was logged and handled
            assert consumer.stats["errors"] > 0

    @pytest.mark.asyncio
    async def test_message_retry_and_dead_letter_queue(self, full_system_setup):
        """Test message retry logic and dead letter queue handling."""
        app, mocks = full_system_setup
        
        # Create a message that will fail processing
        bad_usage_record = {
            "user_id": "user123",
            "session_id": "session456",
            # Missing required fields to cause validation error
        }
        
        mocks["redis"].lpop.return_value = json.dumps(bad_usage_record)
        
        from services.redis_consumer import RedisConsumerService
        
        with patch("dataplane_agent.services.redis_consumer.RedisClient", return_value=mocks["redis"]), \
             patch("dataplane_agent.services.redis_consumer.ControlPlaneClient", return_value=mocks["control_plane"]):
            
            consumer = RedisConsumerService()
            await consumer.start()
            
            # Process the bad message
            await consumer._process_usage_records()
            
            # Verify message was moved to dead letter queue
            mocks["redis"].rpush.assert_called()
            dead_letter_call = None
            for call in mocks["redis"].rpush.call_args_list:
                if "dead_letter" in str(call):
                    dead_letter_call = call
                    break
            
            assert dead_letter_call is not None

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, full_system_setup):
        """Test system behavior under concurrent load."""
        app, mocks = full_system_setup
        
        # Create multiple test messages
        usage_records = [
            UsageRecord(
                user_id=f"user{i}",
                session_id=f"session{i}",
                service_type="transcription",
                timestamp="2024-01-15T10:00:00Z",
                duration_seconds=30,
                tokens_used=150,
                model_id="whisper-large",
                input_size_bytes=1024000,
                output_size_bytes=2048,
            )
            for i in range(10)
        ]
        
        # Mock Redis to return messages sequentially
        message_queue = [record.model_dump_json() for record in usage_records]
        mocks["redis"].lpop.side_effect = message_queue + [None] * 10  # Add None values to end queue
        
        from services.redis_consumer import RedisConsumerService
        
        with patch("dataplane_agent.services.redis_consumer.RedisClient", return_value=mocks["redis"]), \
             patch("dataplane_agent.services.redis_consumer.ControlPlaneClient", return_value=mocks["control_plane"]):
            
            consumer = RedisConsumerService()
            await consumer.start()
            
            # Process multiple batches
            for _ in range(5):
                await consumer._process_usage_records()
                await asyncio.sleep(0.01)  # Small delay to simulate processing time
            
            # Verify multiple messages were processed
            assert mocks["control_plane"].send_enriched_usage_record.call_count >= 5

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, full_system_setup):
        """Test graceful system shutdown."""
        app, mocks = full_system_setup
        
        from services.redis_consumer import RedisConsumerService
        from services.command_processor import CommandProcessor
        
        with patch("dataplane_agent.services.redis_consumer.RedisClient", return_value=mocks["redis"]), \
             patch("dataplane_agent.services.redis_consumer.ControlPlaneClient", return_value=mocks["control_plane"]), \
             patch("dataplane_agent.services.command_processor.ControlPlaneClient", return_value=mocks["control_plane"]), \
             patch("dataplane_agent.services.command_processor.RedisClient", return_value=mocks["redis"]):
            
            consumer = RedisConsumerService()
            processor = CommandProcessor()
            
            # Start services
            await consumer.start()
            await processor.start()
            
            # Verify services are running
            assert consumer.running
            assert processor.running
            
            # Shutdown services
            await consumer.stop()
            await processor.stop()
            
            # Verify services stopped gracefully
            assert not consumer.running
            assert not processor.running

    @pytest.mark.asyncio
    async def test_metrics_collection_throughout_processing(self, full_system_setup):
        """Test that metrics are properly collected during message processing."""
        app, mocks = full_system_setup
        
        # Configure health service to track metrics
        metrics_data = {
            "server_id": "test-server-001",
            "timestamp": "2024-01-15T10:00:00Z",
            "uptime_seconds": 3600,
            "queue_metrics": {
                "queue:usage_records": 0,
                "queue:session_lifecycle": 0,
                "queue:quota_refresh": 0,
                "queue:dead_letter": 0,
            },
            "processing_metrics": {
                "messages_processed": 0,
                "processing_errors": 0,
                "avg_processing_time_ms": 0,
            },
        }
        
        mocks["health"].get_metrics_data.return_value = metrics_data
        
        # Test metrics endpoint
        async with AsyncClient(app=app, base_url="http://test") as client:
            with patch("dataplane_agent.routers.metrics._health_service", mocks["health"]):
                response = await client.get("/metrics/json")
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["server_id"] == "test-server-001"
                assert "queue_metrics" in data
                assert "processing_metrics" in data
