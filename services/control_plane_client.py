"""ControlPlane client service for DataPlane Agent.

This module handles all communication with the ControlPlane API.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

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
from utils import create_contextual_logger, get_connection_state_manager, log_exception


class ControlPlaneClient:
    """HTTP client for ControlPlane API communication."""

    def __init__(self, config: ApplicationConfig) -> None:
        """Initialize ControlPlane client."""
        self.config = config
        self.logger = create_contextual_logger(__name__, service="control_plane_client")
        self._jwt_keys_cache: Optional[Dict[str, Any]] = None
        self._jwt_keys_cached_at: Optional[datetime] = None
        self.connection_state = get_connection_state_manager()

    async def start(self) -> None:
        """Configure the ControlPlane client."""
        self.logger.info("ControlPlane client configured to use 'requests' library.")

    async def stop(self) -> None:
        """Stop the ControlPlane client."""
        self.logger.info("ControlPlane client stopped")

    def _execute_sync_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> requests.Response:
        """Execute a synchronous HTTP request using the 'requests' library with retries disabled."""
        full_url = self.config.control_plane_url + endpoint
        
        with requests.Session() as session:
            adapter = HTTPAdapter(max_retries=0)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            session.headers.update(headers)
            response = session.request(
                method=method.upper(),
                url=full_url,
                json=data,
                params=params,
                timeout=self.config.control_plane_timeout,
            )
            response.raise_for_status()
            return response

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request with circuit breaker and retry logic, using 'requests' in a thread."""
        if not await self.connection_state.should_attempt_request():
            self.logger.warning("Request blocked by circuit breaker", method=method, endpoint=endpoint)
            raise RuntimeError("Circuit breaker is open. Request blocked.")

        request_headers = {
            "User-Agent": f"DataPlane-Agent/{self.config.app_version}",
            "Content-Type": "application/json",
            self.config.api_key_header: self.config.control_plane_api_key,
        }
        if correlation_id:
            request_headers["X-Correlation-ID"] = correlation_id

        loop = asyncio.get_running_loop()

        for attempt in range(self.config.control_plane_retry_attempts):
            try:
                self.logger.info(f"HTTP request initiated: {method} {endpoint}", attempt=attempt + 1)
                
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,  # Use the default ThreadPoolExecutor
                        self._execute_sync_request,
                        method,
                        endpoint,
                        data,
                        params,
                        request_headers,
                    ),
                    timeout=self.config.control_plane_timeout + 5,
                )
                
                response_json = response.json()
                await self.connection_state.mark_success()
                self.logger.info(f"HTTP request completed: {method} {endpoint}", status_code=response.status_code, attempt=attempt + 1)
                return response_json

            except asyncio.TimeoutError:
                self.logger.warning("Request timed out in executor thread", attempt=attempt + 1)
                await self.connection_state.mark_failure()

            except requests.exceptions.RequestException as e:
                if e.response is not None and 400 <= e.response.status_code < 500:
                    self.logger.warning(f"HTTP client error", status_code=e.response.status_code, attempt=attempt + 1)
                    raise
                
                await self.connection_state.mark_failure()
                self.logger.warning(f"HTTP request failed in executor thread", error=str(e), attempt=attempt + 1)

            if attempt < self.config.control_plane_retry_attempts - 1:
                if not await self.connection_state.should_attempt_request():
                    self.logger.warning("Circuit breaker opened, aborting retries")
                    break
                
                delay = await self.connection_state.get_backoff_delay()
                self.logger.info(f"Retrying request after {delay:.2f} seconds", attempt=attempt + 1)
                await asyncio.sleep(delay)

        raise RuntimeError("All retry attempts failed or circuit breaker is open")

    async def submit_usage_record(
        self,
        usage_record: EnrichedUsageRecord,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a single usage record to ControlPlane for a specific session."""
        # Convert EnrichedUsageRecord to the format expected by ControlPlane API
        # Updated payload format to match API_Session_Management.md specification
        data = {
            "transaction_id": usage_record.transaction_id,
            "customer_id": usage_record.customer_id,
            "product_code": usage_record.product_code,
            "server_instance_id": usage_record.server_instance_id,
            "api_server_region": usage_record.api_server_region,
            "processing_timestamp": usage_record.processing_timestamp.isoformat(),
            "agent_version": usage_record.agent_version,
            "connection_duration_seconds": usage_record.connection_duration_seconds,
            "data_bytes_processed": usage_record.data_bytes_processed,
            "audio_duration_seconds": usage_record.audio_duration_seconds,
            "request_count": usage_record.request_count,
            "request_timestamp": usage_record.request_timestamp.isoformat(),
            "response_timestamp": usage_record.response_timestamp.isoformat(),
            # Note: credits_consumed is calculated server-side, not provided by client
        }
        
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/sessions/{usage_record.api_session_id}/usage-records",
            data=data,
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Usage record submitted",
            session_id=usage_record.api_session_id,
            transaction_id=usage_record.transaction_id,
            correlation_id=correlation_id,
        )
        
        return result

    async def submit_usage_records(
        self,
        usage_records: List[EnrichedUsageRecord],
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit multiple usage records to ControlPlane (batch processing)."""
        results = []
        for record in usage_records:
            try:
                result = await self.submit_usage_record(record, correlation_id)
                results.append(result)
            except Exception as e:
                self.logger.error(
                    "Failed to submit usage record",
                    session_id=record.api_session_id,
                    transaction_id=record.transaction_id,
                    error=str(e),
                    correlation_id=correlation_id,
                )
                # Continue with other records even if one fails
                continue
        
        self.logger.info(
            "Usage records batch submitted",
            total_count=len(usage_records),
            successful_count=len(results),
            correlation_id=correlation_id,
        )
        
        return {"submitted_count": len(results), "total_count": len(usage_records)}

    async def notify_session_start(
        self,
        session_event: SessionLifecycleEvent,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify ControlPlane of session start."""
        # Updated payload format to match API_Session_Management.md specification
        data = {
            "started_at": session_event.timestamp.isoformat(),
            "server_instance_id": self.config.server_id,
            "api_server_region": self.config.server_region,
            "agent_version": self.config.app_version,
            "timestamp": session_event.timestamp.isoformat(),
        }
        
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/sessions/{session_event.api_session_id}/started",
            data=data,
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
        # Updated payload format to match API_Session_Management.md specification
        session_refresh_data = {
            "transaction_id": quota_request.transaction_id,
            "customer_id": quota_request.customer_id,
            "product_code": quota_request.product_code.value,
            "timestamp": quota_request.timestamp.isoformat() if hasattr(quota_request.timestamp, 'isoformat') else str(quota_request.timestamp)
        }
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/sessions/{quota_request.api_session_id}/refresh",
            data=session_refresh_data,
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Quota refresh requested",
            session_id=quota_request.api_session_id,
            customer_id=quota_request.customer_id,
            correlation_id=correlation_id,
        )
        
        return result

    async def notify_session_complete(
        self,
        session_event: SessionLifecycleEvent,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify ControlPlane of session completion."""
        # Updated payload format to match API_Session_Management.md specification
        data = {
            "disconnect_reason": session_event.disconnect_reason,
            "completed_at": session_event.timestamp.isoformat(),
            "final_usage_summary": session_event.final_usage_summary or {},
            "server_instance_id": self.config.server_id,
            "api_server_region": self.config.server_region,
            "agent_version": self.config.app_version,
            "timestamp": session_event.timestamp.isoformat(),
        }
        
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/sessions/{session_event.api_session_id}/completed",
            data=data,
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
        server_id: str,
        heartbeat_data: HeartbeatData,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send heartbeat to ControlPlane."""
        # Use mode='json' to ensure proper datetime serialization
        data = heartbeat_data.model_dump(mode='json')
        
        result = await self._make_request(
            method="PUT",
            endpoint=f"/api/v1/servers/{server_id}/heartbeat",
            data=data,
            correlation_id=correlation_id,
        )
        
        self.logger.debug(
            "Heartbeat sent",
            server_id=server_id,
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
            data=command_result.model_dump(mode='json'),
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

    async def notify_server_shutdown(
        self,
        server_id: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify ControlPlane of graceful server shutdown."""
        data = {
            "shutdown_timestamp": datetime.utcnow().isoformat(),
            "reason": "graceful_shutdown",
        }
        
        result = await self._make_request(
            method="POST",
            endpoint=f"/api/v1/servers/{server_id}/shutdown",
            data=data,
            correlation_id=correlation_id,
        )
        
        self.logger.info(
            "Server shutdown notification sent",
            server_id=server_id,
            correlation_id=correlation_id,
        )
        
        return result

    async def health_check(self) -> Dict[str, Any]:
        """Perform ControlPlane health check using authenticated DataPlane endpoint."""
        try:
            if not self._client:
                return {
                    "status": "unhealthy",
                    "error": "Client not started",
                    "base_url": self.config.control_plane_url,
                }
            
            # Test basic connectivity using the authenticated DataPlane health endpoint
            result = await self._make_request("GET", "/health/dataplane")
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
