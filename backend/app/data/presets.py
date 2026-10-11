"""Loader for versioned, offline synthetic demo presets (Issue #67)."""

import json
from pathlib import Path
from typing import Any, Dict, List

from .provenance import normalize_provenance
from ..schemas import (
    AbsoluteRiskReductionEffect,
    ArmCounts,
    RelativeRiskEffect,
    StressScenario,
    TrialAssumptions,
)


def get_demo_data_dir() -> Path:
    """Resolve ``demo-data`` relative to the repository root."""
    repo_root = Path(__file__).resolve().parents[3]
    demo_dir = repo_root / "demo-data"
    if not demo_dir.exists():
        demo_dir = Path.cwd() / "demo-data"
    return demo_dir


def list_demo_presets() -> List[str]:
    """Return preset identifiers declared by the local index, if present."""
    index_file = get_demo_data_dir() / "index.json"
    if not index_file.is_file():
        return []
    with index_file.open(encoding="utf-8") as file:
        data = json.load(file)
    return [entry["preset_id"] for entry in data.get("presets", [])]


def load_demo_preset(preset_id: str) -> Dict[str, Any]:
    """Load a D1 fixture into current v1 API models and normalized provenance."""
    demo_dir = get_demo_data_dir().resolve()
    preset_dir = (demo_dir / preset_id).resolve()
    if preset_dir.parent != demo_dir or not preset_dir.is_dir():
        raise FileNotFoundError(f"Preset directory not found for: {preset_id}")

    with (preset_dir / "manifest.json").open(encoding="utf-8") as file:
        manifest = json.load(file)
    with (preset_dir / "inputs.json").open(encoding="utf-8") as file:
        inputs = json.load(file)

    planned_raw = inputs["planned_design"]
    effect_raw = planned_raw["effect"]
    if effect_raw["kind"] == "relative_risk":
        effect = RelativeRiskEffect(**effect_raw)
    elif effect_raw["kind"] == "absolute_risk_reduction":
        effect = AbsoluteRiskReductionEffect(**effect_raw)
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
    fixed_enrollment = ArmCounts(**inputs["fixed_enrollment"])
    stress_scenario = StressScenario(**inputs["stress_scenario"])

    return {
        "manifest": manifest,
        "planned_design": planned_design,
        "fixed_enrollment": fixed_enrollment,
        "stress_scenario": stress_scenario,
        "simulation": inputs.get("simulation", {"replicates": 10_000, "seed": 42}),
        "provenance": normalize_provenance(manifest.get("provenance", [])),
    }
