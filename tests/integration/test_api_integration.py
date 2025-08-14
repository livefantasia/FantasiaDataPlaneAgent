"""Integration tests for DataPlane Agent API endpoints."""

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from main import create_app


class TestAPIIntegration:
    """Integration tests for API endpoints."""

    @pytest.fixture
    async def app_with_mocked_services(self, mock_config: Any) -> AsyncGenerator[FastAPI, None]:
        """Create FastAPI app with mocked services."""
        app = create_app()
        
        # Mock the services that would be initialized in lifespan
        mock_health_service = AsyncMock()
        mock_health_service.get_health_status.return_value = {
            "status": "healthy",
            "timestamp": "2024-01-15T10:00:00Z",
            "version": "1.0.0",
            "uptime_seconds": 3600,
            "redis_connected": True,
            "control_plane_connected": True,
            "server_registered": True,
        }
        mock_health_service.get_metrics_data.return_value = {
            "server_id": "test-server-001",
            "timestamp": "2024-01-15T10:00:00Z",
            "uptime_seconds": 3600,
            "queue_metrics": {
                "queue:usage_records": 0,
                "queue:session_lifecycle": 0,
                "queue:quota_refresh": 0,
                "queue:dead_letter": 0,
            },
            "connection_status": {
                "redis": True,
                "control_plane": True,
            },
            "server_info": {
                "version": "1.0.0",
                "region": "test-region",
                "registered": True,
            },
        }
        mock_health_service.get_prometheus_metrics.return_value = (
            "# HELP usage_records_processed_total Total usage records processed\n"
            "# TYPE usage_records_processed_total counter\n"
            "usage_records_processed_total{server_id=\"test-server-001\",status=\"success\"} 42\n"
        )
        
        # Inject the mock service
        with patch("routers.health._health_service", mock_health_service), \
             patch("routers.metrics._health_service", mock_health_service):
            yield app

    @pytest.mark.asyncio
    async def test_health_endpoint(self, app_with_mocked_services: FastAPI) -> None:
        """Test the health check endpoint."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            response = await client.get("/health/")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert data["version"] == "1.0.0"
            assert data["uptime_seconds"] == 3600
            assert data["redis_connected"] is True
            assert data["control_plane_connected"] is True

    @pytest.mark.asyncio
    async def test_detailed_health_endpoint(self, app_with_mocked_services: FastAPI) -> None:
        """Test the detailed health check endpoint."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            response = await client.get("/health/detailed")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert "metrics" in data
            assert data["metrics"]["server_id"] == "test-server-001"
            assert "queue_metrics" in data["metrics"]
            assert "connection_status" in data["metrics"]

    @pytest.mark.asyncio
    async def test_prometheus_metrics_endpoint(self, app_with_mocked_services: FastAPI) -> None:
        """Test the Prometheus metrics endpoint."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            response = await client.get("/metrics/")
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
            
            content = response.text
            assert "usage_records_processed_total" in content
            assert "server_id=\"test-server-001\"" in content

    @pytest.mark.asyncio
    async def test_json_metrics_endpoint(self, app_with_mocked_services: FastAPI) -> None:
        """Test the JSON metrics endpoint."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            response = await client.get("/metrics/json")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["server_id"] == "test-server-001"
            assert "queue_metrics" in data
            assert "connection_status" in data
            assert data["connection_status"]["redis"] is True
            assert data["connection_status"]["control_plane"] is True

    @pytest.mark.asyncio
    async def test_unhealthy_status_response(self, app_with_mocked_services: FastAPI) -> None:
        """Test API response when services are unhealthy."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            # Patch the health service to return unhealthy status
            with patch("routers.health._health_service") as mock_service:
                mock_service.get_health_status.return_value = {
                    "status": "unhealthy",
                    "timestamp": "2024-01-15T10:00:00Z",
                    "version": "1.0.0",
                    "uptime_seconds": 3600,
                    "redis_connected": False,
                    "control_plane_connected": False,
                    "components": {
                        "redis": {"status": "unhealthy", "error": "Connection failed"},
                        "control_plane": {"status": "unhealthy", "error": "Timeout"},
                    },
                }
                
                response = await client.get("/health/")
                
                assert response.status_code == 200  # Health endpoint always returns 200
                data = response.json()
                
                assert data["status"] == "unhealthy"
                assert data["redis_connected"] is False
                assert data["control_plane_connected"] is False
                assert "components" in data

    @pytest.mark.asyncio
    async def test_cors_headers(self, app_with_mocked_services: FastAPI) -> None:
        """Test CORS headers are properly set."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            # Test preflight request
            response = await client.options(
                "/health/",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "GET",
                }
            )
            
            assert response.status_code == 200
            assert "access-control-allow-origin" in response.headers
            assert "access-control-allow-methods" in response.headers

    @pytest.mark.asyncio
    async def test_service_dependency_failure(self, app_with_mocked_services: FastAPI) -> None:
        """Test API behavior when service dependencies fail."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            # Patch the health service to raise an exception
            with patch("routers.health._health_service") as mock_service:
                mock_service.get_health_status.side_effect = Exception("Service unavailable")
                
                response = await client.get("/health/")
                
                # The endpoint should handle the exception gracefully
                # In a real implementation, you'd want proper error handling
                assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_api_documentation_available(self, app_with_mocked_services: FastAPI) -> None:
        """Test that API documentation is available."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            # Test OpenAPI schema
            response = await client.get("/openapi.json")
            assert response.status_code == 200
            
            schema = response.json()
            assert "openapi" in schema
            assert "info" in schema
            assert schema["info"]["title"] == "DataPlane Agent"
            
            # Test Swagger UI
            response = await client.get("/docs")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_metrics_content_type_consistency(self, app_with_mocked_services: FastAPI) -> None:
        """Test that metrics endpoints return consistent content types."""
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            # Prometheus metrics should be text/plain
            response = await client.get("/metrics/")
            assert "text/plain" in response.headers["content-type"]
            
            # JSON metrics should be application/json
            response = await client.get("/metrics/json")
            assert "application/json" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_endpoint_performance(self, app_with_mocked_services: FastAPI) -> None:
        """Test that endpoints respond within reasonable time limits."""
        import time
        
        async with AsyncClient(app=app_with_mocked_services, base_url="http://test") as client:
            # Test health endpoint performance
            start_time = time.time()
            response = await client.get("/health/")
            duration = time.time() - start_time
            
            assert response.status_code == 200
            assert duration < 1.0  # Should respond within 1 second
            
            # Test metrics endpoint performance
            start_time = time.time()
            response = await client.get("/metrics/")
            duration = time.time() - start_time
            
            assert response.status_code == 200
            assert duration < 1.0  # Should respond within 1 second
