"""API routers for DataPlane Agent."""

from .health import router as health_router
from .metrics import router as metrics_router

__all__ = ["health_router", "metrics_router"]
