"""Logging utilities for DataPlane Agent.

This module provides structured logging using structlog for JSON output.
"""

import logging
import sys
from typing import Any, Dict, Optional

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structured logging with JSON output."""
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Get a configured logger with optional initial context."""
    logger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


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
    """Create a logger with correlation ID and additional context."""
    logger = get_logger(name)
    
    bind_context: Dict[str, Any] = {}
    if correlation_id:
        bind_context["correlation_id"] = correlation_id
    if context:
        bind_context.update(context)
    
    if bind_context:
        logger = logger.bind(**bind_context)
    
    return logger
