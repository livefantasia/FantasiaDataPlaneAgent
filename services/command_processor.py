"""Command processor service for DataPlane Agent.

This service handles polling and executing remote commands from ControlPlane.
"""

import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from config import ApplicationConfig
from models import CommandResult, CommandType, RemoteCommand
from utils import create_contextual_logger
from .control_plane_client import ControlPlaneClient
from .redis_client import RedisClient


class CommandProcessor:
    """Service for processing remote commands from ControlPlane, using a threaded worker model."""

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
        self.logger = create_contextual_logger(__name__, service="command_processor")
        self._shutdown_event = threading.Event()

    def start(self) -> None:
        """Start the command polling worker in the thread pool."""
        self.logger.info("Starting command processor worker...")
        self._shutdown_event.clear()
        self.executor.submit(self._poll_commands_worker)

    def stop(self) -> None:
        """Signal the command polling worker to stop."""
        self.logger.info("Stopping command processor worker...")
        self._shutdown_event.set()

    def _poll_commands_worker(self) -> None:
        """Synchronous worker to poll for and process commands."""
        self.logger.info("Command polling worker started.")
        while not self._shutdown_event.is_set():
            try:
                correlation_id = str(uuid.uuid4())
                commands = self.control_plane_client.poll_commands_sync(
                    self.config.server_id, correlation_id
                )
                for command in commands:
                    self._process_command_sync(command, correlation_id)
                
                # Use event.wait for an interruptible sleep
                self._shutdown_event.wait(timeout=self.config.command_poll_interval)

            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error in command polling worker: {e}")
                self._shutdown_event.wait(timeout=self.config.control_plane_initial_error_delay)
            except Exception as e:
                self.logger.error(f"Unhandled error in command polling worker: {e}", exc_info=True)
                self._shutdown_event.wait(timeout=self.config.control_plane_initial_error_delay)
        self.logger.info("Command polling worker stopped.")

    def _process_command_sync(self, command: RemoteCommand, correlation_id: str) -> None:
        """Process a single remote command synchronously."""
        cache_key = f"executed_commands:{command.command_id}"
        # Assuming redis_client has sync methods, which need to be created.
        # For now, we will proceed and assume they will be created.
        if self.redis_client.get_cache_sync(cache_key):
            self.logger.info("Command already executed, skipping.", command_id=command.command_id)
            return

        self.logger.info("Processing command", command_id=command.command_id)
        try:
            result_data = self._execute_command_sync(command)
            command_result = CommandResult(command_id=command.command_id, success=True, result=result_data)
            self.redis_client.set_cache_sync(cache_key, "executed", ttl=self.config.command_cache_ttl)
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}", command_id=command.command_id)
            command_result = CommandResult(command_id=command.command_id, success=False, error_message=str(e))

        # Reporting result is best-effort
        try:
            # This method needs to be created in ControlPlaneClient
            self.control_plane_client.report_command_result_sync(self.config.server_id, command_result, correlation_id)
        except Exception as e:
            self.logger.error(f"Failed to report command result: {e}", command_id=command.command_id)

    def _execute_command_sync(self, command: RemoteCommand) -> Dict[str, Any]:
        """Execute a specific command and return result data."""
        if command.command_type == CommandType.REFRESH_PUBLIC_KEYS:
            return self.control_plane_client.fetch_jwt_public_keys_sync()
        elif command.command_type == CommandType.HEALTH_CHECK:
            # Note: HealthMetricsService is not passed to CommandProcessor currently.
            # This would require a small refactor to inject it if this command is used.
            self.logger.warning("HEALTH_CHECK command is not fully implemented in sync mode.")
            return {"status": "not_implemented"}
        elif command.command_type == CommandType.GET_METRICS:
            self.logger.warning("GET_METRICS command is not fully implemented in sync mode.")
            return {"status": "not_implemented"}
        else:
            raise ValueError(f"Unknown command type: {command.command_type}")
