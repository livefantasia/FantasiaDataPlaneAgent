"""Enumeration types for DataPlane Agent models."""

from enum import Enum


class ProductCode(str, Enum):
    """Product codes for billing and usage tracking"""

    SPEECH_TRANSCRIPTION = "speech_transcription"
    SPEECH_SYNTHESIS = "speech_synthesis"
    REAL_TIME_STREAMING = "real_time_streaming"


class SessionEventType(str, Enum):
    """Types of session lifecycle events."""

    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"


class CommandType(str, Enum):
    """Types of remote commands."""

    REFRESH_PUBLIC_KEYS = "refresh_public_keys"
    HEALTH_CHECK = "health_check"
    GET_METRICS = "get_metrics"


class SessionCompletionReason(str, Enum):
    """Session completion reasons matching ControlPlane expectations."""
    
    CLIENT_CLOSE = "CLIENT_CLOSE"
    CLIENT_ERROR = "CLIENT_ERROR"
    STREAM_END = "STREAM_END"
    INVALID_MESSAGE = "INVALID_MESSAGE"
    SESSION_TIMEOUT = "SESSION_TIMEOUT"
    OUT_OF_CREDIT = "OUT_OF_CREDIT"
    SERVER_ERROR = "SERVER_ERROR"
    SERVER_SHUTDOWN = "SERVER_SHUTDOWN"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"