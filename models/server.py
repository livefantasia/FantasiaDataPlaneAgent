"""Server management models for DataPlane Agent."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ServerRegistration(BaseModel):
    """Server registration data."""

    server_id: str = Field(..., description="Unique server identifier")
    region: str = Field(..., description="Deployment region")
    version: str = Field(..., description="Server version")
    ip_address: str = Field(..., description="Server IP address")
    port: int = Field(..., ge=1, le=65535, description="Server port")
    capabilities: Dict[str, Any] = Field(
        default_factory=lambda: {
            "max_concurrent_sessions": 10,
            "supported_products": "speech_transcription",  # Comma-separated string as per MVP spec
            "supported_languages": "en-US",               # Comma-separated string as per MVP spec
        },
        description="Server capabilities with simplified string format per MVP spec"
    )


class HeartbeatData(BaseModel):
    """Heartbeat data."""

    status: str = Field(default="online", description="Server status")
    metrics: Optional[Dict[str, Union[int, float, str]]] = Field(
        default=None, description="Basic metrics"
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