"""Command processor service for DataPlane Agent.

This service handles polling and executing remote commands from ControlPlane.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import ApplicationConfig
from models import CommandResult, CommandType, RemoteCommand
from utils import create_contextual_logger
from .control_plane_client import ControlPlaneClient
from .redis_client import RedisClient


class CommandProcessor:
    """Service for processing remote commands from ControlPlane."""

    def __init__(
        self,
        config: ApplicationConfig,
        redis_client: RedisClient,
        control_plane_client: ControlPlaneClient,
    ) -> None:
        """Initialize command processor."""
        self.config = config
        self.redis_client = redis_client
        self.control_plane_client = control_plane_client
        self.logger = create_contextual_logger(__name__, service="command_processor")
        
        self._running = False
        self._polling_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start command polling."""
        if self._running:
            return

        self._running = True
        self._polling_task = asyncio.create_task(self._poll_commands())
        
        self.logger.info(
            "Command processor started",
            poll_interval=self.config.command_poll_interval,
        )

    async def stop(self) -> None:
        """Stop command polling."""
        if not self._running:
            return

        self._running = False
        
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Command processor stopped")

    async def _poll_commands(self) -> None:
        """Poll for commands from ControlPlane."""
        while self._running:
            try:
                correlation_id = str(uuid.uuid4())
                
                # Poll for commands
                commands = await self.control_plane_client.poll_commands(
                    self.config.server_id, correlation_id
                )
                
                # Process each command
                for command in commands:
                    await self._process_command(command, correlation_id)
                
                # Wait before next poll
                await asyncio.sleep(self.config.command_poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in command polling",
                    error=str(e),
                )
                await asyncio.sleep(5)  # Short delay on error

    async def _process_command(
        self, 
        command: RemoteCommand, 
        correlation_id: str
    ) -> None:
        """Process a single remote command."""
        # Check if command was already executed
        cache_key = f"executed_commands:{command.command_id}"
        if await self.redis_client.get_cache(cache_key):
            self.logger.info(
                "Command already executed, skipping",
                command_id=command.command_id,
                command_type=command.command_type,
                correlation_id=correlation_id,
            )
            return

        self.logger.info(
            "Processing command",
            command_id=command.command_id,
            command_type=command.command_type,
            correlation_id=correlation_id,
        )

        try:
            # Execute command based on type
            result_data = await self._execute_command(command)
            
            # Create successful result
            command_result = CommandResult(
                command_id=command.command_id,
                success=True,
                result=result_data,
            )
            
            # Cache successful execution
            await self.redis_client.set_cache(
                cache_key, 
                "executed", 
                ttl=self.config.command_cache_ttl
            )
            
        except Exception as e:
            self.logger.error(
                "Command execution failed",
                command_id=command.command_id,
                command_type=command.command_type,
                error=str(e),
                correlation_id=correlation_id,
            )
            
            # Create failure result
            command_result = CommandResult(
                command_id=command.command_id,
                success=False,
                error_message=str(e),
            )

        # Report result to ControlPlane
        try:
            await self.control_plane_client.report_command_result(
                self.config.server_id, command_result, correlation_id
            )
        except Exception as e:
            self.logger.error(
                "Failed to report command result",
                command_id=command.command_id,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _execute_command(self, command: RemoteCommand) -> Dict[str, Any]:
        """Execute a specific command and return result data."""
        if command.command_type == CommandType.REFRESH_PUBLIC_KEYS:
            return await self._execute_refresh_public_keys(command)
        elif command.command_type == CommandType.HEALTH_CHECK:
            return await self._execute_health_check(command)
        elif command.command_type == CommandType.GET_METRICS:
            return await self._execute_get_metrics(command)
        else:
            raise ValueError(f"Unknown command type: {command.command_type}")

    async def _execute_refresh_public_keys(
        self, 
        command: RemoteCommand
    ) -> Dict[str, Any]:
        """Execute refresh public keys command."""
        # Fetch fresh JWT public keys from ControlPlane
        keys_data = await self.control_plane_client.fetch_jwt_public_keys()
        
        self.logger.info(
            "JWT public keys refreshed",
            command_id=command.command_id,
            keys_count=len(keys_data.get("keys", [])),
        )
        
        return {
            "action": "refresh_public_keys",
            "keys_refreshed": len(keys_data.get("keys", [])),
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _execute_health_check(
        self, 
        command: RemoteCommand
    ) -> Dict[str, Any]:
        """Execute health check command."""
        # Perform comprehensive health check
        redis_health = await self.redis_client.health_check()
        control_plane_health = await self.control_plane_client.health_check()
        
        overall_status = "healthy"
        if (redis_health.get("status") != "healthy" or 
            control_plane_health.get("status") != "healthy"):
            overall_status = "unhealthy"
        
        health_data = {
            "overall_status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "redis": redis_health,
                "control_plane": control_plane_health,
            },
            "server_id": self.config.server_id,
            "version": self.config.app_version,
        }
        
        self.logger.info(
            "Health check executed",
            command_id=command.command_id,
            overall_status=overall_status,
        )
        
        return health_data

    async def _execute_get_metrics(
        self, 
        command: RemoteCommand
    ) -> Dict[str, Any]:
        """Execute get metrics command."""
        # Get queue lengths
        queue_lengths = await self.redis_client.get_all_queue_lengths()
        
        # Basic system metrics (in a real implementation, you'd use psutil or similar)
        metrics_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "server_id": self.config.server_id,
            "queue_metrics": queue_lengths,
            "system_metrics": {
                "uptime_seconds": 0,  # Would be calculated from start time
                "memory_usage_mb": 0,  # Would be from psutil
                "cpu_usage_percent": 0,  # Would be from psutil
            },
            "application_metrics": {
                "version": self.config.app_version,
                "total_processed_messages": 0,  # Would be tracked
                "failed_messages": 0,  # Would be tracked
            },
        }
        
        self.logger.info(
            "Metrics collected",
            command_id=command.command_id,
            queue_count=len(queue_lengths),
        )
        
        return metrics_data
