"""Metrics router for DataPlane Agent."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response

from services import HealthMetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])
logger = logging.getLogger(__name__)


def get_health_service(request: Request) -> HealthMetricsService:
    """Dependency to get health service from application state."""
    return request.app.state.health_metrics  # type: ignore[no-any-return]


@router.get("/", response_class=Response)
async def prometheus_metrics(
    health_service: HealthMetricsService = Depends(get_health_service),
) -> Response:
    """Get Prometheus metrics in text format."""
    try:
        metrics_text = health_service.get_prometheus_metrics()
        return Response(
            content=metrics_text,
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )
    except Exception as e:
        logger.error(
            "Failed to retrieve Prometheus metrics",
            error=str(e),
            endpoint="/metrics/",
        )
        # Return empty metrics with error comment
        error_metrics = f"# ERROR: Failed to retrieve metrics - {str(e)}\n"
        return Response(
            content=error_metrics,
            media_type="text/plain; version=0.0.4; charset=utf-8",
            status_code=503
        )


@router.get("/json", response_model=Dict[str, Any])
async def json_metrics(
    health_service: HealthMetricsService = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get metrics in JSON format."""
    try:
        return await health_service.get_metrics_data()
    except Exception as e:
        logger.error(
            "Failed to retrieve JSON metrics",
            error=str(e),
            endpoint="/metrics/json",
        )
        # Return error information in JSON format
        return {
            "error": "Failed to retrieve metrics data",
            "details": str(e),
            "status": "service_unavailable"
        }
