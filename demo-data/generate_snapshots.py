#!/usr/bin/env python3
"""Regenerate final preset responses through the merged backend v1 functions.

Run from the repository root with the backend's locked Python 3.12 environment:
    uv run --locked --directory backend python ../demo-data/generate_snapshots.py

Pass --check to fail if checked-in generated content differs. Operational
computed_at timestamps are omitted from response bodies. Provenance, metadata,
inputs, counts, masks, and seeded simulation outcomes remain exact; only listed
continuous analytic results allow 1e-12 relative / 1e-15 absolute math-library
rounding differences across platforms.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "demo-data"
sys.path.insert(0, str(ROOT / "backend"))
GRID_REQUEST = {
    "x_baseline": {"min": 0.05, "max": 0.30, "steps": 26},
    "y_dropout": {"min": 0.0, "max": 0.30, "steps": 31},
}
ENGINE_PATHS = (
    "backend/app",
    "backend/pyproject.toml",
    "backend/uv.lock",
)
OMITTED_OPERATIONAL_FIELDS = [
    "/design/computed_at (not present in design response)",
    "/point/metadata/computed_at",
    "/grid/computed_at",
]


def _dump(value: object) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"Expected a Pydantic response model, got {type(value)!r}")


def _engine_commit() -> str:
    try:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", *ENGINE_PATHS],
            cwd=ROOT,
            text=True,
        )
        if dirty.strip():
            raise RuntimeError("Commit or discard backend source changes before generating snapshots")
        shallow = subprocess.check_output(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=ROOT,
            text=True,
        ).strip()
        if shallow == "true":
            raise RuntimeError(
                "Full Git history is required to identify the committed backend engine source; "
                "fetch with actions/checkout fetch-depth: 0"
            )
        return subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", *ENGINE_PATHS],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Unable to identify the committed backend engine source") from exc


def _field_provenance(manifest: dict) -> dict:
    from app.schemas import FieldProvenance

    return {
        record["field"]: FieldProvenance(
            source="synthetic_preset", description=record["basis"]
        )
        for record in manifest["provenance"]
    }


def _generate(preset_id: str, engine_commit: str) -> tuple[dict, dict]:
    # Imports happen after CLI setup so the required backend environment failure
    # names the locked environment rather than producing a partial snapshot.
    from types import SimpleNamespace

    from app.routers.design import calculate_design
    from app.routers.scenarios import EvaluationRequest, _evaluate
    from app.schemas import DesignCalculateRequest, ScenarioGridRequest
    from app.services.compute import ComputeResourceGuard
    from app.services.grid import compute_grid

    folder = DATA / preset_id
    manifest = json.loads((folder / "manifest.json").read_text())
    inputs = json.loads((folder / "inputs.json").read_text())
    provenance = _field_provenance(manifest)

    design_request = DesignCalculateRequest.model_validate(inputs["planned_design"])
    guard = ComputeResourceGuard()
    request_context = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(compute_guard=guard)))
    design_response = calculate_design(design_request, request_context)

    point_payload = {
        "planned_design": inputs["planned_design"],
        "fixed_enrollment": inputs["fixed_enrollment"],
        "stress_scenario": inputs["stress_scenario"],
        "simulation": inputs["simulation"],
        "provenance": provenance,
    }
    point_request = EvaluationRequest.model_validate(point_payload)
    point_response = _evaluate(point_request, guard)

    grid_payload = {
        "planned_design": inputs["planned_design"],
        "fixed_enrollment": inputs["fixed_enrollment"],
        **GRID_REQUEST,
        "selected_scenario": inputs["stress_scenario"],
        "provenance": provenance,
    }
    grid_request = ScenarioGridRequest.model_validate(grid_payload)
    grid_response = compute_grid(grid_request)

    point = _dump(point_response)
    point["metadata"].pop("computed_at")
    grid = _dump(grid_response)
    grid.pop("computed_at")
    snapshot = {
        "schema_version": 1,
        "preset_id": preset_id,
        "result_status": "measured_generated_backend_output",
        "inputs_hash": manifest["inputs_hash"],
        "engine_commit": engine_commit,
        "generation": {
            "command": "uv run --locked --directory backend python ../demo-data/generate_snapshots.py",
            "engine_commit": engine_commit,
            "seed": inputs["simulation"]["seed"],
            "replicates": inputs["simulation"]["replicates"],
            "grid_request": GRID_REQUEST,
            "software_versions": {
                "python": platform.python_version(),
                "numpy": version("numpy"),
                "scipy": version("scipy"),
                "statsmodels": version("statsmodels"),
                "fastapi": version("fastapi"),
                "pydantic": version("pydantic"),
                "betterbaseline_backend": "0.1.0",
            },
            "omitted_operational_fields": OMITTED_OPERATIONAL_FIELDS,
        },
        "requests": {
            "design": design_request.model_dump(mode="json"),
            "point": point_request.model_dump(mode="json"),
            "grid": grid_request.model_dump(mode="json"),
        },
        "design": _dump(design_response),
        "point": point,
        "grid": grid,
    }
    return snapshot, manifest


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=False, allow_nan=False) + "\n").encode()


def _diff_summary(expected: object, actual: object, pointer: str = "") -> list[str]:
    """Describe a bounded set of exact JSON differences for failed --check runs."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences = []
        for key in expected.keys() | actual.keys():
            child = f"{pointer}/{key}"
            if key not in expected or key not in actual:
                differences.append(f"{child}: key missing from one value")
            else:
                differences.extend(_diff_summary(expected[key], actual[key], child))
            if len(differences) >= 12:
                return differences[:12]
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        if len(expected) != len(actual):
            differences.append(f"{pointer}: list lengths differ ({len(expected)} != {len(actual)})")
        for index, (left, right) in enumerate(zip(expected, actual)):
            differences.extend(_diff_summary(left, right, f"{pointer}/{index}"))
            if len(differences) >= 12:
                break
        return differences[:12]
    if type(expected) is not type(actual) or expected != actual:
        return [f"{pointer}: expected {expected!r}, got {actual!r}"]
    return []


def _is_platform_sensitive_float(pointer: str) -> bool:
    """Allow only continuous analytic fields to vary at floating-point noise."""
    if pointer == "/design/nominal_power_evaluable" or pointer.startswith("/point/analytic/"):
        return True
    if pointer in {
        "/point/monte_carlo/mcse_two_sided",
        "/point/monte_carlo/mcse_favorable",
        "/grid/analytic_delta",
        "/grid/worst_case_power",
    }:
        return True
    parts = pointer.split("/")
    if len(parts) == 5 and parts[:2] == ["", "grid"]:
        if parts[2] == "power" and parts[3].isdigit() and parts[4].isdigit():
            return True
        if parts[2] == "power_curve" and parts[3].isdigit() and parts[4] in {"p_control", "power"}:
            return True
        if parts[2] == "frontier_points" and parts[3].isdigit() and parts[4] in {"p_control", "dropout", "power"}:
            return True
    if (
        len(parts) == 4
        and parts[:2] == ["", "grid"]
        and parts[2] in {"planned_point", "selected_point"}
        and parts[3] in {"p_control", "dropout", "power"}
    ):
        return True
    if (
        len(parts) == 6
        and parts[:2] == ["", "grid"]
        and parts[2] == "contour_segments"
        and parts[3].isdigit()
        and parts[4] in {"start", "end"}
        and parts[5] in {"p_control", "dropout"}
    ):
        return True
    return False


def _matches_snapshot(expected: object, actual: object, pointer: str = "") -> bool:
    """Compare snapshots strictly except for documented continuous float noise."""
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(
            _matches_snapshot(expected[key], actual[key], f"{pointer}/{key}")
            for key in expected
        )
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(
            _matches_snapshot(left, right, f"{pointer}/{index}")
            for index, (left, right) in enumerate(zip(expected, actual))
        )
    if isinstance(expected, float) and _is_platform_sensitive_float(pointer):
        return math.isclose(expected, actual, rel_tol=1e-12, abs_tol=1e-15)
    return expected == actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare generated files without writing")
    args = parser.parse_args()
    try:
        engine_commit = _engine_commit()
        index_path = DATA / "index.json"
        index = json.loads(index_path.read_text())
        outputs: dict[Path, bytes] = {}
        for entry in index["presets"]:
            preset_id = entry["preset_id"]
            snapshot, manifest = _generate(preset_id, engine_commit)
            snapshot_name = "final-response.json"
            snapshot_path = DATA / preset_id / snapshot_name
            outputs[snapshot_path] = _json_bytes(snapshot)
            manifest["final_response_file"] = snapshot_name
            manifest["contract_status"] = "canonical_backend_v1"
            manifest["snapshot_requirements"] = {
                "status": "generated_and_reproducible",
                "actual_engine_functions_required": True,
                "fixed_seed": snapshot["generation"]["seed"],
                "replicates": snapshot["generation"]["replicates"],
                "record_software_versions": True,
                "record_engine_commit": True,
                "schema_alignment_gate": "B1 complete; canonical backend v1 response models",
            }
            manifest["warnings"] = [
                "All input assumptions are synthetic and are not clinical evidence.",
                "mock-response.json remains illustrative; final-response.json is generated backend output.",
            ]
            outputs[DATA / entry["manifest"]] = _json_bytes(manifest)
            entry["final_response"] = f"{preset_id}/{snapshot_name}"
        outputs[index_path] = _json_bytes(index)

        mismatches = []
        for path, content in outputs.items():
            if args.check:
                if not path.exists():
                    mismatches.append(path.relative_to(ROOT).as_posix())
                    continue
                expected = json.loads(path.read_bytes())
                actual = json.loads(content)
                if not _matches_snapshot(expected, actual):
                    mismatches.append(path.relative_to(ROOT).as_posix())
            else:
                path.write_bytes(content)
        if mismatches:
            print("Generated snapshots are stale: " + ", ".join(mismatches), file=sys.stderr)
            for path in outputs:
                if path.relative_to(ROOT).as_posix() not in mismatches:
                    continue
                expected = json.loads(path.read_text())
                actual = json.loads(outputs[path])
                for difference in _diff_summary(expected, actual):
                    print(f"  {path.relative_to(ROOT).as_posix()}{difference}", file=sys.stderr)
            return 1
        if args.check:
            print(
                "All three generated snapshots and manifests match: discrete data and provenance exact; "
                "continuous analytic floats within 1e-12 relative / 1e-15 absolute tolerance."
            )
        else:
            print("Generated measured final response snapshots for all three presets.")
        return 0
    except Exception as exc:
        print(f"Snapshot generation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
