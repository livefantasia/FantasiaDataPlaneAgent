"""Redis consumer service for DataPlane Agent.

This service handles consuming messages from Redis queues and processing them.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import ApplicationConfig
from models import (
    EnrichedUsageRecord,
    QuotaRefreshRequest,
    QuotaRefreshResponse,
    SessionLifecycleEvent,
    UsageRecord,
)
from models.enums import ProductCode, SessionEventType
from utils import create_contextual_logger
from .control_plane_client import ControlPlaneClient
from .redis_client import RedisClient


class RedisConsumerService:
    """Service for consuming and processing Redis queue messages."""

    def __init__(
        self,
        config: ApplicationConfig,
        redis_client: RedisClient,
        control_plane_client: ControlPlaneClient,
    ) -> None:
        """Initialize Redis consumer service."""
        self.config = config
        self.redis_client = redis_client
        self.control_plane_client = control_plane_client
        self.logger = create_contextual_logger(__name__, service="redis_consumer")
        
        self._running = False
        self._tasks: List[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Start consuming from Redis queues."""
        if self._running:
            return

        self._running = True
        
        # Recover any messages left in processing queues from previous shutdown
        source_queues = [
            self.config.usage_records_queue,
            self.config.session_lifecycle_queue,
            self.config.quota_refresh_queue,
        ]
        
        try:
            recovered_count = await self.redis_client.recover_processing_queues(source_queues)
            if recovered_count > 0:
                self.logger.info(
                    "Recovered messages from processing queues on startup",
                    recovered_messages=recovered_count
                )
        except Exception as e:
            self.logger.error(
                "Failed to recover processing queues on startup",
                error=str(e)
            )
        
        # Start consumer tasks
        self._tasks = [
            asyncio.create_task(self._consume_usage_records()),
            asyncio.create_task(self._consume_session_lifecycle()),
            asyncio.create_task(self._consume_quota_refresh()),
        ]
        
        self.logger.info("Redis consumer service started")

    async def stop(self) -> None:
        """Stop consuming from Redis queues."""
        if not self._running:
            return

        self._running = False
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self.logger.info("Redis consumer service stopped")

    async def _consume_usage_records(self) -> None:
        """Consume usage records from Redis queue."""
        queue = self.config.usage_records_queue
        processing_queue = f"{queue}:processing"
        
        self.logger.info(
            "Started consuming usage records",
            queue=queue,
            processing_queue=processing_queue,
        )
        
        while self._running:
            try:
                # Use reliable pop with processing queue
                result = await self.redis_client.reliable_pop_message(
                    queue, processing_queue, timeout=5
                )
                
                if result:
                    message_data = result
                    correlation_id = str(uuid.uuid4())
                    message_id = message_data.get("message_id", "unknown")
                    
                    try:
                        await self._process_usage_record(
                            message_data, correlation_id
                        )
                        
                        # Acknowledge successful processing
                        await self.redis_client.acknowledge_message(
                            processing_queue, json.dumps(message_data)
                        )
                        
                    except Exception as e:
                        self.logger.error(
                            "Failed to process usage record",
                            error=str(e),
                            message_id=message_id,
                            correlation_id=correlation_id,
                        )
                        
                        # Move to dead letter queue
                        await self.redis_client.move_to_dead_letter_queue(
                            processing_queue,
                            json.dumps(message_data),
                            error_info=str(e),
                        )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in usage records consumer",
                    error=str(e),
                    queue=queue,
                )
                await asyncio.sleep(1)

    async def _consume_session_lifecycle(self) -> None:
        """Consume session lifecycle events from Redis queue."""
        queue = self.config.session_lifecycle_queue
        processing_queue = f"{queue}:processing"
        
        self.logger.info(
            "Started consuming session lifecycle events",
            queue=queue,
            processing_queue=processing_queue,
        )
        
        while self._running:
            try:
                result = await self.redis_client.reliable_pop_message(
                    queue, processing_queue, timeout=5
                )
                
                if result:
                    message_data = result
                    correlation_id = str(uuid.uuid4())
                    message_id = message_data.get("message_id", "unknown")
                    
                    try:
                        await self._process_session_lifecycle_event(
                            message_data, correlation_id
                        )
                        
                        # Acknowledge successful processing
                        await self.redis_client.acknowledge_message(
                            processing_queue, json.dumps(message_data)
                        )
                        
                    except Exception as e:
                        self.logger.error(
                            "Failed to process session lifecycle event",
                            error=str(e),
                            message_id=message_id,
                            correlation_id=correlation_id,
                        )
                        
                        # Move to dead letter queue
                        await self.redis_client.move_to_dead_letter_queue(
                            processing_queue,
                            json.dumps(message_data),
                            error_info=str(e),
                        )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in session lifecycle consumer",
                    error=str(e),
                    queue=queue,
                )
                await asyncio.sleep(1)

    async def _consume_quota_refresh(self) -> None:
        """Consume quota refresh requests from Redis queue."""
        queue = self.config.quota_refresh_queue
        processing_queue = f"{queue}:processing"
        
        self.logger.info(
            "Started consuming quota refresh requests",
            queue=queue,
            processing_queue=processing_queue,
        )
        
        while self._running:
            try:
                result = await self.redis_client.reliable_pop_message(
                    queue, processing_queue, timeout=5
                )
                
                if result:
                    message_data = result
                    correlation_id = str(uuid.uuid4())
                    message_id = message_data.get("message_id", "unknown")
                    
                    try:
                        await self._process_quota_refresh_request(
                            message_data, correlation_id
                        )
                        
                        # Acknowledge successful processing
                        await self.redis_client.acknowledge_message(
                            processing_queue, json.dumps(message_data)
                        )
                        
                    except Exception as e:
                        self.logger.error(
                            "Failed to process quota refresh request",
                            error=str(e),
                            message_id=message_id,
                            correlation_id=correlation_id,
                        )
                        
                        # Move to dead letter queue
                        await self.redis_client.move_to_dead_letter_queue(
                            processing_queue,
                            json.dumps(message_data),
                            error_info=str(e),
                        )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Error in quota refresh consumer",
                    error=str(e),
                    queue=queue,
                )
                await asyncio.sleep(1)

    async def _process_usage_record(
        self, 
        message_data: Dict[str, Any], 
        correlation_id: str
    ) -> None:
        """Process a single usage record."""
        # Parse and validate usage record
        usage_record = UsageRecord(**message_data)
        
        # Enrich with server metadata
        enriched_record = EnrichedUsageRecord(
            **usage_record.model_dump(),
            server_instance_id=self.config.server_id,
            api_server_region=self.config.server_region,
            processing_timestamp=datetime.utcnow(),
            agent_version=self.config.app_version,
        )
        
        # Submit to ControlPlane and check if successful
        result = await self.control_plane_client.submit_usage_records(
            [enriched_record], correlation_id
        )
        
        # Only log success if the submission was actually successful
        if result.get("submitted_count", 0) > 0:
            self.logger.info(
                "Usage record processed successfully",
                session_id=usage_record.api_session_id,
                customer_id=usage_record.customer_id,
                correlation_id=correlation_id,
            )
        else:
            self.logger.error(
                "Usage record processing failed - submission to ControlPlane unsuccessful",
                session_id=usage_record.api_session_id,
                customer_id=usage_record.customer_id,
                submitted_count=result.get("submitted_count", 0),
                total_count=result.get("total_count", 1),
                correlation_id=correlation_id,
            )
            # Re-raise the exception to ensure the message is requeued or moved to DLQ
            raise RuntimeError(f"Failed to submit usage record for session {usage_record.api_session_id}")

    async def _process_session_lifecycle_event(
        self, 
        message_data: Dict[str, Any], 
        correlation_id: str
    ) -> None:
        """Process a session lifecycle event."""
        event = SessionLifecycleEvent(**message_data)
        result = None
        
        try:
            self.logger.info(
                "Sending session lifecycle event to ControlPlane",
                session_id=event.api_session_id,
                event_type=event.event_type,
                transaction_id=event.transaction_id,
                correlation_id=correlation_id,
            )
            
            if event.event_type == SessionEventType.START.value:
                result = await self.control_plane_client.notify_session_start(
                    event, correlation_id
                )
            elif event.event_type == SessionEventType.COMPLETE.value:
                result = await self.control_plane_client.notify_session_complete(
                    event, correlation_id
                )
            else:
                raise ValueError(f"Unknown event type: {event.event_type}")
            
            self.logger.info(
                "ControlPlane responded to session lifecycle event",
                session_id=event.api_session_id,
                event_type=event.event_type,
                transaction_id=event.transaction_id,
                response_summary=str(result)[:200] if result else "empty",
                correlation_id=correlation_id,
            )
        except Exception as e:
            self.logger.error(
                "Session lifecycle event processing failed",
                session_id=event.api_session_id,
                event_type=event.event_type,
                error=str(e),
                correlation_id=correlation_id,
            )
            # Re-raise the exception to ensure the message is requeued or moved to DLQ
            raise

    async def _process_quota_refresh_request(
        self, 
        message_data: Dict[str, Any], 
        correlation_id: str
    ) -> None:
        """Process a quota refresh request."""
        # Add a default product_code if it's missing for backward compatibility
        if 'product_code' not in message_data:
            message_data['product_code'] = ProductCode.SPEECH_TRANSCRIPTION.value

        quota_request = QuotaRefreshRequest(**message_data)
        
        try:
            # Submit quota refresh request to ControlPlane and get response
            response_data = await self.control_plane_client.request_quota_refresh(
                quota_request, correlation_id
            )
            
            self.logger.info(
                "Quota refresh request processed successfully",
                session_id=quota_request.api_session_id,
                customer_id=quota_request.customer_id,
                correlation_id=correlation_id,
            )
            
            # If we received a response, forward it back to the AudioAPIServer
            if response_data:
                try:
                    quota_response = QuotaRefreshResponse(**response_data)
                    
                    # Send response back to AudioAPIServer via quota_response_queue
                    await self.redis_client.push_message(
                        self.config.quota_response_queue,
                        quota_response.model_dump()
                    )
                    
                    self.logger.info(
                        "Quota refresh response forwarded to AudioAPIServer",
                        session_id=quota_response.api_session_id,
                        new_quota_amount=quota_response.new_quota_amount,
                        final_quota=quota_response.final_quota,
                        correlation_id=correlation_id,
                    )
                    
                except Exception as e:
                    self.logger.error(
                        "Failed to process quota refresh response",
                        error=str(e),
                        response_data=response_data,
                        correlation_id=correlation_id,
                    )
        
        except Exception as e:
            self.logger.error(
                "Quota refresh request processing failed",
                session_id=quota_request.api_session_id,
                customer_id=quota_request.customer_id,
                error=str(e),
                correlation_id=correlation_id,
            )
            # Re-raise the exception to ensure the message is requeued or moved to DLQ
            raise

    async def get_consumer_stats(self) -> Dict[str, Any]:
        """Get consumer statistics."""
        queue_lengths = await self.redis_client.get_all_queue_lengths()
        
        return {
            "running": self._running,
            "active_tasks": len([t for t in self._tasks if not t.done()]),
            "queue_lengths": queue_lengths,
            "total_tasks": len(self._tasks),
        }
