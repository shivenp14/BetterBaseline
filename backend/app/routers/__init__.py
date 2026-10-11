"""API router modules for Better Baseline."""

from .health import router as health_router
from .design import router as design_router
from .scenarios import router as scenarios_router
from .grid import router as grid_router

__all__ = ["health_router", "design_router", "scenarios_router", "grid_router"]
