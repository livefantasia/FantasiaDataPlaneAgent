"""Unit tests for DataPlane Agent models."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from models import (
    CommandType,
    EnrichedUsageRecord,
    ProductCode,
    QuotaRefreshRequest,
    RemoteCommand,
    SessionEventType,
    SessionLifecycleEvent,
    UsageRecord,
)


class TestUsageRecord:
    """Test cases for UsageRecord model."""

    def test_valid_usage_record(self) -> None:
        """Test creating a valid usage record."""
        data = {
            "transaction_id": "test-transaction-001",
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "connection_duration_seconds": 120.5,
            "data_bytes_processed": 1024000,
            "audio_duration_seconds": 110.0,
            "request_timestamp": "2024-01-15T10:00:00Z",
            "response_timestamp": "2024-01-15T10:02:00Z",
        }
        
        record = UsageRecord(**data)
        
        assert record.api_session_id == "test-session-001"
        assert record.customer_id == "test-customer-001"
        assert record.product_code == ProductCode.SPEECH_TO_TEXT_STANDARD
        assert record.connection_duration_seconds == 120.5
        assert record.data_bytes_processed == 1024000
        assert record.audio_duration_seconds == 110.0

    def test_negative_duration_validation(self) -> None:
        """Test validation fails for negative durations."""
        data = {
            "transaction_id": "test-transaction-002",
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "connection_duration_seconds": -10.0,
            "data_bytes_processed": 1024000,
            "audio_duration_seconds": 110.0,
            "request_timestamp": "2024-01-15T10:00:00Z",
            "response_timestamp": "2024-01-15T10:02:00Z",
        }
        
        with pytest.raises(ValidationError):
            UsageRecord(**data)

    def test_negative_bytes_validation(self) -> None:
        """Test validation fails for negative bytes."""
        data = {
            "transaction_id": "test-transaction-003",
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "connection_duration_seconds": 120.5,
            "data_bytes_processed": -1000,
            "audio_duration_seconds": 110.0,
            "request_timestamp": "2024-01-15T10:00:00Z",
            "response_timestamp": "2024-01-15T10:02:00Z",
        }
        
        with pytest.raises(ValidationError):
            UsageRecord(**data)

    def test_response_before_request_validation(self) -> None:
        """Test validation fails when response timestamp is before request."""
        data = {
            "transaction_id": "test-transaction-004",
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "connection_duration_seconds": 120.5,
            "data_bytes_processed": 1024000,
            "audio_duration_seconds": 110.0,
            "request_timestamp": "2024-01-15T10:02:00Z",
            "response_timestamp": "2024-01-15T10:00:00Z",
        }
        
        with pytest.raises(ValidationError):
            UsageRecord(**data)


class TestEnrichedUsageRecord:
    """Test cases for EnrichedUsageRecord model."""

    def test_enriched_usage_record(self) -> None:
        """Test creating an enriched usage record."""
        data = {
            "transaction_id": "test-transaction-005",
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "connection_duration_seconds": 120.5,
            "data_bytes_processed": 1024000,
            "audio_duration_seconds": 110.0,
            "request_timestamp": "2024-01-15T10:00:00Z",
            "response_timestamp": "2024-01-15T10:02:00Z",
            "server_instance_id": "server-001",
            "api_server_region": "us-east-1",
            "agent_version": "1.0.0",
        }
        
        record = EnrichedUsageRecord(**data)
        
        assert record.server_instance_id == "server-001"
        assert record.api_server_region == "us-east-1"
        assert record.agent_version == "1.0.0"
        assert record.processing_timestamp is not None


class TestSessionLifecycleEvent:
    """Test cases for SessionLifecycleEvent model."""

    def test_session_start_event(self) -> None:
        """Test creating a session start event."""
        data = {
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "event_type": "start",
        }
        
        event = SessionLifecycleEvent(**data)
        
        assert event.api_session_id == "test-session-001"
        assert event.customer_id == "test-customer-001"
        assert event.event_type == SessionEventType.START
        assert event.timestamp is not None

    def test_session_complete_event(self) -> None:
        """Test creating a session complete event."""
        data = {
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "event_type": "complete",
            "metadata": {"final_usage": 100.0},
        }
        
        event = SessionLifecycleEvent(**data)
        
        assert event.event_type == SessionEventType.COMPLETE
        assert event.metadata == {"final_usage": 100.0}

    def test_invalid_event_type(self) -> None:
        """Test validation fails for invalid event type."""
        data = {
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "event_type": "invalid",
        }
        
        with pytest.raises(ValidationError):
            SessionLifecycleEvent(**data)


class TestQuotaRefreshRequest:
    """Test cases for QuotaRefreshRequest model."""

    def test_valid_quota_request(self) -> None:
        """Test creating a valid quota refresh request."""
        data = {
            "transaction_id": "test-transaction-001",
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "current_usage": 50.0,
            "requested_quota": 100.0,
        }
        
        request = QuotaRefreshRequest(**data)
        
        assert request.api_session_id == "test-session-001"
        assert request.customer_id == "test-customer-001"
        assert request.current_usage == 50.0
        assert request.requested_quota == 100.0
        assert request.timestamp is not None

    def test_negative_usage_validation(self) -> None:
        """Test validation fails for negative current usage."""
        data = {
            "transaction_id": "test-transaction-002",
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "current_usage": -10.0,
            "requested_quota": 100.0,
        }
        
        with pytest.raises(ValidationError):
            QuotaRefreshRequest(**data)

    def test_zero_quota_validation(self) -> None:
        """Test validation fails for zero requested quota."""
        data = {
            "transaction_id": "test-transaction-003",
            "api_session_id": "test-session-001",
            "customer_id": "test-customer-001",
            "current_usage": 50.0,
            "requested_quota": 0.0,
        }
        
        with pytest.raises(ValidationError):
            QuotaRefreshRequest(**data)


class TestRemoteCommand:
    """Test cases for RemoteCommand model."""

    def test_refresh_keys_command(self) -> None:
        """Test creating a refresh public keys command."""
        data = {
            "command_id": "cmd-001",
            "command_type": "refresh_public_keys",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        
        command = RemoteCommand(**data)
        
        assert command.command_id == "cmd-001"
        assert command.command_type == CommandType.REFRESH_PUBLIC_KEYS
        assert command.parameters is None

    def test_health_check_command(self) -> None:
        """Test creating a health check command."""
        data = {
            "command_id": "cmd-002",
            "command_type": "health_check",
            "timestamp": "2024-01-15T10:00:00Z",
            "parameters": {"include_details": True},
        }
        
        command = RemoteCommand(**data)
        
        assert command.command_type == CommandType.HEALTH_CHECK
        assert command.parameters == {"include_details": True}

    def test_get_metrics_command(self) -> None:
        """Test creating a get metrics command."""
        data = {
            "command_id": "cmd-003",
            "command_type": "get_metrics",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        
        command = RemoteCommand(**data)
        
        assert command.command_type == CommandType.GET_METRICS

    def test_invalid_command_type(self) -> None:
        """Test validation fails for invalid command type."""
        data = {
            "command_id": "cmd-001",
            "command_type": "invalid_command",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        
        with pytest.raises(ValidationError):
            RemoteCommand(**data)
