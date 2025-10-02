"""ControlPlane client service for DataPlane Agent.

This module handles all communication with the ControlPlane API.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from config import ApplicationConfig
from models import (
    CommandResult,
    EnrichedUsageRecord,
    HeartbeatData,
    RemoteCommand,
    ServerRegistration,
    SessionLifecycleEvent,
    QuotaRefreshRequest,
)
from utils import create_contextual_logger, log_exception


class ControlPlaneClient:
    """Hybrid client for ControlPlane API, supporting both sync and async callers."""

    def __init__(self, config: ApplicationConfig) -> None:
        self.config = config
        self.logger = create_contextual_logger(__name__, service="control_plane_client")
        self.loop = asyncio.get_running_loop()

    def _execute_sync_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> requests.Response:
        """Executes a synchronous HTTP request. This is the thread-safe core."""
        full_url = self.config.control_plane_url + endpoint
        headers = {
            "User-Agent": f"DataPlane-Agent/{self.config.app_version}",
            "Content-Type": "application/json",
            self.config.api_key_header: self.config.control_plane_api_key,
            "Connection": "close",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        # A new session is created for each request to ensure thread safety and resource cleanup.
        with requests.Session() as session:
            response = session.request(
                method=method.upper(),
                url=full_url,
                json=data,
                params=params,
                timeout=self.config.control_plane_timeout,
                headers=headers,
            )
            response.raise_for_status()
            return response

    async def _make_async_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Async wrapper that calls the sync request method in a thread."""
        try:
            response = await self.loop.run_in_executor(
                None,  # Use default ThreadPoolExecutor
                self._execute_sync_request,
                method, endpoint, data, params, correlation_id
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Async request failed: {e}")
            raise

    # --- Synchronous methods for threaded workers ---
    def register_server_sync(self, registration_data: ServerRegistration, correlation_id: Optional[str] = None) -> None:
        self._execute_sync_request("POST", "/api/v1/servers/register", data=registration_data.model_dump(), correlation_id=correlation_id)

    def send_heartbeat_sync(self, server_id: str, heartbeat_data: HeartbeatData, correlation_id: Optional[str] = None) -> None:
        self._execute_sync_request("PUT", f"/api/v1/servers/{server_id}/heartbeat", data=heartbeat_data.model_dump(mode='json'), correlation_id=correlation_id)

    def poll_commands_sync(self, server_id: str, correlation_id: Optional[str] = None) -> List[RemoteCommand]:
        response_json = self._execute_sync_request("GET", f"/api/v1/servers/{server_id}/commands", correlation_id=correlation_id).json()
        return [RemoteCommand(**cmd) for cmd in response_json.get("commands", [])]

    def report_command_result_sync(self, server_id: str, command_result: CommandResult, correlation_id: Optional[str] = None) -> None:
        self._execute_sync_request("POST", f"/api/v1/servers/{server_id}/command-results", data=command_result.model_dump(mode='json'), correlation_id=correlation_id)

    # --- Asynchronous methods for asyncio services (e.g., RedisConsumerService) ---
    async def submit_usage_record(self, usage_record: EnrichedUsageRecord, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        data = usage_record.model_dump(mode='json')
        return await self._make_async_request("POST", f"/api/v1/sessions/{usage_record.api_session_id}/usage-records", data=data, correlation_id=correlation_id)