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
from utils import create_contextual_logger
from .control_plane_client import ControlPlaneClient
from .redis_client import RedisClient

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

    def start(self) -> None:
        """Start background workers in the thread pool."""
        self.logger.info("Starting health and metrics workers...")
        self._shutdown_event.clear()
        self.executor.submit(self._heartbeat_worker)
        # Metrics collection can be added here if needed
        # self.executor.submit(self._metrics_worker)

    def stop(self) -> None:
        """Signal all background workers to stop."""
        self.logger.info("Stopping health and metrics workers...")
        self._shutdown_event.set()

    def _heartbeat_worker(self) -> None:
        """Synchronous worker to manage registration and send heartbeats."""
        self.logger.info("Heartbeat worker started.")
        while not self._shutdown_event.is_set():
            try:
                if not self._registered:
                    self._perform_registration()
                
                if self._registered:
                    self._send_heartbeat()
                
                # The sleep interval depends on whether we are registered
                interval = self.config.heartbeat_interval if self._registered else self.config.control_plane_initial_error_delay
                # Use event.wait for an interruptible sleep
                self._shutdown_event.wait(timeout=interval)

            except Exception as e:
                self.logger.error(f"Unhandled error in heartbeat worker: {e}", exc_info=True)
                # On error, wait for a bit before restarting the loop
                self._shutdown_event.wait(timeout=self.config.control_plane_initial_error_delay)
        self.logger.info("Heartbeat worker stopped.")

    def _perform_registration(self) -> None:
        """Attempt to register the server, with simple retry logic."""
        for attempt in range(self.config.control_plane_retry_attempts):
            if self._shutdown_event.is_set():
                break
            try:
                self.logger.info(f"Attempting server registration (attempt {attempt + 1})...")
                registration_data = ServerRegistration(
                    server_id=self.config.server_id,
                    region=self.config.server_region,
                    version=self.config.app_version,
                    ip_address=self.config.server_ip,
                    port=self.config.server_port,
                    capabilities={ "max_concurrent_sessions": 100, "supported_products": "speech_transcription", "supported_languages": "en-US" },
                )
                self.control_plane_client.register_server_sync(registration_data)
                self.logger.info("Server registered successfully.")
                self._registered = True
                return  # Exit on success
            except Exception as e:
                self.logger.warning(f"Registration attempt {attempt + 1} failed: {e}")
                if attempt < self.config.control_plane_retry_attempts - 1:
                    time.sleep(self.config.control_plane_initial_error_delay)
        
        self.logger.error("Server registration failed after all attempts.")

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

    def _send_heartbeat(self) -> None:
        """Send a single heartbeat."""
        try:
            # Health status logic simplified for sync context
            redis_ok = self.redis_client.is_connected_sync()
            status = "online" if redis_ok else "degraded"

            heartbeat_data = HeartbeatData(
                status=status,
                metrics={
                    "uptime_seconds": int(time.time() - self._start_time),
                    "redis_connected": 1 if redis_ok else 0,
                    "control_plane_connected": 1, # Assume connected if we can send a heartbeat
                },
            )
            self.control_plane_client.send_heartbeat_sync(self.config.server_id, heartbeat_data)
        except Exception as e:
            self.logger.warning(f"Heartbeat failed: {e}. Marking server as unregistered.")
            self._registered = False # If heartbeat fails, re-register on next loop
