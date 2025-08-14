"""ControlPlane client service for DataPlane Agent.

This module handles all communication with the ControlPlane API.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from httpx import AsyncClient, HTTPStatusError, RequestError

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


class ControlPlaneClient:
    """HTTP client for ControlPlane API communication."""

    def __init__(self, config: ApplicationConfig) -> None:
        """Initialize ControlPlane client."""
        self.config = config
        self.logger = create_contextual_logger(__name__, service="control_plane_client")
        self._client: Optional[AsyncClient] = None
        self._jwt_keys_cache: Optional[Dict[str, Any]] = None
        self._jwt_keys_cached_at: Optional[datetime] = None

    async def start(self) -> None:
        """Start the HTTP client."""
        self._client = AsyncClient(
            base_url=self.config.control_plane_url,
            timeout=httpx.Timeout(self.config.control_plane_timeout),
            headers={
                "User-Agent": f"DataPlane-Agent/{self.config.app_version}",
                "Content-Type": "application/json",
                self.config.api_key_header: self.config.control_plane_api_key,
            },
        )
        self.logger.info(
            "ControlPlane client started",
            base_url=self.config.control_plane_url,
        )

    async def stop(self) -> None:
        """Stop the HTTP client."""
        if self._client:
            await self._client.aclose()
            self.logger.info("ControlPlane client stopped")

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic."""
        if not self._client:
            raise RuntimeError("ControlPlane client not started")

        headers = {}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        for attempt in range(self.config.control_plane_retry_attempts):
            try:
                response = await self._client.request(
                    method=method,
                    url=endpoint,
                    json=data,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                
                self.logger.debug(
                    "ControlPlane request successful",
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                    attempt=attempt + 1,
                    correlation_id=correlation_id,
                )
                
                return response.json()

            except HTTPStatusError as e:
                self.logger.warning(
                    "ControlPlane request failed with HTTP error",
                    method=method,
                    endpoint=endpoint,
                    status_code=e.response.status_code,
                    error=str(e),
                    attempt=attempt + 1,
                    correlation_id=correlation_id,
                )
                
                # Don't retry on client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    raise
                
                if attempt == self.config.control_plane_retry_attempts - 1:
                    raise

            except RequestError as e:
                self.logger.warning(
                    "ControlPlane request failed with network error",
                    method=method,
                    endpoint=endpoint,
                    error=str(e),
                    attempt=attempt + 1,
                    correlation_id=correlation_id,
                )
                
                if attempt == self.config.control_plane_retry_attempts - 1:
                    raise

            # Exponential backoff
            if attempt < self.config.control_plane_retry_attempts - 1:
                delay = (self.config.control_plane_retry_backoff_factor ** attempt)
                await asyncio.sleep(delay)

        raise RuntimeError("All retry attempts failed")

    async def submit_usage_records(
        self,
        usage_records: List[EnrichedUsageRecord],
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit usage records to ControlPlane."""
        data = {
            "usage_records": [record.model_dump() for record in usage_records],
            "submission_timestamp": datetime.utcnow().isoformat(),
        }
        
        result = await self._make_request(
            method="POST",
            endpoint="/api/v1/usage-records",
            data=data,
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Usage records submitted",
            count=len(usage_records),
            correlation_id=correlation_id,
        )
        
        return result

    async def notify_session_start(
        self,
        session_event: SessionLifecycleEvent,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify ControlPlane of session start."""
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/sessions/{session_event.api_session_id}/start",
            data=session_event.model_dump(),
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Session start notification sent",
            session_id=session_event.api_session_id,
            customer_id=session_event.customer_id,
            correlation_id=correlation_id,
        )
        
        return result

    async def request_quota_refresh(
        self,
        quota_request: QuotaRefreshRequest,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request additional quota for active session."""
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/sessions/{quota_request.api_session_id}/refresh",
            data=quota_request.model_dump(),
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Quota refresh requested",
            session_id=quota_request.api_session_id,
            customer_id=quota_request.customer_id,
            requested_quota=quota_request.requested_quota,
            correlation_id=correlation_id,
        )
        
        return result

    async def notify_session_complete(
        self,
        session_event: SessionLifecycleEvent,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify ControlPlane of session completion."""
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/sessions/{session_event.api_session_id}/complete",
            data=session_event.model_dump(),
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Session completion notification sent",
            session_id=session_event.api_session_id,
            customer_id=session_event.customer_id,
            correlation_id=correlation_id,
        )
        
        return result

    async def register_server(
        self,
        registration_data: ServerRegistration,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register server with ControlPlane."""
        result = await self._make_request(
            method="POST",
            endpoint="/api/v1/servers/register",
            data=registration_data.model_dump(),
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Server registered",
            server_id=registration_data.server_id,
            region=registration_data.region,
            correlation_id=correlation_id,
        )
        
        return result

    async def send_heartbeat(
        self,
        heartbeat_data: HeartbeatData,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send heartbeat to ControlPlane."""
        result = await self._make_request(
            method="PUT",
            endpoint=f"/api/v1/servers/{heartbeat_data.server_id}/heartbeat",
            data=heartbeat_data.model_dump(),
            correlation_id=correlation_id,
        )
        
        self.logger.debug(
            "Heartbeat sent",
            server_id=heartbeat_data.server_id,
            correlation_id=correlation_id,
        )
        
        return result

    async def poll_commands(
        self,
        server_id: str,
        correlation_id: Optional[str] = None,
    ) -> List[RemoteCommand]:
        """Poll for pending commands."""
        result = await self._make_request(
            method="GET",
            endpoint=f"/api/v1/servers/{server_id}/commands",
            correlation_id=correlation_id,
        )
        
        commands = [RemoteCommand(**cmd) for cmd in result.get("commands", [])]
        
        if commands:
            self.logger.info(
                "Commands received",
                server_id=server_id,
                command_count=len(commands),
                correlation_id=correlation_id,
            )
        
        return commands

    async def report_command_result(
        self,
        server_id: str,
        command_result: CommandResult,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Report command execution result."""
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/servers/{server_id}/command-results",
            data=command_result.model_dump(),
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Command result reported",
            server_id=server_id,
            command_id=command_result.command_id,
            success=command_result.success,
            correlation_id=correlation_id,
        )
        
        return result

    async def fetch_jwt_public_keys(
        self,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch JWT public keys from ControlPlane."""
        # Check cache first
        if (
            self._jwt_keys_cache
            and self._jwt_keys_cached_at
            and (datetime.utcnow() - self._jwt_keys_cached_at).total_seconds()
            < self.config.jwt_public_keys_cache_ttl
        ):
            return self._jwt_keys_cache

        result = await self._make_request(
            method="GET",
            endpoint="/api/v1/auth/public-keys",
            correlation_id=correlation_id,
        )
        
        # Update cache
        self._jwt_keys_cache = result
        self._jwt_keys_cached_at = datetime.utcnow()
        
        self.logger.info(
            "JWT public keys fetched",
            keys_count=len(result.get("keys", [])),
            correlation_id=correlation_id,
        )
        
        return result

    async def health_check(self) -> Dict[str, Any]:
        """Perform ControlPlane health check."""
        try:
            if not self._client:
                return {
                    "status": "unhealthy",
                    "error": "Client not started"
                }
            
            # Test basic connectivity
            result = await self._make_request("GET", "/api/v1/health")
            return {
                "status": "healthy",
                "response": result,
                "base_url": self.config.control_plane_url,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "base_url": self.config.control_plane_url,
            }
