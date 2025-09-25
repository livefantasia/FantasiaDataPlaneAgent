"""Middleware for handling correlation IDs in FastAPI requests."""

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from utils import set_correlation_id, get_logger

logger = get_logger(__name__)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware to handle correlation IDs for requests."""
    
    def __init__(self, app, correlation_header: str = "X-Correlation-ID"):
        super().__init__(app)
        self.correlation_header = correlation_header
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Set correlation ID for the request context."""
        # Get correlation ID from header or generate new one
        correlation_id = request.headers.get(self.correlation_header)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Set correlation ID in context
        set_correlation_id(correlation_id)
        
        # Add to request state for access in route handlers
        request.state.correlation_id = correlation_id
        
        # Log the incoming request
        logger.info(
            f"HTTP request received: {request.method} {request.url.path}",
            serviceName="CorrelationMiddleware",
            operationName="handleRequest",
            method=request.method,
            path=request.url.path,
            user_agent=request.headers.get("user-agent"),
            client_ip=request.client.host if request.client else None,
        )
        
        # Process the request
        response = await call_next(request)
        
        # Add correlation ID to response headers
        response.headers[self.correlation_header] = correlation_id
        
        # Log the response
        logger.info(
            f"HTTP request completed: {request.method} {request.url.path}",
            serviceName="CorrelationMiddleware", 
            operationName="handleRequest",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            success=200 <= response.status_code < 400,
        )
        
        return response