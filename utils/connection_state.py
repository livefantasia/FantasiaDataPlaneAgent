"""Connection state management for Control Plane connectivity.

This module provides a shared state manager to track Control Plane connectivity
across all services and implement circuit breaker patterns.
"""

import asyncio
import time
import logging
from typing import Optional
from asyncio import Lock


class ConnectionStateManager:
    """Manages connection state and implements circuit breaker logic for Control Plane."""
    
    def __init__(self, config):
        """Initialize connection state manager."""
        self.config = config
        self._lock = Lock()
        self.logger = logging.getLogger(__name__)
        
        # Connection state tracking
        self._is_connected = True
        self._consecutive_failures = 0
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None
        
        # Circuit breaker state
        self._circuit_open = False
        self._circuit_open_time: Optional[float] = None
    
    async def mark_success(self) -> None:
        """Mark a successful Control Plane operation."""
        async with self._lock:
            was_circuit_open = self._circuit_open
            consecutive_failures_before = self._consecutive_failures
            
            self._is_connected = True
            self._consecutive_failures = 0
            self._last_success_time = time.time()
            self._circuit_open = False
            self._circuit_open_time = None
            
            if was_circuit_open:
                self.logger.info(
                    "Circuit breaker CLOSED - Connection recovered",
                    previous_failures=consecutive_failures_before,
                    downtime_seconds=int(time.time() - (self._last_failure_time or 0)),
                )
            elif consecutive_failures_before > 0:
                self.logger.info(
                    "Connection stabilized after failures",
                    recovered_from_failures=consecutive_failures_before,
                )
    
    async def mark_failure(self) -> None:
        """Mark a failed Control Plane operation."""
        async with self._lock:
            self._is_connected = False
            self._consecutive_failures += 1
            self._last_failure_time = time.time()
            
            if self._consecutive_failures >= 3:
                was_already_open = self._circuit_open
                self._circuit_open = True
                self._circuit_open_time = time.time()
                
                if not was_already_open:
                    next_backoff = await self.get_backoff_delay()
                    self.logger.warning(
                        "Circuit breaker OPENED - Too many consecutive failures",
                        consecutive_failures=self._consecutive_failures,
                        next_retry_delay_seconds=next_backoff,
                    )
            else:
                self.logger.debug(
                    "Connection failure recorded",
                    consecutive_failures=self._consecutive_failures,
                    failures_until_circuit_open=3 - self._consecutive_failures,
                )
    
    async def get_backoff_delay(self) -> float:
        """Calculate the appropriate backoff delay based on failure history."""
        async with self._lock:
            if self._consecutive_failures == 0:
                return 0.0
            
            delay = self.config.control_plane_initial_error_delay * (
                self.config.control_plane_error_backoff_multiplier ** (self._consecutive_failures - 1)
            )
            
            return min(delay, self.config.control_plane_max_backoff)
    
    async def should_attempt_request(self) -> bool:
        """Determine if a request should be attempted based on circuit breaker state."""
        async with self._lock:
            if not self._circuit_open:
                return True
            
            if self._circuit_open_time and self._last_failure_time:
                time_since_open = time.time() - self._circuit_open_time
                backoff_delay = await self.get_backoff_delay()
                if time_since_open >= backoff_delay:
                    self.logger.info(
                        "Circuit breaker entering HALF-OPEN state - Allowing test request",
                        time_since_open_seconds=int(time_since_open),
                        backoff_delay_seconds=backoff_delay,
                    )
                    return True
                else:
                    self.logger.debug(
                        "Circuit breaker still OPEN - Request blocked",
                        remaining_wait_seconds=int(backoff_delay - time_since_open),
                    )
            
            return False
    
    async def get_connection_info(self) -> dict:
        """Get current connection state information."""
        async with self._lock:
            return {
                "is_connected": self._is_connected,
                "consecutive_failures": self._consecutive_failures,
                "circuit_open": self._circuit_open,
                "last_success_time": self._last_success_time,
                "last_failure_time": self._last_failure_time,
                "current_backoff_delay": await self.get_backoff_delay(),
            }
    
    async def is_healthy(self) -> bool:
        """Check if the connection is considered healthy."""
        async with self._lock:
            return self._is_connected and not self._circuit_open


# Global connection state manager instance
_connection_state_manager: Optional[ConnectionStateManager] = None


def get_connection_state_manager(config=None) -> ConnectionStateManager:
    """Get or create the global connection state manager."""
    global _connection_state_manager
    if _connection_state_manager is None:
        if config is None:
            raise RuntimeError("Connection state manager not initialized and no config provided")
        _connection_state_manager = ConnectionStateManager(config)
    return _connection_state_manager


def initialize_connection_state_manager(config) -> None:
    """Initialize the global connection state manager."""
    global _connection_state_manager
    _connection_state_manager = ConnectionStateManager(config)