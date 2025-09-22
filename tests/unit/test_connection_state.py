"""Test the connection state manager and circuit breaker functionality."""

import pytest
import time
from unittest.mock import Mock

from utils.connection_state import ConnectionStateManager


class TestConnectionStateManager:
    """Test cases for ConnectionStateManager."""

    def test_initial_state(self):
        """Test initial connection state."""
        config = Mock()
        config.control_plane_initial_error_delay = 5
        config.control_plane_error_backoff_multiplier = 2.0
        config.control_plane_max_backoff = 300
        
        manager = ConnectionStateManager(config)
        
        assert manager.is_healthy()
        assert manager.should_attempt_request()
        assert manager.get_backoff_delay() == 0.0
        
        info = manager.get_connection_info()
        assert info["is_connected"] is True
        assert info["consecutive_failures"] == 0
        assert info["circuit_open"] is False

    def test_single_failure(self):
        """Test behavior after a single failure."""
        config = Mock()
        config.control_plane_initial_error_delay = 5
        config.control_plane_error_backoff_multiplier = 2.0
        config.control_plane_max_backoff = 300
        
        manager = ConnectionStateManager(config)
        manager.mark_failure()
        
        assert not manager.is_healthy()
        assert manager.should_attempt_request()  # Circuit not open yet
        assert manager.get_backoff_delay() == 5.0
        
        info = manager.get_connection_info()
        assert info["is_connected"] is False
        assert info["consecutive_failures"] == 1
        assert info["circuit_open"] is False

    def test_circuit_breaker_opens_after_failures(self):
        """Test that circuit opens after multiple failures."""
        config = Mock()
        config.control_plane_initial_error_delay = 5
        config.control_plane_error_backoff_multiplier = 2.0
        config.control_plane_max_backoff = 300
        
        manager = ConnectionStateManager(config)
        
        # Mark 3 failures to open the circuit
        manager.mark_failure()
        manager.mark_failure()
        manager.mark_failure()
        
        assert not manager.is_healthy()
        assert not manager.should_attempt_request()  # Circuit is open
        assert manager.get_backoff_delay() == 20.0  # 5 * 2^2
        
        info = manager.get_connection_info()
        assert info["circuit_open"] is True
        assert info["consecutive_failures"] == 3

    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        config = Mock()
        config.control_plane_initial_error_delay = 5
        config.control_plane_error_backoff_multiplier = 2.0
        config.control_plane_max_backoff = 300
        
        manager = ConnectionStateManager(config)
        
        # Test backoff progression
        manager.mark_failure()
        assert manager.get_backoff_delay() == 5.0  # 5 * 2^0
        
        manager.mark_failure()
        assert manager.get_backoff_delay() == 10.0  # 5 * 2^1
        
        manager.mark_failure()
        assert manager.get_backoff_delay() == 20.0  # 5 * 2^2
        
        manager.mark_failure()
        assert manager.get_backoff_delay() == 40.0  # 5 * 2^3

    def test_backoff_cap(self):
        """Test that backoff is capped at maximum value."""
        config = Mock()
        config.control_plane_initial_error_delay = 5
        config.control_plane_error_backoff_multiplier = 2.0
        config.control_plane_max_backoff = 60  # Low cap for testing
        
        manager = ConnectionStateManager(config)
        
        # Mark many failures to exceed the cap
        for _ in range(10):
            manager.mark_failure()
        
        assert manager.get_backoff_delay() == 60.0  # Capped at max

    def test_success_resets_state(self):
        """Test that success resets the failure state."""
        config = Mock()
        config.control_plane_initial_error_delay = 5
        config.control_plane_error_backoff_multiplier = 2.0
        config.control_plane_max_backoff = 300
        
        manager = ConnectionStateManager(config)
        
        # Mark failures and then success
        manager.mark_failure()
        manager.mark_failure()
        manager.mark_failure()  # Circuit should be open
        
        assert not manager.is_healthy()
        assert not manager.should_attempt_request()
        
        # Mark success
        manager.mark_success()
        
        assert manager.is_healthy()
        assert manager.should_attempt_request()
        assert manager.get_backoff_delay() == 0.0
        
        info = manager.get_connection_info()
        assert info["is_connected"] is True
        assert info["consecutive_failures"] == 0
        assert info["circuit_open"] is False