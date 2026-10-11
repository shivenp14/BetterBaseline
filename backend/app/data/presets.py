"""Demo preset loader and normalization (Issue #67).

Loads and normalizes D1 versioned synthetic offline demo presets into typed
Better Baseline API models and field provenance dictionaries.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .provenance import normalize_provenance
from ..schemas import (
    ArmCounts,
    FieldProvenance,
    RelativeRiskEffect,
    AbsoluteRiskReductionEffect,
    StressScenario,
    TrialAssumptions,
)


def get_demo_data_dir() -> Path:
    """Resolve demo-data directory relative to repository root."""
    # backend/app/data/presets.py -> backend/app/data -> backend/app -> backend -> root
    repo_root = Path(__file__).resolve().parents[3]
    demo_dir = repo_root / "demo-data"
    if not demo_dir.exists():
        # Fallback if working inside a submodule or alternative tree
        demo_dir = Path.cwd() / "demo-data"
    return demo_dir


def list_demo_presets() -> List[str]:
    """List available demo preset identifiers from demo-data index.json."""
    demo_dir = get_demo_data_dir()
    index_file = demo_dir / "index.json"
    if not index_file.exists():
        return []
    with open(index_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [entry["preset_id"] for entry in data.get("presets", [])]


def load_demo_preset(preset_id: str) -> Dict[str, Any]:
    """Load and normalize a D1 demo preset by its preset_id.

    Returns:
    - manifest: dict from manifest.json
    - planned_design: typed TrialAssumptions
    - fixed_enrollment: typed ArmCounts
    - stress_scenario: typed StressScenario
    - simulation: dict with replicates and seed
    - provenance: normalized Dict[str, FieldProvenance]
    """
    demo_dir = get_demo_data_dir()
    preset_dir = demo_dir / preset_id
    if not preset_dir.exists():
        raise FileNotFoundError(f"Preset directory not found for: {preset_id}")

    manifest_file = preset_dir / "manifest.json"
    inputs_file = preset_dir / "inputs.json"

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(inputs_file, "r", encoding="utf-8") as f:
        inputs = json.load(f)

    # Normalize planned design
    planned_raw = inputs["planned_design"]
    effect_raw = planned_raw["effect"]
    if effect_raw["kind"] == "relative_risk":
        effect = RelativeRiskEffect(kind="relative_risk", value=effect_raw["value"])
    elif effect_raw["kind"] == "absolute_risk_reduction":
        effect = AbsoluteRiskReductionEffect(kind="absolute_risk_reduction", value=effect_raw["value"])
    else:
        raise ValueError(f"Unknown effect kind: {effect_raw['kind']}")

    planned_design = TrialAssumptions(
        model_version=planned_raw.get("model_version", "binary-v1"),
        control_event_rate=planned_raw["control_event_rate"],
        effect=effect,
        alpha=planned_raw["alpha"],
        target_power=planned_raw["target_power"],
        allocation_ratio=planned_raw.get("allocation_ratio", 1.0),
        dropout=planned_raw["dropout"],
    )

    # Normalize fixed enrollment
    fixed_enrollment = ArmCounts(
        control=inputs["fixed_enrollment"]["control"],
        treatment=inputs["fixed_enrollment"]["treatment"],
    )

    # Normalize stress scenario
    stress_raw = inputs["stress_scenario"]
    stress_scenario = StressScenario(
        control_event_rate=stress_raw["control_event_rate"],
        dropout=stress_raw["dropout"],
        effect_override=stress_raw.get("effect_override"),
    )

    # Normalize provenance from manifest records
    manifest_prov = manifest.get("provenance", [])
    normalized_provenance = normalize_provenance(manifest_prov)

    return {
        "manifest": manifest,
        "planned_design": planned_design,
        "fixed_enrollment": fixed_enrollment,
        "stress_scenario": stress_scenario,
        "simulation": inputs.get("simulation", {"replicates": 10000, "seed": 42}),
        "provenance": normalized_provenance,
    }
