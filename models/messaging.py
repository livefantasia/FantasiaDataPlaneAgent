"""Messaging models for DataPlane Agent."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


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