"""Logging utilities for DataPlane Agent.

This module provides structured logging with support for both JSON and console output,
comprehensive context information, and proper error handling.
"""

import json
import logging
import os
import sys
import threading
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

import structlog

# Context variable for correlation ID
correlation_id_context: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def _log4j_formatter(logger: Any, name: str, event_dict: Dict[str, Any]) -> str:
    """Format logs in log4j style: timestamp [level]: message {json_context}"""
    # Extract core fields
    timestamp = event_dict.pop("timestamp", "")
    level = event_dict.pop("level", "info")
    event = event_dict.pop("event", "")
    
    # Remove logger name from context since we'll use it in the message
    event_dict.pop("logger", None)
    
    # Format the log line
    if event_dict:
        # Convert remaining context to JSON
        context_json = json.dumps(event_dict, sort_keys=True, separators=(',', ':'))
        return f"{timestamp} [{level}]: {event} {context_json}"
    else:
        return f"{timestamp} [{level}]: {event}"


def _add_system_context(logger: Any, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add system context like process ID, thread ID, and hostname."""
    event_dict["pid"] = os.getpid()
    event_dict["hostname"] = os.uname().nodename
    
    # Add correlation ID if available
    correlation_id = correlation_id_context.get()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    
    return event_dict


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID for the current context.
    
    Args:
        correlation_id: The correlation ID to set. If None, generates a new UUID.
        
    Returns:
        The correlation ID that was set.
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    
    correlation_id_context.set(correlation_id)
    return correlation_id


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return correlation_id_context.get()


def clear_correlation_id() -> None:
    """Clear the current correlation ID."""
    correlation_id_context.set(None)


def configure_logging(log_level: str = "INFO", json_output: bool = True, include_system_context: bool = True) -> None:
    """Configure structured logging with log4j-style formatting.
    
    Args:
        log_level: The minimum log level to output (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output pure JSON format. If False, use log4j-style format.
        include_system_context: If True, include system context like PID, hostname.
    """
    
    # Clear any existing handlers
    logging.getLogger().handlers.clear()
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
        force=True,
    )

    # Suppress noisy third-party library logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    # Build processors list
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    # Add system context if requested
    if include_system_context:
        processors.append(_add_system_context)
    
    # Add final formatting processor
    processors.append(structlog.processors.UnicodeDecoder())
    
    if json_output:
        # Pure JSON output
        processors.append(structlog.processors.JSONRenderer(sort_keys=True))
    else:
        # log4j-style output: timestamp [level]: message {json_context}
        processors.append(_log4j_formatter)

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Get a configured logger with optional initial context.
    
    Args:
        name: The logger name (typically __name__ or module path)
        **initial_context: Initial context to bind to the logger
        
    Returns:
        A bound logger instance with the given name and context
    """
    logger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


def get_logger_for_class(cls_instance: Any, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Get a logger for a class instance with class context.
    
    Args:
        cls_instance: The class instance to create a logger for
        **initial_context: Additional initial context
        
    Returns:
        A bound logger with class and context information
    """
    class_name = cls_instance.__class__.__name__
    module_name = cls_instance.__class__.__module__
    logger_name = f"{module_name}.{class_name}"
    
    context = {"class": class_name}
    context.update(initial_context)
    
    return get_logger(logger_name, **context)


class CorrelationIdFilter(logging.Filter):
    """Filter to add correlation ID to log records."""

    def __init__(self, correlation_id: Optional[str] = None) -> None:
        super().__init__()
        self.correlation_id = correlation_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to log record."""
        if self.correlation_id:
            record.correlation_id = self.correlation_id  # type: ignore
        return True


def create_contextual_logger(
    name: str,
    correlation_id: Optional[str] = None,
    **context: Any
) -> structlog.stdlib.BoundLogger:
    """Create a logger with correlation ID and additional context.
    
    Args:
        name: The logger name (typically __name__ or module path)
        correlation_id: Optional correlation ID. If not provided, uses current context ID.
        **context: Additional context fields to bind to the logger
        
    Returns:
        A bound logger with correlation ID and context
    """
    logger = get_logger(name)
    
    bind_context: Dict[str, Any] = {}
    
    # Use provided correlation ID or get from context
    if correlation_id:
        bind_context["correlation_id"] = correlation_id
    elif get_correlation_id():
        bind_context["correlation_id"] = get_correlation_id()
    
    # Add any additional context
    if context:
        bind_context.update(context)
    
    if bind_context:
        logger = logger.bind(**bind_context)
    
    return logger


def log_exception(
    logger: structlog.stdlib.BoundLogger,
    exception: Exception,
    message: str = "An error occurred",
    **additional_context: Any
) -> None:
    """Log an exception with full context and stack trace.
    
    Args:
        logger: The logger to use
        exception: The exception that occurred
        message: A descriptive message about the error
        **additional_context: Additional context to include in the log
    """
    context = {
        "exception_type": type(exception).__name__,
        "exception_message": str(exception),
        **additional_context
    }
    
    logger.error(message, exc_info=True, **context)
