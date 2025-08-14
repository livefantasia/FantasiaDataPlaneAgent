"""Command management models for DataPlane Agent."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .enums import CommandType


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