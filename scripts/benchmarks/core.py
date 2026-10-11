"""D6 core measurements from D1 inputs; separate from A7's profiler.

Run from repo root with PYTHONPATH=backend. See README.md in this directory.
API/browser/cache measurements await B6; direct core workloads use real engines.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
GRID_BASELINES = tuple((5 + index) / 100 for index in range(31))
GRID_DROPOUTS = tuple(index / 100 for index in range(21))
PRESETS = ("baseline-collapse-v1", "attrition-shock-v1", "stable-design-v1")


# Cross-platform audit tolerance for continuous probabilities/MCSE only.
# Counts, dimensions, masks, seeds and same-environment replay remain exact.
FLOAT_REL_TOL = 1e-12
FLOAT_ABS_TOL = 1e-12

def close_float(actual, expected):
    return math.isclose(actual, expected, rel_tol=FLOAT_REL_TOL, abs_tol=FLOAT_ABS_TOL)

def normalized_source_hash(data):
    text = data.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def measure(call, *, runs=30, warmups=3):
    for name, value, minimum, maximum in (("runs", runs, 30, 10000), ("warmups", warmups, 1, 100)):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    reference = call()
    payload = canonical(reference)
    for _ in range(warmups - 1):
        if canonical(call()) != payload:
            raise RuntimeError("Identical inputs produced different core results")
    samples = []
    for _ in range(runs):
        start = time.perf_counter_ns()
        result = call()
        samples.append(time.perf_counter_ns() - start)
        if canonical(result) != payload:
            raise RuntimeError("Identical inputs produced different core results")
    return {
        "measured_runs": runs, "excluded_warmups": warmups, "raw_elapsed_ns": samples,
        "median_ms": statistics.median(samples) / 1e6,
        "p95_ms": sorted(samples)[math.ceil(.95 * runs) - 1] / 1e6,
        "p95_definition": "nearest rank, ceil(0.95*runs), one-based",
        "representative_result": reference,
        "result_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "identical_results": True,
    }


def prepare(workload, inputs):
    from app.statistics.effect import resolve_treatment_risk
    from app.statistics.inputs import Dropout, Effect, FixedEnrollment

    plan = inputs["planned_design"]
    if plan["allocation_ratio"] != 1 or plan["model_version"] != "binary-v1":
        raise ValueError("Only equal-arm binary-v1 presets are supported")
    planned_effect = Effect(**plan["effect"])
    if workload == "design":
        from app.statistics.sample_size import minimum_sample_size
        treatment = resolve_treatment_risk(plan["control_event_rate"], planned_effect)
        dropout = Dropout(**plan["dropout"])
        return lambda: asdict(minimum_sample_size(plan["control_event_rate"], treatment,
                                                  plan["target_power"], plan["alpha"], dropout))
    stress = inputs["stress_scenario"]
    effect = Effect(**stress["effect_override"]) if stress["effect_override"] else planned_effect
    fixed = inputs["fixed_enrollment"]
    enrollment = FixedEnrollment(**fixed)
    planned_dropout = Dropout(**plan["dropout"])
    selected_dropout = Dropout(**stress["dropout"])
    if workload == "grid":
        from app.statistics.stress_grid import GridCoordinate, stress_grid
        planned = GridCoordinate(plan["control_event_rate"], planned_dropout.control)
        selected = GridCoordinate(stress["control_event_rate"], selected_dropout.control)
        return lambda: asdict(stress_grid(
            enrollment, effect, GRID_BASELINES, GRID_DROPOUTS,
            planned_point=planned, selected_point=selected,
            alpha=plan["alpha"], target_power=plan["target_power"],
        ))
    if workload != "monte-carlo":
        raise ValueError("Unknown workload")
    from app.statistics.simulation import simulate_binary
    treatment = resolve_treatment_risk(stress["control_event_rate"], effect)
    options = inputs["simulation"]
    return lambda: simulate_binary(fixed["control"], fixed["treatment"],
                                  stress["control_event_rate"], treatment,
                                  stress["dropout"]["control"], stress["dropout"]["treatment"],
                                  plan["alpha"], options["replicates"], options["seed"])


def validate_result(workload, inputs, result):
    """Check public numerical invariants outside the timed computation."""
    from app.statistics.analytic import analytic_power
    from app.statistics.effect import resolve_treatment_risk
    from app.statistics.inputs import Effect, expected_retained_count

    plan = inputs["planned_design"]
    if workload == "design":
        n = result["evaluable_per_arm"]
        treatment = resolve_treatment_risk(plan["control_event_rate"], Effect(**plan["effect"]))
        power = analytic_power(plan["control_event_rate"], treatment, n, n, plan["alpha"]).power
        if not close_float(power, result["achieved_power"]) or power < plan["target_power"]:
            raise ValueError("Design result fails direct analytical agreement/target")
        if n > 2 and analytic_power(plan["control_event_rate"], treatment, n - 1, n - 1, plan["alpha"]).power >= plan["target_power"]:
            raise ValueError("Design result is not the minimum integer N")
        retained = expected_retained_count(result["enrolled_per_arm"], plan["dropout"]["control"])
        if retained < n or expected_retained_count(result["enrolled_per_arm"] - 1, plan["dropout"]["control"]) >= n:
            raise ValueError("Design enrollment inflation is inconsistent")
        return
    if workload == "monte-carlo":
        options = inputs["simulation"]
        if result["replicates"] != options["replicates"] or result["seed"] != options["seed"]:
            raise ValueError("Simulation identity changed")
        for fraction, mcse in (("significant_two_sided_fraction", "mcse_two_sided"),
                               ("significant_favorable_fraction", "mcse_favorable")):
            value = result[fraction]
            expected = math.sqrt(value * (1 - value) / options["replicates"])
            if not 0 <= value <= 1 or not close_float(result[mcse], expected):
                raise ValueError("Simulation fractions/MCSE are inconsistent")
        if result["significant_favorable_fraction"] > result["significant_two_sided_fraction"]:
            raise ValueError("Favorable rejections exceed two-sided rejections")
        return
    if workload != "grid":
        raise ValueError("Unknown workload")
    if result["fixed_enrollment"] != inputs["fixed_enrollment"]:
        raise ValueError("Grid enrollment changed")
    if tuple(result["x_baseline"]) != GRID_BASELINES or tuple(result["y_dropout"]) != GRID_DROPOUTS:
        raise ValueError("Grid axes changed")
    for field in ("power", "invalid_mask", "below_target"):
        if len(result[field]) != 21 or any(len(row) != 31 for row in result[field]):
            raise ValueError("Grid dimensions are not dropout-major 21 by 31")
    effect = Effect(**(inputs["stress_scenario"]["effect_override"] or plan["effect"]))
    valid = []
    for row, dropout in enumerate(GRID_DROPOUTS):
        for column, baseline in enumerate(GRID_BASELINES):
            point = result["power"][row][column]
            if result["invalid_mask"][row][column] != (point is None):
                raise ValueError("Grid null/mask disagreement")
            if point is not None:
                n = expected_retained_count(inputs["fixed_enrollment"]["control"], dropout)
                expected = analytic_power(baseline, resolve_treatment_risk(baseline, effect), n, n, plan["alpha"]).power
                if not close_float(point, expected) or result["below_target"][row][column] != (point < plan["target_power"]):
                    raise ValueError("Grid cell fails direct scalar/target agreement")
                valid.append(point)
    if result["invalid_cell_count"] != 651 - len(valid) or (not close_float(result["worst_case_power"], min(valid)) if valid else result["worst_case_power"] is not None):
        raise ValueError("Grid summary is inconsistent")
    if len(result["power_curve"]) != 31:
        raise ValueError("Grid power curve has wrong length")
    for baseline, point in zip(GRID_BASELINES, result["power_curve"]):
        dropout = inputs["stress_scenario"]["dropout"]["control"]
        n = expected_retained_count(inputs["fixed_enrollment"]["control"], dropout)
        expected = analytic_power(baseline, resolve_treatment_risk(baseline, effect), n, n, plan["alpha"]).power
        if (point["baseline"], point["dropout"], point["expected_evaluable_per_arm"], point["below_target"]) != (baseline, dropout, n, point["power"] < plan["target_power"]) or not close_float(point["power"], expected):
            raise ValueError("Selected-dropout curve fails direct agreement")


def workload_parameters(workload, inputs):
    from app.statistics.analytic import COHEN_H_NORMAL_METHOD, COHEN_H_NORMAL_VERSION
    parameters = {"fixture_inputs": inputs, "workload": workload}
    if workload == "grid":
        parameters.update({"x_baseline": GRID_BASELINES, "y_dropout": GRID_DROPOUTS,
                           "axis_origin": "synthetic_benchmark: baseline .05.. .35 and dropout .00.. .20 in .01 steps"})
    if workload in ("design", "grid"):
        parameters.update({"method": COHEN_H_NORMAL_METHOD, "method_version": COHEN_H_NORMAL_VERSION})
    else:
        from app.statistics.simulation import METHOD
        parameters.update({"method": METHOD, "rng": "numpy.random.PCG64"})
    return parameters


def environment():
    packages = {}
    for package in ("numpy", "scipy", "statsmodels"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = "not installed"
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    paths = sorted((ROOT / "backend/app/statistics").glob("*.py"))
    return {
        "python": platform.python_version(), "packages": packages,
        "hardware": {"os": platform.platform(), "machine": platform.machine(),
                     "processor": platform.processor() or None, "logical_cpu_count": os.cpu_count()},
        "git_commit": commit,
        "core_source_sha256": {str(path.relative_to(ROOT)): normalized_source_hash(path.read_bytes()) for path in paths},
        "source_hash_policy": "UTF-8 text, CRLF/CR normalized to LF",
        "harness_source_sha256": normalized_source_hash(Path(__file__).read_bytes()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", choices=("design", "monte-carlo", "grid"), required=True)
    parser.add_argument("--preset", choices=PRESETS, default="baseline-collapse-v1")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        directory = ROOT / "demo-data" / args.preset
        inputs = json.loads((directory / "inputs.json").read_text())
        manifest = json.loads((directory / "manifest.json").read_text())
        inputs_hash = "sha256:" + hashlib.sha256(canonical(inputs).encode()).hexdigest()
        if inputs_hash != manifest["inputs_hash"]:
            raise ValueError("D1 fixture hash mismatch")
        call = prepare(args.workload, inputs)
        measurement = measure(call, runs=args.runs, warmups=args.warmups)
        validate_result(args.workload, inputs, measurement["representative_result"])
        parameters = workload_parameters(args.workload, inputs)
        report = {
            "benchmark_schema_version": 1, "measured_at_utc": datetime.now(timezone.utc).isoformat(),
            "workload": args.workload, "preset_id": args.preset, "preset_version": manifest["preset_version"],
            "inputs": inputs, "inputs_hash": inputs_hash,
            "provenance": manifest["provenance"],
            "computation_parameters": parameters,
            "computation_sha256": hashlib.sha256(canonical(parameters).encode()).hexdigest(),
            "numerical_invariants_checked": True,
            "scope": "direct uncached core call and local result conversion; excludes fixture parsing, setup, invariant checks, HTTP, frontend, and report serialization; per-cell effect resolution is included for grid",
            "cache_condition": "not applicable: direct core call without API cache",
            "timing_notice": "Local hardware/load-dependent measurements; no latency threshold or clinical validation claim.",
            "environment": environment(),
            "measurement": measurement,
        }
        payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
    except (ValueError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
