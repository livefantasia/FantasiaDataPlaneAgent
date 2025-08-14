"""Usage tracking models for DataPlane Agent."""

from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator, ConfigDict

from .enums import ProductCode


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

    @field_validator("response_timestamp")
    @classmethod
    def response_after_request(
        cls, v: datetime, info
    ) -> datetime:
        """Ensure response timestamp is after request timestamp."""
        if "request_timestamp" in info.data and v < info.data["request_timestamp"]:
            raise ValueError("response_timestamp must be after request_timestamp")
        return v

    model_config = ConfigDict(use_enum_values=True)


class EnrichedUsageRecord(UsageRecord):
    """Usage record enriched with server metadata."""

    server_instance_id: str = Field(..., description="Server instance identifier")
    api_server_region: str = Field(..., description="Server deployment region")
    processing_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When record was processed"
    )
    agent_version: str = Field(..., description="DataPlane agent version")