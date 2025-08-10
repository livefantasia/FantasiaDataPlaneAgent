"""Health check router for DataPlane Agent."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

router = APIRouter(prefix="/health", tags=["health"])

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


@router.get("/", response_model=Dict[str, Any])
async def health_check(
    health_service = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get application health status."""
    return await health_service.get_health_status()


@router.get("/detailed", response_model=Dict[str, Any])
async def detailed_health_check(
    health_service = Depends(get_health_service),
) -> Dict[str, Any]:
    """Get detailed health status with component information."""
    health_status = await health_service.get_health_status()
    metrics_data = await health_service.get_metrics_data()
    
    return {
        **health_status,
        "metrics": metrics_data,
    }
