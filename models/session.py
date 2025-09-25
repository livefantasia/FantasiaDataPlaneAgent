"""Session management models for DataPlane Agent."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict

from .enums import SessionEventType, SessionCompletionReason


class FinalUsageSummary(BaseModel):
    """Final usage summary matching ControlPlane expectations."""
    
    total_duration_seconds: float = Field(..., ge=0, description="Total connection duration")
    total_bytes_processed: int = Field(..., ge=0, description="Total bytes processed")
    total_audio_seconds: float = Field(..., ge=0, description="Total audio duration")
    total_request_count: int = Field(..., ge=0, description="Total number of requests")
    last_request_timestamp: datetime = Field(..., description="Timestamp of last request")


class SessionLifecycleEvent(BaseModel):
    """Session lifecycle event."""

    api_session_id: str = Field(..., description="Session identifier")
    customer_id: str = Field(..., description="Customer identifier")
    event_type: SessionEventType = Field(..., description="Type of lifecycle event")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
    disconnect_reason: Optional[SessionCompletionReason] = Field(
        default=None, description="Reason for session completion"
    )
    final_usage_summary: Optional[FinalUsageSummary] = Field(
        default=None, description="Final authoritative usage summary for session completion"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional event metadata"
    )

    model_config = ConfigDict(use_enum_values=True)