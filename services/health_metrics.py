"""Health and metrics service for DataPlane Agent.

This service provides health monitoring and metrics collection.
"""

import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from prometheus_client import Counter, Gauge, Histogram, generate_latest

from config import ApplicationConfig
from models import HeartbeatData, ServerRegistration
from utils import create_contextual_logger, set_correlation_id
from .control_plane_client import ControlPlaneClient
from .redis_client import RedisClient

class RetryHelper:
    """Manages retry state and exponential backoff for a worker."""
    def __init__(self, config: ApplicationConfig, logger):
        self.config = config
        self.logger = logger
        self.consecutive_failures = 0
        self.circuit_open = False

    def mark_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.config.control_plane_retry_attempts:
            if not self.circuit_open:
                self.logger.warning("Circuit breaker OPENED due to repeated failures.")
                self.circuit_open = True

    def mark_success(self):
        if self.circuit_open:
            self.logger.info("Circuit breaker CLOSED after successful connection.")
        self.consecutive_failures = 0
        self.circuit_open = False

    def get_backoff_delay(self) -> float:
        if self.consecutive_failures == 0:
            return 0.0
        
        delay = self.config.control_plane_initial_error_delay * (2 ** (self.consecutive_failures - 1))
        capped_delay = min(delay, self.config.control_plane_max_backoff)
        
        self.logger.info(
            f"Next retry in {capped_delay:.2f} seconds...",
            consecutive_failures=self.consecutive_failures,
            delay_seconds=capped_delay
        )
        return capped_delay

# Prometheus metrics definitions remain the same...
usage_records_processed = Counter(
    "usage_records_processed_total",
    "Total number of usage records processed",
    ["server_id", "status"]
)

session_events_processed = Counter(
    "session_events_processed_total", 
    "Total number of session events processed",
    ["server_id", "event_type", "status"]
)

# ... other metrics ...

class HealthMetricsService:
    """Service for health monitoring and metrics, using a threaded worker model."""

    def __init__(
        self,
        config: ApplicationConfig,
        redis_client: RedisClient,
        control_plane_client: ControlPlaneClient,
        executor: ThreadPoolExecutor,
    ) -> None:
        self.config = config
        self.redis_client = redis_client
        self.control_plane_client = control_plane_client
        self.executor = executor
        self.logger = create_contextual_logger(__name__, service="health_metrics")
        
        self._start_time = time.time()
        self._shutdown_event = threading.Event()
        self._registered = False
        self._retry_helper = RetryHelper(config, self.logger)

    def start(self) -> None:
        """Start background workers in the thread pool."""
        self.logger.info("Starting health and metrics workers...")
        self._shutdown_event.clear()
        self.executor.submit(self._heartbeat_worker)

    def stop(self) -> None:
        """Signal all background workers to stop."""
        self.logger.info("Stopping health and metrics workers...")
        self._shutdown_event.set()

    def _heartbeat_worker(self) -> None:
        """Synchronous worker to manage registration and send heartbeats."""
        self.logger.info("Heartbeat worker started.")
        while not self._shutdown_event.is_set():
            # Set a new correlation ID for each iteration
            correlation_id = str(uuid.uuid4())
            set_correlation_id(correlation_id)

            try:
                if not self._registered:
                    self._perform_registration()
                else: # Only send heartbeat if registered
                    self._send_heartbeat()
                
                # If we were successful, use the normal heartbeat interval
                self._retry_helper.mark_success()
                self.logger.debug("Heartbeat loop completed successfully, waiting for next interval.")
                self._shutdown_event.wait(timeout=self.config.heartbeat_interval)

            except Exception as e:
                self.logger.warning(f"Heartbeat loop failed: {e}")
                self._retry_helper.mark_failure()
                delay = self._retry_helper.get_backoff_delay()
                self._shutdown_event.wait(timeout=delay)

        self.logger.info("Heartbeat worker stopped.")

    def _perform_registration(self) -> None:
        """Attempt to register the server. Raises exception on failure."""
        self.logger.info("Attempting server registration...")
        registration_data = ServerRegistration(
            server_id=self.config.server_id,
            region=self.config.server_region,
            version=self.config.app_version,
            ip_address=self.config.dataplane_host,
            port=self.config.dataplane_port,
            capabilities={ "max_concurrent_sessions": 100, "supported_products": "speech_transcription", "supported_languages": "en-US" },
        )
        self.control_plane_client.register_server_sync(registration_data)
        self.logger.info("Server registered successfully.")
        self._registered = True

    def _send_heartbeat(self) -> None:
        """Send a single heartbeat. Raises exception on failure."""
        redis_ok = self.redis_client.is_connected_sync()
        status = "online" if redis_ok else "degraded"
        heartbeat_data = HeartbeatData(
            status=status,
            metrics={
                "uptime_seconds": int(time.time() - self._start_time),
                "redis_connected": 1 if redis_ok else 0,
                "control_plane_connected": 1,
            },
        )
        self.control_plane_client.send_heartbeat_sync(self.config.server_id, heartbeat_data)
        self.logger.debug("Heartbeat sent successfully.")

    def get_health_status_sync(self) -> Dict[str, Any]:
        """Get a simplified, synchronous health status."""
        redis_ok = self.redis_client.is_connected_sync()
        status = "unhealthy"
        if self._registered and redis_ok:
            status = "healthy"
        elif self._registered or redis_ok:
            status = "degraded"

        return {
            "status": status,
            "redis_connected": redis_ok,
            "server_registered": self._registered,
        }
