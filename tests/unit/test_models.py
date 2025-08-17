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
        record = UsageRecord(
            transaction_id="test-transaction-001",
            api_session_id="test-session-001",
            customer_id="test-customer-001",
            connection_duration_seconds=120.5,
            data_bytes_processed=1024000,
            audio_duration_seconds=110.0,
            request_timestamp=datetime.fromisoformat("2024-01-15T10:00:00+00:00"),
            response_timestamp=datetime.fromisoformat("2024-01-15T10:02:00+00:00"),
        )
        
        assert record.api_session_id == "test-session-001"
        assert record.customer_id == "test-customer-001"
        assert record.product_code == ProductCode.SPEECH_TO_TEXT_STANDARD
        assert record.connection_duration_seconds == 120.5
        assert record.data_bytes_processed == 1024000
        assert record.audio_duration_seconds == 110.0

    def test_negative_duration_validation(self) -> None:
        """Test validation fails for negative durations."""
        with pytest.raises(ValidationError):
            UsageRecord(
                transaction_id="test-transaction-002",
                api_session_id="test-session-001",
                customer_id="test-customer-001",
                connection_duration_seconds=-10.0,
                data_bytes_processed=1024000,
                audio_duration_seconds=110.0,
                request_timestamp=datetime.fromisoformat("2024-01-15T10:00:00+00:00"),
                response_timestamp=datetime.fromisoformat("2024-01-15T10:02:00+00:00"),
            )

    def test_negative_bytes_validation(self) -> None:
        """Test validation fails for negative bytes."""
        with pytest.raises(ValidationError):
            UsageRecord(
                transaction_id="test-transaction-003",
                api_session_id="test-session-001",
                customer_id="test-customer-001",
                connection_duration_seconds=120.5,
                data_bytes_processed=-1000,
                audio_duration_seconds=110.0,
                request_timestamp=datetime.fromisoformat("2024-01-15T10:00:00+00:00"),
                response_timestamp=datetime.fromisoformat("2024-01-15T10:02:00+00:00"),
            )

    def test_response_before_request_validation(self) -> None:
        """Test validation fails when response timestamp is before request."""
        with pytest.raises(ValidationError):
            UsageRecord(
                transaction_id="test-transaction-004",
                api_session_id="test-session-001",
                customer_id="test-customer-001",
                connection_duration_seconds=120.5,
                data_bytes_processed=1024000,
                audio_duration_seconds=110.0,
                request_timestamp=datetime.fromisoformat("2024-01-15T10:02:00+00:00"),
                response_timestamp=datetime.fromisoformat("2024-01-15T10:00:00+00:00"),
            )


class TestEnrichedUsageRecord:
    """Test cases for EnrichedUsageRecord model."""

    def test_enriched_usage_record(self) -> None:
        """Test creating an enriched usage record."""
        record = EnrichedUsageRecord(
            transaction_id="test-transaction-005",
            api_session_id="test-session-001",
            customer_id="test-customer-001",
            connection_duration_seconds=120.5,
            data_bytes_processed=1024000,
            audio_duration_seconds=110.0,
            request_timestamp=datetime.fromisoformat("2024-01-15T10:00:00+00:00"),
            response_timestamp=datetime.fromisoformat("2024-01-15T10:02:00+00:00"),
            server_instance_id="server-001",
            api_server_region="us-east-1",
            agent_version="1.0.0",
        )
        
        assert record.server_instance_id == "server-001"
        assert record.api_server_region == "us-east-1"
        assert record.agent_version == "1.0.0"
        assert record.processing_timestamp is not None


class TestSessionLifecycleEvent:
    """Test cases for SessionLifecycleEvent model."""

    def test_session_start_event(self) -> None:
        """Test creating a session start event."""
        event = SessionLifecycleEvent(
            api_session_id="test-session-001",
            customer_id="test-customer-001",
            event_type=SessionEventType.START,
        )
        
        assert event.api_session_id == "test-session-001"
        assert event.customer_id == "test-customer-001"
        assert event.event_type == SessionEventType.START
        assert event.timestamp is not None

    def test_session_complete_event(self) -> None:
        """Test creating a session complete event."""
        event = SessionLifecycleEvent(
            api_session_id="test-session-001",
            customer_id="test-customer-001",
            event_type=SessionEventType.COMPLETE,
            metadata={"final_usage": 100.0},
        )
        
        assert event.event_type == SessionEventType.COMPLETE
        assert event.metadata == {"final_usage": 100.0}

    def test_invalid_event_type(self) -> None:
        """Test validation fails for invalid event type."""
        with pytest.raises(ValueError):
            # This should raise ValueError when trying to access invalid enum member
            SessionEventType["INVALID"]
 

class TestQuotaRefreshRequest:
    """Test cases for QuotaRefreshRequest model."""

    def test_valid_quota_request(self) -> None:
        """Test creating a valid quota refresh request."""
        request = QuotaRefreshRequest(
            transaction_id="test-transaction-001",
            api_session_id="test-session-001",
            customer_id="test-customer-001",
            current_usage=50.0,
            requested_quota=100.0,
        )
        
        assert request.api_session_id == "test-session-001"
        assert request.customer_id == "test-customer-001"
        assert request.current_usage == 50.0
        assert request.requested_quota == 100.0
        assert request.timestamp is not None

    def test_negative_usage_validation(self) -> None:
        """Test validation fails for negative current usage."""
        with pytest.raises(ValidationError):
            QuotaRefreshRequest(
                transaction_id="test-transaction-002",
                api_session_id="test-session-001",
                customer_id="test-customer-001",
                current_usage=-10.0,
                requested_quota=100.0,
            )

    def test_zero_quota_validation(self) -> None:
        """Test validation fails for zero requested quota."""
        with pytest.raises(ValidationError):
            QuotaRefreshRequest(
                transaction_id="test-transaction-003",
                api_session_id="test-session-001",
                customer_id="test-customer-001",
                current_usage=50.0,
                requested_quota=0.0,
            )


class TestRemoteCommand:
    """Test cases for RemoteCommand model."""

    def test_refresh_keys_command(self) -> None:
        """Test creating a refresh public keys command."""
        command = RemoteCommand(
            command_id="cmd-001",
            command_type=CommandType.REFRESH_PUBLIC_KEYS,
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00+00:00"),
        )
        
        assert command.command_id == "cmd-001"
        assert command.command_type == CommandType.REFRESH_PUBLIC_KEYS
        assert command.parameters is None

    def test_health_check_command(self) -> None:
        """Test creating a health check command."""
        command = RemoteCommand(
            command_id="cmd-002",
            command_type=CommandType.HEALTH_CHECK,
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00+00:00"),
            parameters={"include_details": True},
        )
        
        assert command.command_type == CommandType.HEALTH_CHECK
        assert command.parameters == {"include_details": True}

    def test_get_metrics_command(self) -> None:
        """Test creating a get metrics command."""
        command = RemoteCommand(
            command_id="cmd-003",
            command_type=CommandType.GET_METRICS,
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00+00:00"),
        )
        
        assert command.command_type == CommandType.GET_METRICS

    def test_invalid_command_type(self) -> None:
        """Test validation fails for invalid command type."""
        with pytest.raises(ValueError):
            # This should raise ValueError when trying to access invalid enum member
            CommandType["INVALID_COMMAND"]
