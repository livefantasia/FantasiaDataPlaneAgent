"""Unit tests for Redis client service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import RedisMessage
from services.redis_client import RedisClient


class TestRedisClient:
    """Test cases for RedisClient class."""

    @pytest.fixture
    def redis_client(self, mock_config) -> RedisClient:
        """Create a Redis client instance for testing."""
        return RedisClient(mock_config)

    @pytest.mark.asyncio
    async def test_connect_success(self, redis_client, mock_config) -> None:
        """Test successful Redis connection."""
        with patch("dataplane_agent.services.redis_client.redis") as mock_redis:
            mock_pool = AsyncMock()
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            
            mock_redis.ConnectionPool.return_value = mock_pool
            mock_redis.Redis.return_value = mock_client
            
            await redis_client.connect()
            
            assert redis_client._connected is True
            mock_redis.ConnectionPool.assert_called_once_with(
                host=mock_config.redis_host,
                port=mock_config.redis_port,
                password=mock_config.redis_password,
                db=mock_config.redis_db,
                socket_timeout=mock_config.redis_socket_timeout,
                retry_on_timeout=mock_config.redis_retry_on_timeout,
                max_connections=mock_config.redis_max_connections,
            )
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, redis_client) -> None:
        """Test Redis connection failure."""
        with patch("dataplane_agent.services.redis_client.redis") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=Exception("Connection failed"))
            mock_redis.Redis.return_value = mock_client
            
            with pytest.raises(Exception):
                await redis_client.connect()
            
            assert redis_client._connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, redis_client) -> None:
        """Test Redis disconnection."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        await redis_client.disconnect()
        
        mock_client.close.assert_called_once()
        assert redis_client._connected is False

    @pytest.mark.asyncio
    async def test_is_connected_true(self, redis_client) -> None:
        """Test is_connected returns True when connected."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        result = await redis_client.is_connected()
        
        assert result is True
        mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected_false_when_not_connected(self, redis_client) -> None:
        """Test is_connected returns False when not connected."""
        redis_client._client = None
        redis_client._connected = False
        
        result = await redis_client.is_connected()
        
        assert result is False

    @pytest.mark.asyncio
    async def test_is_connected_false_on_ping_failure(self, redis_client) -> None:
        """Test is_connected returns False when ping fails."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("Ping failed"))
        redis_client._client = mock_client
        redis_client._connected = True
        
        result = await redis_client.is_connected()
        
        assert result is False
        assert redis_client._connected is False

    @pytest.mark.asyncio
    async def test_push_message_with_dict(self, redis_client) -> None:
        """Test pushing a dictionary message."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        message = {"test": "data"}
        queue = "test_queue"
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            await redis_client.push_message(queue, message)
            
            expected_data = json.dumps(message, default=str)
            mock_client.lpush.assert_called_once_with(queue, expected_data)

    @pytest.mark.asyncio
    async def test_push_message_with_redis_message(self, redis_client) -> None:
        """Test pushing a RedisMessage object."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        message = RedisMessage(
            message_type="test",
            data={"test": "data"}
        )
        queue = "test_queue"
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            await redis_client.push_message(queue, message)
            
            expected_data = json.dumps(message.dict(), default=str)
            mock_client.lpush.assert_called_once_with(queue, expected_data)

    @pytest.mark.asyncio
    async def test_pop_message_blocking(self, redis_client) -> None:
        """Test blocking pop message."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        test_data = {"test": "data"}
        mock_client.brpop = AsyncMock(return_value=("queue", json.dumps(test_data)))
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            result = await redis_client.pop_message("test_queue", timeout=10)
            
            assert result == test_data
            mock_client.brpop.assert_called_once_with("test_queue", timeout=10)

    @pytest.mark.asyncio
    async def test_pop_message_non_blocking(self, redis_client) -> None:
        """Test non-blocking pop message."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        test_data = {"test": "data"}
        mock_client.rpop = AsyncMock(return_value=json.dumps(test_data))
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            result = await redis_client.pop_message("test_queue", timeout=0)
            
            assert result == test_data
            mock_client.rpop.assert_called_once_with("test_queue")

    @pytest.mark.asyncio
    async def test_pop_message_empty_queue(self, redis_client) -> None:
        """Test pop message from empty queue."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        mock_client.rpop = AsyncMock(return_value=None)
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            result = await redis_client.pop_message("test_queue", timeout=0)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_reliable_pop_message(self, redis_client) -> None:
        """Test reliable pop message using BRPOPLPUSH."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        test_data = {"test": "data"}
        serialized_data = json.dumps(test_data)
        
        mock_client.brpoplpush = AsyncMock(return_value=serialized_data)
        mock_client.get = AsyncMock(return_value=None)
        mock_client.incr = AsyncMock(return_value=1)
        mock_client.set = AsyncMock()
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            result = await redis_client.reliable_pop_message(
                "source_queue", "processing_queue", timeout=5
            )
            
            assert result is not None
            message_id, message_data = result
            assert message_data == test_data
            assert "source_queue:1" in message_id

    @pytest.mark.asyncio
    async def test_acknowledge_message(self, redis_client) -> None:
        """Test message acknowledgment."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            await redis_client.acknowledge_message("processing_queue", "test_data")
            
            mock_client.lrem.assert_called_once_with("processing_queue", 1, "test_data")

    @pytest.mark.asyncio
    async def test_move_to_dead_letter_queue(self, redis_client, mock_config) -> None:
        """Test moving message to dead letter queue."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        original_message = {"test": "data"}
        message_data = json.dumps(original_message)
        error_info = "Processing failed"
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            await redis_client.move_to_dead_letter_queue(
                "processing_queue", message_data, error_info
            )
            
            # Check that message was pushed to DLQ and removed from processing queue
            assert mock_client.lpush.called
            assert mock_client.lrem.called
            
            # Verify DLQ entry structure
            dlq_call_args = mock_client.lpush.call_args[0]
            assert dlq_call_args[0] == mock_config.dead_letter_queue
            
            dlq_entry = json.loads(dlq_call_args[1])
            assert dlq_entry["original_message"] == original_message
            assert dlq_entry["error_info"] == error_info

    @pytest.mark.asyncio
    async def test_get_queue_length(self, redis_client) -> None:
        """Test getting queue length."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        mock_client.llen = AsyncMock(return_value=5)
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            result = await redis_client.get_queue_length("test_queue")
            
            assert result == 5
            mock_client.llen.assert_called_once_with("test_queue")

    @pytest.mark.asyncio
    async def test_set_cache(self, redis_client) -> None:
        """Test setting cache value."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            await redis_client.set_cache("test_key", "test_value", ttl=60)
            
            mock_client.setex.assert_called_once_with("test_key", 60, "test_value")

    @pytest.mark.asyncio
    async def test_get_cache(self, redis_client) -> None:
        """Test getting cache value."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        mock_value = MagicMock()
        mock_value.decode.return_value = "test_value"
        mock_client.get = AsyncMock(return_value=mock_value)
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            result = await redis_client.get_cache("test_key")
            
            assert result == "test_value"
            mock_client.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_cache_not_found(self, redis_client) -> None:
        """Test getting cache value when key doesn't exist."""
        mock_client = AsyncMock()
        redis_client._client = mock_client
        redis_client._connected = True
        
        mock_client.get = AsyncMock(return_value=None)
        
        with patch.object(redis_client, "_ensure_connected", new_callable=AsyncMock):
            result = await redis_client.get_cache("test_key")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, redis_client, mock_config) -> None:
        """Test health check when Redis is healthy."""
        with patch.object(redis_client, "is_connected", return_value=True), \
             patch.object(redis_client, "set_cache") as mock_set, \
             patch.object(redis_client, "get_cache", return_value="test_value") as mock_get, \
             patch.object(redis_client, "delete_cache") as mock_delete:
            
            result = await redis_client.health_check()
            
            assert result["status"] == "healthy"
            assert result["host"] == mock_config.redis_host
            assert result["port"] == mock_config.redis_port
            assert result["db"] == mock_config.redis_db
            
            mock_set.assert_called_once()
            mock_get.assert_called_once()
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self, redis_client) -> None:
        """Test health check when Redis is not connected."""
        with patch.object(redis_client, "is_connected", return_value=False):
            result = await redis_client.health_check()
            
            assert result["status"] == "unhealthy"
            assert "Not connected to Redis" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_cache_operations_fail(self, redis_client) -> None:
        """Test health check when cache operations fail."""
        with patch.object(redis_client, "is_connected", return_value=True), \
             patch.object(redis_client, "set_cache") as mock_set, \
             patch.object(redis_client, "get_cache", return_value="wrong_value") as mock_get, \
             patch.object(redis_client, "delete_cache") as mock_delete:
            
            result = await redis_client.health_check()
            
            assert result["status"] == "unhealthy"
            assert "Cache operations failed" in result["error"]
