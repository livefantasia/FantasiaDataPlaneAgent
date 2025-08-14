"""Quota management models for DataPlane Agent."""

from datetime import datetime

from pydantic import BaseModel, Field


class QuotaRefreshRequest(BaseModel):
    """Request for quota refresh."""

    transaction_id: str = Field(..., description="Unique transaction identifier for idempotency")
    api_session_id: str = Field(..., description="Session identifier")
    customer_id: str = Field(..., description="Customer identifier")
    current_usage: float = Field(..., ge=0, description="Current usage for the session")
    requested_quota: float = Field(..., gt=0, description="Requested quota amount")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Request timestamp"
    )


class QuotaRefreshResponse(BaseModel):
    """Response for quota refresh request."""

    api_session_id: str = Field(..., description="Session identifier")
    new_quota_amount: float = Field(..., ge=0, description="Newly allocated quota amount")
    final_quota: bool = Field(default=False, description="Whether this is the final quota allocation")
    transaction_id: str = Field(..., description="Transaction identifier for idempotency")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Response timestamp"
    )