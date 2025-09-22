"""Connection state management for Control Plane connectivity.

This module provides a shared state manager to track Control Plane connectivity
across all services and implement circuit breaker patterns.
"""

import time
from typing import Optional
from threading import Lock


class ConnectionStateManager:
    """Manages connection state and implements circuit breaker logic for Control Plane."""
    
    def __init__(self, config):
        """Initialize connection state manager."""
        self.config = config
        self._lock = Lock()
        
        # Connection state tracking
        self._is_connected = True
        self._consecutive_failures = 0
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None
        
        # Circuit breaker state
        self._circuit_open = False
        self._circuit_open_time: Optional[float] = None
    
    def mark_success(self) -> None:
        """Mark a successful Control Plane operation."""
        with self._lock:
            self._is_connected = True
            self._consecutive_failures = 0
            self._last_success_time = time.time()
            self._circuit_open = False
            self._circuit_open_time = None
    
    def mark_failure(self) -> None:
        """Mark a failed Control Plane operation."""
        with self._lock:
            self._is_connected = False
            self._consecutive_failures += 1
            self._last_failure_time = time.time()
            
            # Open circuit if too many consecutive failures
            if self._consecutive_failures >= 3:
                self._circuit_open = True
                self._circuit_open_time = time.time()
    
    def get_backoff_delay(self) -> float:
        """Calculate the appropriate backoff delay based on failure history."""
        with self._lock:
            if self._consecutive_failures == 0:
                return 0.0
            
            # Calculate progressive backoff
            delay = self.config.control_plane_initial_error_delay * (
                self.config.control_plane_error_backoff_multiplier ** (self._consecutive_failures - 1)
            )
            
            # Cap at maximum backoff
            return min(delay, self.config.control_plane_max_backoff)
    
    def should_attempt_request(self) -> bool:
        """Determine if a request should be attempted based on circuit breaker state."""
        with self._lock:
            if not self._circuit_open:
                return True
            
            # Check if circuit should be half-open (allow test requests)
            if self._circuit_open_time and self._last_failure_time:
                time_since_open = time.time() - self._circuit_open_time
                # Allow test request after backoff delay
                backoff_delay = self.get_backoff_delay()
                if time_since_open >= backoff_delay:
                    return True
            
            return False
    
    def get_connection_info(self) -> dict:
        """Get current connection state information."""
        with self._lock:
            return {
                "is_connected": self._is_connected,
                "consecutive_failures": self._consecutive_failures,
                "circuit_open": self._circuit_open,
                "last_success_time": self._last_success_time,
                "last_failure_time": self._last_failure_time,
                "current_backoff_delay": self.get_backoff_delay(),
            }
    
    def is_healthy(self) -> bool:
        """Check if the connection is considered healthy."""
        with self._lock:
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