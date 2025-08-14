"""Metrics router for DataPlane Agent."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response

from services import HealthMetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])


def get_health_service(request: Request) -> HealthMetricsService:
    """Dependency to get health service from application state."""
    return request.app.state.health_metrics  # type: ignore[no-any-return]


@router.get("/", response_class=Response)
async def prometheus_metrics(
    health_service: HealthMetricsService = Depends(get_health_service),
) -> Response:
    """Get Prometheus metrics in text format."""
    metrics_text = health_service.get_prometheus_metrics()
    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@router.get("/json", response_model=Dict[str, Any])
async def json_metrics(
    health_service: HealthMetricsService = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get metrics in JSON format."""
    return await health_service.get_metrics_data()
