"""Enumeration types for DataPlane Agent models."""

from enum import Enum


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