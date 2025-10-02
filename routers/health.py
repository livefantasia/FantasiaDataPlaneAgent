"""Health check router for DataPlane Agent."""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from services import HealthMetricsService

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


def get_health_service(request: Request) -> HealthMetricsService:
    """Dependency to get health service from application state."""
    return request.app.state.health_metrics  # type: ignore[no-any-return]


@router.get("/", response_model=Dict[str, Any])
async def health_check(
    health_service: HealthMetricsService = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get application health status."""
    try:
        return await health_service.get_health_status()
    except Exception as e:
        logger.error(
            "Health check failed",
            error=str(e),
            endpoint="/health/",
        )
        # Return a degraded health status instead of failing completely
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "unknown",
            "uptime_seconds": 0,
            "redis_connected": False,
            "control_plane_connected": False,
            "components": {
                "health_service": {"status": "unhealthy", "error": str(e)}
            },
        }


@router.get("/detailed", response_model=Dict[str, Any])
async def detailed_health_check(
    health_service: HealthMetricsService = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get detailed health status with component information."""
    try:
        health_status = await health_service.get_health_status()
        metrics_data = await health_service.get_metrics_data()

        return {
            **health_status,
            "metrics": metrics_data,
        }
    except Exception as e:
        logger.error(
            "Detailed health check failed",
            error=str(e),
            endpoint="/health/detailed",
        )
        # Return a degraded health status instead of failing completely
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "unknown",
            "uptime_seconds": 0,
            "redis_connected": False,
            "control_plane_connected": False,
            "components": {
                "health_service": {"status": "unhealthy", "error": str(e)}
            },
            "metrics": {
                "error": "Failed to retrieve metrics data",
                "details": str(e)
            },
        }
