#!/usr/bin/env python3
"""Regenerate final preset responses through the merged backend v1 functions.

Run from the repository root with the backend's locked Python 3.12 environment:
    uv run --locked --directory backend python ../demo-data/generate_snapshots.py

Pass --check to fail if checked-in generated content differs. Operational
computed_at timestamps are omitted from response bodies so repeated runs are
byte-for-byte stable; the exact engine source commit and package versions remain
recorded in each snapshot.
"""

from __future__ import annotations

import argparse
import json
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
    "backend/app/statistics",
    "backend/app/routers/design.py",
    "backend/app/routers/scenarios.py",
    "backend/app/services/grid.py",
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
                if not path.exists() or path.read_bytes() != content:
                    mismatches.append(path.relative_to(ROOT).as_posix())
            else:
                path.write_bytes(content)
        if mismatches:
            print("Generated snapshots are stale: " + ", ".join(mismatches), file=sys.stderr)
            return 1
        if args.check:
            print("All three generated snapshots and manifests match the backend output.")
        else:
            print("Generated measured final response snapshots for all three presets.")
        return 0
    except Exception as exc:
        print(f"Snapshot generation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
