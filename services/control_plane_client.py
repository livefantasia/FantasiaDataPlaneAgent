"""ControlPlane client service for DataPlane Agent.

This module handles all communication with the ControlPlane API.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import namedtuple

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
from utils import create_contextual_logger

# Result object to pass between sync and async contexts
SyncRequestResult = namedtuple("SyncRequestResult", ["json_data", "error"])

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
    ) -> SyncRequestResult:
        """Executes a synchronous HTTP request and returns a result object."""
        try:
            full_url = self.config.control_plane_url + endpoint
            headers = {
                "User-Agent": f"DataPlane-Agent/{self.config.app_version}",
                "Content-Type": "application/json",
                self.config.api_key_header: self.config.control_plane_api_key,
                "Connection": "close",
            }
            if correlation_id:
                headers["X-Correlation-ID"] = correlation_id

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
                return SyncRequestResult(json_data=response.json(), error=None)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"SYNC HTTP request failed: {e}")
            return SyncRequestResult(json_data=None, error=str(e))

    async def _make_async_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Async wrapper that calls the sync request method and handles the result."""
        result = await self.loop.run_in_executor(
            None, self._execute_sync_request, method, endpoint, data, params, correlation_id
        )
        if result.error:
            raise Exception(result.error)
        return result.json_data

    # --- Synchronous methods for threaded workers ---
    def register_server_sync(self, registration_data: ServerRegistration, correlation_id: Optional[str] = None) -> None:
        result = self._execute_sync_request("POST", "/api/v1/servers/register", data=registration_data.model_dump(), correlation_id=correlation_id)
        if result.error:
            raise Exception(result.error)

    def send_heartbeat_sync(self, server_id: str, heartbeat_data: HeartbeatData, correlation_id: Optional[str] = None) -> None:
        result = self._execute_sync_request("PUT", f"/api/v1/servers/{server_id}/heartbeat", data=heartbeat_data.model_dump(mode='json'), correlation_id=correlation_id)
        if result.error:
            raise Exception(result.error)

    def poll_commands_sync(self, server_id: str, correlation_id: Optional[str] = None) -> List[RemoteCommand]:
        result = self._execute_sync_request("GET", f"/api/v1/servers/{server_id}/commands", correlation_id=correlation_id)
        if result.error:
            raise Exception(result.error)
        return [RemoteCommand(**cmd) for cmd in result.json_data.get("commands", [])]

    def report_command_result_sync(self, server_id: str, command_result: CommandResult, correlation_id: Optional[str] = None) -> None:
        result = self._execute_sync_request("POST", f"/api/v1/servers/{server_id}/command-results", data=command_result.model_dump(mode='json'), correlation_id=correlation_id)
        if result.error:
            raise Exception(result.error)

    # --- Asynchronous methods for asyncio services (e.g., RedisConsumerService) ---
    async def submit_usage_record(self, usage_record: EnrichedUsageRecord, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        return await self._make_async_request("POST", f"/api/v1/sessions/{usage_record.api_session_id}/usage-records", data=usage_record.model_dump(mode='json'), correlation_id=correlation_id)

    async def submit_usage_records(self, records: List[EnrichedUsageRecord], correlation_id: Optional[str] = None) -> Dict[str, Any]:
        # This is not a true batch endpoint, so we send one by one.
        results = []
        for record in records:
            try:
                result = await self.submit_usage_record(record, correlation_id)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to submit one usage record in batch: {e}", session_id=record.api_session_id)
        return {"submitted_count": len(results), "total_count": len(records)}

    async def notify_session_start(self, session_event: SessionLifecycleEvent, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        return await self._make_async_request("POST", f"/api/v1/sessions/{session_event.api_session_id}/started", data=session_event.model_dump(mode='json'), correlation_id=correlation_id)

    async def notify_session_complete(self, session_event: SessionLifecycleEvent, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        return await self._make_async_request("POST", f"/api/v1/sessions/{session_event.api_session_id}/completed", data=session_event.model_dump(mode='json'), correlation_id=correlation_id)

    async def request_quota_refresh(self, quota_request: QuotaRefreshRequest, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        return await self._make_async_request("POST", f"/api/v1/sessions/{quota_request.api_session_id}/refresh", data=quota_request.model_dump(mode='json'), correlation_id=correlation_id)

    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Alias for _make_async_request for backward compatibility."""
        return await self._make_async_request(method, endpoint, data, params, correlation_id)

    async def register_server(self, registration_data: ServerRegistration, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Async version of register_server_sync."""
        return await self._make_async_request("POST", "/api/v1/servers/register", data=registration_data.model_dump(), correlation_id=correlation_id)

    async def send_heartbeat(self, server_id: str, heartbeat_data: HeartbeatData, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Async version of send_heartbeat_sync."""
        return await self._make_async_request("PUT", f"/api/v1/servers/{server_id}/heartbeat", data=heartbeat_data.model_dump(mode='json'), correlation_id=correlation_id)

    async def poll_commands(self, server_id: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Async version of poll_commands_sync."""
        result = await self._make_async_request("GET", f"/api/v1/servers/{server_id}/commands", correlation_id=correlation_id)
        return {"commands": [RemoteCommand(**cmd) for cmd in result.get("commands", [])]}

    async def report_command_result(self, server_id: str, command_result: CommandResult, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Async version of report_command_result_sync."""
        return await self._make_async_request("POST", f"/api/v1/servers/{server_id}/command-results", data=command_result.model_dump(mode='json'), correlation_id=correlation_id)

    async def fetch_jwt_public_keys(self, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch JWT public keys from the control plane."""
        return await self._make_async_request("GET", "/api/v1/auth/public-keys", correlation_id=correlation_id)

    async def health_check(self, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Perform health check against the control plane."""
        return await self._make_async_request("GET", "/api/v1/health", correlation_id=correlation_id)

    async def notify_server_shutdown(self, server_id: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Notify the control plane that the server is shutting down."""
        return await self._make_async_request("POST", f"/api/v1/servers/{server_id}/shutdown", correlation_id=correlation_id)
