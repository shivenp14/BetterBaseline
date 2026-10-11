"""Compute service wrapper, concurrency semaphore, and computational resource guards (Issue #68)."""

from contextlib import contextmanager
import math
from threading import BoundedSemaphore
from typing import Any, Callable, Dict, Generator, Optional, TypeVar

from ..cache import BoundedComputeCache, make_cache_key
from ..settings import settings
from ..statistics.errors import StatisticalInputError

T = TypeVar("T")


class ResourceSaturatedError(Exception):
    """Raised when CPU compute concurrency permits are exhausted (retryable 429/503)."""

    def __init__(self, message: str = "Compute capacity saturated; retry request shortly.", retry_after: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class ComputeResourceGuard:
    """Validates computational dimensions and resource bounds before numerical allocation."""

    def __init__(
        self,
        max_mc_reps: int = 100_000,
        max_grid_cells: int = 5_000,
        max_enrolled_per_arm: int = 1_000_000,
        max_concurrent_compute: int = 4,
        cache_capacity: int = 256,
    ) -> None:
        self.max_mc_reps = max_mc_reps
        self.max_grid_cells = max_grid_cells
        self.max_enrolled_per_arm = max_enrolled_per_arm
        self.semaphore = BoundedSemaphore(value=max(1, max_concurrent_compute))
        self.cache = BoundedComputeCache(capacity=cache_capacity)

    def check_simulation_options(self, replicates: int, seed: Optional[int] = None) -> None:
        """Validate Monte Carlo replicate ceilings."""
        if replicates > self.max_mc_reps:
            raise StatisticalInputError(
                f"Replicates exceeds maximum limit of {self.max_mc_reps}",
                field="simulation.replicates",
                code="RESOURCE_LIMIT",
            )
        if replicates < 1:
            raise StatisticalInputError(
                "Replicates must be at least 1",
                field="simulation.replicates",
                code="RESOURCE_LIMIT",
            )

    def check_grid_dimensions(self, x_steps: int, y_steps: int) -> None:
        """Validate sensitivity grid dimension and total cell count caps."""
        total_cells = x_steps * y_steps
        if total_cells > self.max_grid_cells:
            raise StatisticalInputError(
                f"Total grid cells exceed maximum limit of {self.max_grid_cells} ({total_cells} requested)",
                field="grid.dimensions",
                code="RESOURCE_LIMIT",
            )

    def check_design_inflation(self, evaluable_per_arm: int, dropout: float) -> None:
        """Check that enrollment produced by design dropout inflation does not exceed maximum limit."""
        if dropout >= 1.0 or dropout < 0.0:
            return
        if dropout == 0.0:
            enrolled = evaluable_per_arm
        else:
            enrolled = math.ceil(evaluable_per_arm / (1.0 - dropout))

        if enrolled > self.max_enrolled_per_arm:
            raise StatisticalInputError(
                f"Inflated enrollment exceeds maximum limit of {self.max_enrolled_per_arm} per arm ({enrolled} required)",
                field="design.enrolled_n",
                code="RESOURCE_LIMIT",
            )

    def check_enrollment(self, control_enrolled: int, treatment_enrolled: int) -> None:
        """Validate fixed enrolled participant counts."""
        for name, val in [("control", control_enrolled), ("treatment", treatment_enrolled)]:
            if val > self.max_enrolled_per_arm:
                raise StatisticalInputError(
                    f"Enrollment exceeds maximum limit of {self.max_enrolled_per_arm} per arm ({val} requested)",
                    field=f"fixed_enrollment.{name}",
                    code="RESOURCE_LIMIT",
                )

    @contextmanager
    def acquire_compute_permit(self, timeout: float = 0.0) -> Generator[None, None, None]:
        """Acquire a concurrency permit, releasing it on exit regardless of success or failure."""
        acquired = self.semaphore.acquire(blocking=False)
        if not acquired:
            raise ResourceSaturatedError()
        try:
            yield
        finally:
            self.semaphore.release()


# Global compute guard instance initialized from settings
_global_guard: Optional[ComputeResourceGuard] = None


def get_compute_guard() -> ComputeResourceGuard:
    global _global_guard
    if _global_guard is None:
        _global_guard = ComputeResourceGuard(
            max_mc_reps=settings.max_mc_reps,
            max_grid_cells=settings.max_grid_cells,
            max_enrolled_per_arm=settings.max_enrolled_per_arm,
            max_concurrent_compute=settings.max_concurrent_compute,
            cache_capacity=settings.cache_size,
        )
    return _global_guard


def execute_guarded_computation(
    func: Callable[..., T],
    *args: Any,
    cache_key: Optional[str] = None,
    **kwargs: Any,
) -> T:
    """Execute computation guarded by CPU concurrency semaphore and optional LRU cache."""
    guard = get_compute_guard()

    # Check cache first if a key was provided
    if cache_key:
        cached_result = guard.cache.get(cache_key)
        if cached_result is not None:
            return cached_result

    # Acquire CPU concurrency permit
    with guard.acquire_compute_permit():
        result = func(*args, **kwargs)

    if cache_key:
        guard.cache.set(cache_key, result)

    return result
