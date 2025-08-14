"""Session management models for DataPlane Agent."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .enums import SessionEventType


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
    final_usage_summary: Optional[Dict[str, Any]] = Field(
        default=None, description="Final authoritative usage summary for session completion"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional event metadata"
    )

    class Config:
        """Pydantic model configuration."""
        use_enum_values = True