"""Health and metrics service for DataPlane Agent.

This service provides health monitoring and metrics collection.
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from prometheus_client import Counter, Gauge, Histogram, generate_latest

from config import ApplicationConfig, ControlPlaneConfig
from models import HeartbeatData, ServerRegistration
from utils import create_contextual_logger
from .control_plane_client import ControlPlaneClient
from .redis_client import RedisClient


# Prometheus metrics
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

quota_requests_processed = Counter(
    "quota_requests_processed_total",
    "Total number of quota refresh requests processed", 
    ["server_id", "status"]
)

control_plane_requests = Counter(
    "control_plane_requests_total",
    "Total number of ControlPlane API requests",
    ["server_id", "endpoint", "status"]
)

redis_queue_depth = Gauge(
    "redis_queue_depth",
    "Current depth of Redis queues",
    ["server_id", "queue_name"]
)

redis_connection_status = Gauge(
    "redis_connection_status",
    "Redis connection status (1=connected, 0=disconnected)",
    ["server_id"]
)

control_plane_connection_status = Gauge(
    "control_plane_connection_status", 
    "ControlPlane connection status (1=connected, 0=disconnected)",
    ["server_id"]
)

request_duration = Histogram(
    "request_duration_seconds",
    "Request duration in seconds",
    ["server_id", "service", "operation"]
)


class HealthMetricsService:
    """Service for health monitoring and metrics collection."""

    def __init__(
        self,
        config: ApplicationConfig,
        redis_client: RedisClient,
        control_plane_client: ControlPlaneClient,
    ) -> None:
        """Initialize health and metrics service."""
        self.config = config
        self.redis_client = redis_client
        self.control_plane_client = control_plane_client
        self.logger = create_contextual_logger(__name__, service="health_metrics")
        
        self._start_time = time.time()
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._metrics_task: Optional[asyncio.Task[None]] = None
        self._registered = False

    async def start(self) -> None:
        """Start health monitoring and metrics collection."""
        if self._running:
            return

        self._running = True
        
        # Register server with ControlPlane
        await self._register_server()
        
        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._metrics_task = asyncio.create_task(self._metrics_collection_loop())
        
        self.logger.info("Health and metrics service started")

    async def stop(self) -> None:
        """Stop health monitoring and metrics collection."""
        if not self._running:
            return

        self._running = False
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._metrics_task:
            self._metrics_task.cancel()
        
        # Wait for tasks to complete
        tasks = [t for t in [self._heartbeat_task, self._metrics_task] if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.logger.info("Health and metrics service stopped")

    async def _register_server(self) -> None:
        """Register this server with ControlPlane."""
        try:
            registration_data = ServerRegistration(
                server_id=self.config.server_id,
                region=self.config.server_region,
                version=self.config.app_version,
                ip_address=self.config.server_ip,
                port=self.config.server_port,
                capabilities={
                    "supported_languages": ["en-US"],  # Default supported language
                    "max_concurrent_sessions": 100,    # Default max sessions
                    "supported_models": ["whisper-1"], # Default models
                    "features": [
                        "usage_tracking",
                        "session_management", 
                        "quota_refresh",
                        "remote_commands",
                        "health_monitoring",
                    ],
                },
            )
            
            correlation_id = str(uuid.uuid4())
            await self.control_plane_client.register_server(
                registration_data, correlation_id
            )
            
            self._registered = True
            self.logger.info(
                "Server registered successfully",
                server_id=self.config.server_id,
                correlation_id=correlation_id,
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to register server",
                error=str(e),
                server_id=self.config.server_id,
            )
            # Don't fail startup on registration failure

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to ControlPlane."""
        while self._running:
            try:
                # Get current status
                health_status = await self.get_health_status()
                
                # Map health status to server status enum
                status_mapping = {
                    "healthy": "online",
                    "degraded": "degraded", 
                    "unhealthy": "offline"
                }
                server_status = status_mapping.get(health_status["status"], "offline")
                
                heartbeat_data = HeartbeatData(
                    status=server_status,
                    metrics={
                        "uptime_seconds": int(time.time() - self._start_time),
                        "redis_connected": 1 if health_status["redis_connected"] else 0,
                        "control_plane_connected": 1 if health_status["control_plane_connected"] else 0,
                    },
                )
                
                correlation_id = str(uuid.uuid4())
                await self.control_plane_client.send_heartbeat(
                    self.config.server_id, heartbeat_data, correlation_id
                )
                
                # Wait for next heartbeat
                await asyncio.sleep(self.config.heartbeat_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in heartbeat loop",
                    error=str(e),
                )
                await asyncio.sleep(5)  # Short delay on error

    async def _metrics_collection_loop(self) -> None:
        """Collect and update Prometheus metrics."""
        while self._running:
            try:
                await self._update_metrics()
                await asyncio.sleep(30)  # Update metrics every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in metrics collection",
                    error=str(e),
                )
                await asyncio.sleep(5)

    async def _update_metrics(self) -> None:
        """Update Prometheus metrics."""
        server_id = self.config.server_id
        
        # Update connection status metrics
        redis_connected = await self.redis_client.is_connected()
        redis_connection_status.labels(server_id=server_id).set(
            1 if redis_connected else 0
        )

        if self.config.control_plane_health_check_enabled:
            control_plane_health = await self.control_plane_client.health_check()
            cp_connected = control_plane_health.get("status") == "healthy"
            control_plane_connection_status.labels(server_id=server_id).set(
                1 if cp_connected else 0
            )
        
        # Update queue depth metrics
        if redis_connected:
            queue_lengths = await self.redis_client.get_all_queue_lengths()
            for queue_name, depth in queue_lengths.items():
                redis_queue_depth.labels(
                    server_id=server_id,
                    queue_name=queue_name
                ).set(depth)

    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        # Check Redis connection
        redis_health = await self.redis_client.health_check()
        redis_connected = redis_health.get("status") == "healthy"
        
        # Check ControlPlane connection only if enabled
        if self.config.control_plane_health_check_enabled:
            cp_health = await self.control_plane_client.health_check()
            cp_connected = cp_health.get("status") == "healthy"
        else:
            cp_health = {"status": "disabled", "message": "Health check disabled"}
            cp_connected = True  # Consider as healthy if disabled
        
        # Determine overall status
        if redis_connected and cp_connected:
            overall_status = "healthy"
        elif redis_connected or cp_connected:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "version": self.config.app_version,
            "uptime_seconds": int(time.time() - self._start_time),
            "redis_connected": redis_connected,
            "control_plane_connected": cp_connected,
            "server_registered": self._registered,
            "components": {
                "redis": redis_health,
                "control_plane": cp_health,
            },
        }

    async def get_metrics_data(self) -> Dict[str, Any]:
        """Get detailed metrics data."""
        queue_lengths = await self.redis_client.get_all_queue_lengths()
        
        return {
            "server_id": self.config.server_id,
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": int(time.time() - self._start_time),
            "queue_metrics": queue_lengths,
            "connection_status": {
                "redis": await self.redis_client.is_connected(),
                "control_plane": (await self.control_plane_client.health_check()).get("status") == "healthy",
            },
            "server_info": {
                "version": self.config.app_version,
                "region": self.config.server_region,
                "registered": self._registered,
            },
        }

    def get_prometheus_metrics(self) -> str:
        """Get Prometheus metrics in text format."""
        return generate_latest().decode('utf-8')

    # Metric recording methods
    def record_usage_record_processed(self, status: str = "success") -> None:
        """Record usage record processing."""
        usage_records_processed.labels(
            server_id=self.config.server_id,
            status=status
        ).inc()

    def record_session_event_processed(
        self, 
        event_type: str, 
        status: str = "success"
    ) -> None:
        """Record session event processing."""
        session_events_processed.labels(
            server_id=self.config.server_id,
            event_type=event_type,
            status=status
        ).inc()

    def record_quota_request_processed(self, status: str = "success") -> None:
        """Record quota request processing."""
        quota_requests_processed.labels(
            server_id=self.config.server_id,
            status=status
        ).inc()

    def record_control_plane_request(
        self, 
        endpoint: str, 
        status: str = "success"
    ) -> None:
        """Record ControlPlane API request."""
        control_plane_requests.labels(
            server_id=self.config.server_id,
            endpoint=endpoint,
            status=status
        ).inc()

    def time_operation(self, service: str, operation: str) -> Any:
        """Get a timer context manager for operation timing."""
        return request_duration.labels(
            server_id=self.config.server_id,
            service=service,
            operation=operation
        ).time()
