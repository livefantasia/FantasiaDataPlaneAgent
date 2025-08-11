"""Health check router for DataPlane Agent."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from services import HealthMetricsService

router = APIRouter(prefix="/health", tags=["health"])


def get_health_service(request: Request) -> HealthMetricsService:
    """Dependency to get health service from application state."""
    return request.app.state.health_metrics


@router.get("/", response_model=Dict[str, Any])
async def health_check(
    health_service: HealthMetricsService = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get application health status."""
    return await health_service.get_health_status()


@router.get("/detailed", response_model=Dict[str, Any])
async def detailed_health_check(
    health_service: HealthMetricsService = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get detailed health status with component information."""
    health_status = await health_service.get_health_status()
    metrics_data = await health_service.get_metrics_data()

    return {
        **health_status,
        "metrics": metrics_data,
    }
