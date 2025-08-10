"""Metrics router for DataPlane Agent."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Response

router = APIRouter(prefix="/metrics", tags=["metrics"])

# Global reference to health service (injected by main app)
_health_service = None


def set_health_service(service: Any) -> None:
    """Set the health service instance."""
    global _health_service
    _health_service = service


def get_health_service() -> Any:
    """Dependency to get health service."""
    if _health_service is None:
        raise RuntimeError("Health service not initialized")
    return _health_service


@router.get("/", response_class=Response)
async def prometheus_metrics(
    health_service = Depends(get_health_service),
) -> Response:
    """Get Prometheus metrics in text format."""
    metrics_text = health_service.get_prometheus_metrics()
    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@router.get("/json", response_model=Dict[str, Any])
async def json_metrics(
    health_service = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get metrics in JSON format."""
    return await health_service.get_metrics_data()
