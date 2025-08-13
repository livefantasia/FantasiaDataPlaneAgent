"""Data models for DataPlane Agent.

This module contains all Pydantic models used throughout the application,
ensuring strict type safety and runtime validation.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


class ProductCode(str, Enum):
    """Available product codes."""

    SPEECH_TO_TEXT_STANDARD = "SPEECH_TO_TEXT_STANDARD"


class SessionEventType(str, Enum):
    """Types of session lifecycle events."""

    START = "start"
    COMPLETE = "complete"


class CommandType(str, Enum):
    """Types of remote commands."""

    REFRESH_PUBLIC_KEYS = "refresh_public_keys"
    HEALTH_CHECK = "health_check"
    GET_METRICS = "get_metrics"


class UsageRecord(BaseModel):
    """Usage record from AudioAPIServer."""

    transaction_id: str = Field(..., description="Unique transaction identifier for idempotency")
    api_session_id: str = Field(..., description="Unique session identifier")
    customer_id: str = Field(..., description="Customer identifier")
    product_code: ProductCode = Field(
        default=ProductCode.SPEECH_TO_TEXT_STANDARD,
        description="Product code for billing",
    )
    connection_duration_seconds: float = Field(
        ..., ge=0, description="Total connection duration in seconds"
    )
    data_bytes_processed: int = Field(
        ..., ge=0, description="Total bytes of data processed"
    )
    audio_duration_seconds: float = Field(
        ..., ge=0, description="Total audio duration processed in seconds"
    )
    request_timestamp: datetime = Field(..., description="When request was initiated")
    response_timestamp: datetime = Field(..., description="When response was sent")

    @validator("response_timestamp")
    def response_after_request(
        cls, v: datetime, values: Dict[str, Any]
    ) -> datetime:
        """Ensure response timestamp is after request timestamp."""
        if "request_timestamp" in values and v < values["request_timestamp"]:
            raise ValueError("response_timestamp must be after request_timestamp")
        return v

    class Config:
        """Pydantic model configuration."""
        use_enum_values = True


class EnrichedUsageRecord(UsageRecord):
    """Usage record enriched with server metadata."""

    server_instance_id: str = Field(..., description="Server instance identifier")
    api_server_region: str = Field(..., description="Server deployment region")
    processing_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When record was processed"
    )
    agent_version: str = Field(..., description="DataPlane agent version")


class SessionLifecycleEvent(BaseModel):
    """Session lifecycle event."""

    api_session_id: str = Field(..., description="Session identifier")
    customer_id: str = Field(..., description="Customer identifier")
    event_type: SessionEventType = Field(..., description="Type of lifecycle event")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
    disconnect_reason: Optional[str] = Field(
        default=None, description="Reason for session completion"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional event metadata"
    )

    class Config:
        """Pydantic model configuration."""
        use_enum_values = True


class QuotaRefreshRequest(BaseModel):
    """Request for quota refresh."""

    transaction_id: str = Field(..., description="Unique transaction identifier for idempotency")
    api_session_id: str = Field(..., description="Session identifier")
    customer_id: str = Field(..., description="Customer identifier")
    current_usage_seconds: float = Field(..., ge=0, description="Current usage in seconds for the session")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Request timestamp"
    )


class ServerRegistration(BaseModel):
    """Server registration data."""

    server_id: str = Field(..., description="Unique server identifier")
    region: str = Field(..., description="Deployment region")
    version: str = Field(..., description="Server version")
    ip_address: str = Field(..., description="Server IP address")
    port: int = Field(..., ge=1, le=65535, description="Server port")
    capabilities: List[str] = Field(
        default_factory=list, description="Server capabilities"
    )


class HeartbeatData(BaseModel):
    """Heartbeat data."""

    server_id: str = Field(..., description="Server identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Heartbeat timestamp"
    )
    status: str = Field(default="healthy", description="Server status")
    metrics: Optional[Dict[str, Union[int, float, str]]] = Field(
        default=None, description="Basic metrics"
    )


class RemoteCommand(BaseModel):
    """Remote command from ControlPlane."""

    command_id: str = Field(..., description="Unique command identifier")
    command_type: CommandType = Field(..., description="Type of command")
    parameters: Optional[Dict[str, Any]] = Field(
        default=None, description="Command parameters"
    )
    timestamp: datetime = Field(..., description="Command timestamp")

    class Config:
        """Pydantic model configuration."""
        use_enum_values = True


class CommandResult(BaseModel):
    """Result of command execution."""

    command_id: str = Field(..., description="Command identifier")
    success: bool = Field(..., description="Whether command succeeded")
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Command result data"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if failed"
    )
    execution_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Execution timestamp"
    )


class HealthStatus(BaseModel):
    """Health status response."""

    status: str = Field(..., description="Overall health status")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Status timestamp"
    )
    version: str = Field(..., description="Agent version")
    uptime_seconds: int = Field(..., ge=0, description="Uptime in seconds")
    redis_connected: bool = Field(..., description="Redis connection status")
    control_plane_connected: bool = Field(
        ..., description="ControlPlane connection status"
    )
    components: Optional[Dict[str, str]] = Field(
        default=None, description="Component statuses"
    )


class MetricsData(BaseModel):
    """Basic metrics data."""

    server_id: str = Field(..., description="Server identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Metrics timestamp"
    )
    usage_records_processed: int = Field(
        ..., ge=0, description="Total usage records processed"
    )
    control_plane_requests: int = Field(
        ..., ge=0, description="Total ControlPlane requests"
    )
    redis_queue_depth: int = Field(..., ge=0, description="Current Redis queue depth")
    failed_deliveries: int = Field(..., ge=0, description="Failed delivery count")
    memory_usage_mb: float = Field(..., ge=0, description="Memory usage in MB")
    cpu_usage_percent: float = Field(
        ..., ge=0, le=100, description="CPU usage percentage"
    )


class RedisMessage(BaseModel):
    """Generic Redis message wrapper."""

    message_type: str = Field(..., description="Type of message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Message timestamp"
    )
    data: Dict[str, Any] = Field(..., description="Message payload")
    correlation_id: Optional[str] = Field(
        default=None, description="Correlation ID for tracing"
    )
