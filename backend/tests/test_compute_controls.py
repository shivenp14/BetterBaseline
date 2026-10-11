"""Tests for bounded LRU cache, compute guards, concurrency limits, and resource ceilings (Issue #68)."""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from app.cache import BoundedComputeCache, make_cache_key
from app.main import create_app
from app.services.compute import (
    ComputeResourceGuard,
    execute_guarded_computation,
    get_compute_guard,
)
from app.settings import Settings
from app.statistics.errors import StatisticalInputError


# ── SEAM 1: CACHE TESTS ──

def test_cache_key_deterministic_and_sensitive_to_seed_and_version():
    params_a = {"control_event_rate": 0.20, "replicates": 10000, "seed": 42}
    params_b = {"replicates": 10000, "control_event_rate": 0.20, "seed": 42}  # different key order
    params_diff_seed = {"control_event_rate": 0.20, "replicates": 10000, "seed": 43}

    key_a = make_cache_key(route="/api/v1/scenarios/evaluate", model_version="binary-v1", params=params_a)
    key_b = make_cache_key(route="/api/v1/scenarios/evaluate", model_version="binary-v1", params=params_b)
    key_diff_seed = make_cache_key(route="/api/v1/scenarios/evaluate", model_version="binary-v1", params=params_diff_seed)
    key_diff_version = make_cache_key(route="/api/v1/scenarios/evaluate", model_version="binary-v2", params=params_a)

    assert key_a == key_b
    assert key_a != key_diff_seed
    assert key_a != key_diff_version
    assert key_a.startswith("sha256:")


def test_bounded_lru_cache_capacity_eviction():
    cache = BoundedComputeCache(capacity=2)
    cache.set("k1", {"val": 1})
    cache.set("k2", {"val": 2})

    assert cache.get("k1") == {"val": 1}
    # Accessing k1 marks it as recently used; inserting k3 should evict k2
    cache.set("k3", {"val": 3})

    assert cache.get("k1") == {"val": 1}
    assert cache.get("k2") is None
    assert cache.get("k3") == {"val": 3}


# ── SEAM 2: COMPUTE RESOURCE GUARDS ──

def test_guard_enforces_replicate_cap():
    guard = ComputeResourceGuard(max_mc_reps=10_000)
    with pytest.raises(StatisticalInputError, match="Replicates exceeds maximum limit"):
        guard.check_simulation_options(replicates=100_001, seed=42)


def test_guard_enforces_grid_cell_cap():
    guard = ComputeResourceGuard(max_grid_cells=5_000)
    with pytest.raises(StatisticalInputError, match="Total grid cells exceed maximum limit"):
        guard.check_grid_dimensions(x_steps=100, y_steps=100)  # 10,000 cells > 5,000


def test_guard_enforces_enrollment_inflation_cap():
    guard = ComputeResourceGuard(max_enrolled_per_arm=1_000_000)
    # Check that design inflation resulting in enrolled > 1,000,000 is rejected
    with pytest.raises(StatisticalInputError, match="Inflated enrollment exceeds maximum limit"):
        guard.check_design_inflation(evaluable_per_arm=900_000, dropout=0.50)  # ceil(900k / 0.5) = 1.8M > 1M


def test_guard_enforces_fixed_enrollment_cap():
    guard = ComputeResourceGuard(max_enrolled_per_arm=1_000_000)
    with pytest.raises(StatisticalInputError, match="Enrollment exceeds maximum limit"):
        guard.check_enrollment(control_enrolled=1_000_001, treatment_enrolled=500)


# ── SEAM 3: CACHED COMPUTATION AND CONCURRENCY SATURATION ──

def test_execute_guarded_computation_cache_hit():
    call_count = 0

    def expensive_func(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

    key = "sha256:test_key_hit"
    res1 = execute_guarded_computation(expensive_func, 21, cache_key=key)
    res2 = execute_guarded_computation(expensive_func, 21, cache_key=key)

    assert res1 == 42
    assert res2 == 42
    assert call_count == 1  # Second call served directly from LRU cache


def test_concurrency_saturation_returns_429_with_retry_after():
    from app.services.compute import ResourceSaturatedError
    import threading
    import time

    app = create_app()
    guard = get_compute_guard()
    # Temporarily drain the semaphore
    acquired = guard.semaphore.acquire(blocking=False)
    assert acquired is True

    # While holding permit (assuming max_concurrent_compute capacity saturated),
    # acquire the rest of the permits
    other_permits = []
    while True:
        p = guard.semaphore.acquire(blocking=False)
        if not p:
            break
        other_permits.append(p)

    client = TestClient(app)
    try:
        # Request should fail with 429 RESOURCE_SATURATED and Retry-After header
        payload = {
            "control_event_rate": 0.20,
            "effect": {"kind": "relative_risk", "value": 0.80},
            "target_power": 0.80,
            "alpha": 0.05,
            "dropout": {"control": 0.10, "treatment": 0.10},
        }
        # Clear cache to guarantee guarded computation attempt
        guard.cache.clear()
        response = client.post("/api/v1/design/calculate", json=payload)
        assert response.status_code == 429
        body = response.json()
        assert body["error"]["code"] == "RESOURCE_SATURATED"
        assert body["error"]["recoverable"] is True
        assert "Retry-After" in response.headers
    finally:
        # Release all permits
        guard.semaphore.release()
        for _ in other_permits:
            guard.semaphore.release()


def test_payload_body_size_limit_returns_413():
    app = create_app()
    client = TestClient(app)

    # Exceed max_body_bytes (1,048,576 bytes = 1MB)
    huge_data = "x" * (1024 * 1024 + 100)
    response = client.post(
        "/api/v1/design/calculate",
        content=huge_data,
        headers={"Content-Type": "application/json", "Content-Length": str(len(huge_data))},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert body["error"]["recoverable"] is False


def test_design_calculate_uses_cache():
    guard = get_compute_guard()
    guard.cache.clear()

    app = create_app()
    client = TestClient(app)
    payload = {
        "control_event_rate": 0.20,
        "effect": {"kind": "relative_risk", "value": 0.80},
        "target_power": 0.80,
        "alpha": 0.05,
        "dropout": {"control": 0.10, "treatment": 0.10},
    }

    resp1 = client.post("/api/v1/design/calculate", json=payload)
    assert resp1.status_code == 200
    assert len(guard.cache) == 1

    resp2 = client.post("/api/v1/design/calculate", json=payload)
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()
    assert len(guard.cache) == 1
