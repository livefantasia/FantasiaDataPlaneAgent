"""Redis client service for DataPlane Agent.

This module provides Redis connectivity and queue operations.
"""

import asyncio
import json
from typing import Any, Awaitable, Dict, List, Optional, Tuple, Union, cast

import redis.asyncio as redis
from redis.exceptions import ConnectionError, RedisError

from config import ApplicationConfig
from models import RedisMessage
from utils import create_contextual_logger, log_exception


class RedisClient:
    """Async Redis client with connection management and queue operations."""

    def __init__(self, config: ApplicationConfig) -> None:
        """Initialize Redis client."""
        self.config = config
        self.logger = create_contextual_logger(__name__, service="redis_client")
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self._pool = redis.ConnectionPool(
                host=self.config.redis_host,
                port=self.config.redis_port,
                password=self.config.redis_password,
                db=self.config.redis_db,
                socket_timeout=self.config.redis_socket_timeout,
                retry_on_timeout=self.config.redis_retry_on_timeout,
                max_connections=self.config.redis_max_connections,
            )
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._client.ping()
            self._connected = True
            
            self.logger.info(
                "Redis connection established successfully",
                serviceName="RedisClient",
                operationName="connect",
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                success=True,
            )
        except Exception as e:
            log_exception(
                self.logger,
                e,
                "Redis connection failed: RedisClient.connect",
                serviceName="RedisClient",
                operationName="connect",
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
            )
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._connected = False
            self.logger.info("Disconnected from Redis")

    async def is_connected(self) -> bool:
        """Check Redis connection status."""
        if not self._client or not self._connected:
            return False
        
        try:
            await self._client.ping()
            return True
        except Exception:
            self._connected = False
            return False

    async def _ensure_connected(self) -> None:
        """Ensure Redis connection is established."""
        if not await self.is_connected():
            await self.connect()

    async def push_message(
        self, 
        queue: str, 
        message: Union[Dict[str, Any], RedisMessage],
        correlation_id: Optional[str] = None
    ) -> None:
        """Push message to Redis queue."""
        await self._ensure_connected()
        
        try:
            if isinstance(message, RedisMessage):
                data = message.model_dump()
            else:
                data = message
            
            serialized = json.dumps(data, default=str)
            
            if self._client:
                await cast(Awaitable[int], self._client.lpush(queue, serialized))
                
                self.logger.debug(
                    "Message pushed to queue",
                    queue=queue,
                    correlation_id=correlation_id,
                    message_size=len(serialized),
                )
        except Exception as e:
            log_exception(
                self.logger,
                e,
                "Failed to push message to queue",
                queue=queue,
                correlation_id=correlation_id,
                message_type=type(message).__name__,
            )
            raise

    async def pop_message(
        self, 
        queue: str, 
        timeout: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Pop message from Redis queue with optional timeout."""
        await self._ensure_connected()
        
        try:
            if self._client:
                if timeout > 0:
                    # Blocking pop with timeout
                    result = await cast(Awaitable[list], self._client.brpop([queue], timeout=timeout))
                    if result:
                        _, serialized = result
                        return json.loads(serialized)
                else:
                    # Non-blocking pop
                    serialized = await cast(Awaitable[Optional[str]], self._client.rpop(queue))
                    if serialized:
                        return json.loads(serialized)
            return None
        except Exception as e:
            self.logger.error(
                "Failed to pop message from queue",
                queue=queue,
                error=str(e),
            )
            raise

    async def reliable_pop_message(
        self,
        source_queue: str,
        processing_queue: str,
        timeout: int = 5
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Reliably pop message using BRPOPLPUSH pattern."""
        await self._ensure_connected()
        
        try:
            if self._client:
                result = await cast(Awaitable[str], self._client.brpoplpush(
                    source_queue, 
                    processing_queue, 
                    timeout=timeout
                ))

                if result:
                    message_id = await self._client.get(f"msg_id:{result}")
                    if not message_id:
                        # Generate message ID if not exists
                        message_id = f"{source_queue}:{await self._client.incr('msg_counter')}"
                        await self._client.set(f"msg_id:{result}", message_id)
                    
                    return str(message_id), json.loads(result)
            return None
        except Exception as e:
            self.logger.error(
                "Failed to reliably pop message",
                source_queue=source_queue,
                processing_queue=processing_queue,
                error=str(e),
            )
            raise

    async def acknowledge_message(
        self,
        processing_queue: str,
        message_data: str
    ) -> None:
        """Acknowledge message processing by removing from processing queue."""
        await self._ensure_connected()
        
        try:
            if self._client:
                await cast(Awaitable[int], self._client.lrem(processing_queue, 1, message_data))

                self.logger.debug(
                    "Message acknowledged",
                    processing_queue=processing_queue,
                )
        except Exception as e:
            self.logger.error(
                "Failed to acknowledge message",
                processing_queue=processing_queue,
                error=str(e),
            )
            raise

    async def move_to_dead_letter_queue(
        self,
        processing_queue: str,
        message_data: str,
        error_info: Optional[str] = None
    ) -> None:
        """Move failed message to dead letter queue."""
        await self._ensure_connected()
        
        try:
            if self._client:
                # Create DLQ entry with error info
                dlq_entry = {
                    "original_message": json.loads(message_data),
                    "error_info": error_info,
                    "failed_at": json.dumps(asyncio.get_event_loop().time(), default=str),
                    "processing_queue": processing_queue,
                }
                
                # Push to DLQ and remove from processing queue
                await cast(Awaitable[int], self._client.lpush(
                    self.config.dead_letter_queue,
                    json.dumps(dlq_entry, default=str)
                ))
                await cast(Awaitable[int], self._client.lrem(processing_queue, 1, message_data))
                
                self.logger.warning(
                    "Message moved to dead letter queue",
                    processing_queue=processing_queue,
                    error_info=error_info,
                )
        except Exception as e:
            self.logger.error(
                "Failed to move message to DLQ",
                processing_queue=processing_queue,
                error=str(e),
            )
            raise

    async def get_queue_length(self, queue: str) -> int:
        """Get the length of a queue."""
        await self._ensure_connected()
        
        try:
            if self._client:
                return await cast(Awaitable[int], self._client.llen(queue))
            return 0
        except Exception as e:
            self.logger.error(
                "Failed to get queue length",
                queue=queue,
                error=str(e),
            )
            return 0

    async def get_all_queue_lengths(self) -> Dict[str, int]:
        """Get lengths of all configured queues."""
        queues = [
            self.config.usage_records_queue,
            self.config.session_lifecycle_queue,
            self.config.quota_refresh_queue,
            self.config.dead_letter_queue,
        ]
        
        lengths = {}
        for queue in queues:
            lengths[queue] = await self.get_queue_length(queue)
        
        return lengths

    async def set_cache(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None
    ) -> None:
        """Set value in Redis cache."""
        await self._ensure_connected()
        
        try:
            if self._client:
                if ttl:
                    await self._client.setex(key, ttl, value)
                else:
                    await self._client.set(key, value)
        except Exception as e:
            self.logger.error(
                "Failed to set cache value",
                key=key,
                error=str(e),
            )
            raise

    async def get_cache(self, key: str) -> Optional[str]:
        """Get value from Redis cache."""
        await self._ensure_connected()
        
        try:
            if self._client:
                value = await self._client.get(key)
                return value.decode() if value else None
            return None
        except Exception as e:
            self.logger.error(
                "Failed to get cache value",
                key=key,
                error=str(e),
            )
            return None

    async def delete_cache(self, key: str) -> None:
        """Delete value from Redis cache."""
        await self._ensure_connected()
        
        try:
            if self._client:
                await self._client.delete(key)
        except Exception as e:
            self.logger.error(
                "Failed to delete cache value",
                key=key,
                error=str(e),
            )
            raise

    async def health_check(self) -> Dict[str, Any]:
        """Perform Redis health check."""
        try:
            is_connected = await self.is_connected()
            if not is_connected:
                return {
                    "status": "unhealthy",
                    "error": "Not connected to Redis"
                }
            
            # Test basic operations
            test_key = "health_check_test"
            await self.set_cache(test_key, "test_value", ttl=5)
            value = await self.get_cache(test_key)
            await self.delete_cache(test_key)
            
            if value == "test_value":
                return {
                    "status": "healthy",
                    "host": self.config.redis_host,
                    "port": self.config.redis_port,
                    "db": self.config.redis_db,
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": "Cache operations failed"
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
