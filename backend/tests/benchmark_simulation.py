"""A7's opt-in, uncached core benchmark; never a normal pytest timing test.

From the repo root, in an environment with NumPy/SciPy installed:
    PYTHONPATH=backend python backend/tests/benchmark_simulation.py
    PYTHONPATH=backend python backend/tests/benchmark_simulation.py \
        --scenario null --output /tmp/simulation-benchmark.json
    PYTHONPATH=backend python backend/tests/benchmark_simulation.py \
        --profile /tmp/simulation-profile.pstats

Defaults: seed 42, 10,000 replicates, 3 warmups, 30 measured runs. JSON records
raw timings, nearest-rank p95, hardware/software, inputs, and seeded results.
Timings are hardware/load dependent, not assertions of a latency requirement.
Profiling (when requested) is a separate invocation outside the timed sample.
This measures the statistical function, not routes, caches, or frontend latency
(those belong to D6). No algorithm or default simulation settings are changed.
"""

import argparse
import cProfile
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

from app.statistics.errors import StatisticalInputError
from app.statistics.simulation import MAX_REPLICATES, MAX_SEED, simulate_binary

SCENARIOS = {
    "baseline-collapse": dict(n_c=903, n_t=903, p_c=.10, p_t=.075, d_c=0., d_t=0.),
    "planned": dict(n_c=903, n_t=903, p_c=.20, p_t=.15, d_c=0., d_t=0.),
    "attrition": dict(n_c=1004, n_t=1004, p_c=.20, p_t=.15, d_c=.10, d_t=.10),
    "null": dict(n_c=903, n_t=903, p_c=.20, p_t=.20, d_c=0., d_t=0.),
    "rare-events": dict(n_c=20, n_t=20, p_c=.01, p_t=.0075, d_c=.50, d_t=.50),
}


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _hardware() -> dict:
    cpu = platform.processor() or None
    if platform.system() == "Darwin":
        try:
            cpu = subprocess.run(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True, timeout=5, check=True).stdout.strip() or cpu
        except (OSError, subprocess.SubprocessError):
            pass
    return {"os": platform.platform(), "machine": platform.machine(),
            "processor": cpu, "logical_cpu_count": os.cpu_count()}


def _canonical(result: dict) -> str:
    return json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)


def run_benchmark(*, scenario: str = "baseline-collapse", runs: int = 30,
                  warmups: int = 3, replicates: int = 10_000, seed: int = 42,
                  profile: Path | None = None) -> dict:
    """Measure repeated identical seeded calls with no timing pass/fail policy."""
    for name, value, minimum, maximum in (
        ("runs", runs, 30, 10_000), ("warmups", warmups, 1, 100),
        ("replicates", replicates, 1, MAX_REPLICATES), ("seed", seed, 0, MAX_SEED),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    if scenario not in SCENARIOS:
        raise ValueError("Unknown simulation scenario")
    inputs = dict(SCENARIOS[scenario], alpha=.05, reps=replicates, seed=seed)
    measured_at = datetime.now(timezone.utc).isoformat()
    reference = simulate_binary(**inputs)
    serialized = _canonical(reference)
    # The first call is a warmup; metadata/JSON checks are outside all timings.
    for _ in range(warmups - 1):
        if _canonical(simulate_binary(**inputs)) != serialized:
            raise RuntimeError("Identical seeded inputs produced different results during warmup")
    timings_ns = []
    for _ in range(runs):
        start = time.perf_counter_ns()
        result = simulate_binary(**inputs)
        elapsed = time.perf_counter_ns() - start
        timings_ns.append(elapsed)
        if _canonical(result) != serialized:
            raise RuntimeError("Identical seeded inputs produced different results")
    if profile is not None:
        profiler = cProfile.Profile()
        result = profiler.runcall(simulate_binary, **inputs)
        profiler.dump_stats(str(profile))
        if _canonical(result) != serialized:
            raise RuntimeError("Profiling changed the seeded simulation result")

    root = Path(__file__).resolve().parents[2]
    source = root / "backend/app/statistics/simulation.py"
    status = _git(root, "status", "--porcelain")
    ordered = sorted(timings_ns)
    report = {
        "benchmark_schema_version": 1,
        "measured_at_utc": measured_at,
        "scenario": scenario,
        "scope": "uncached simulate_binary call: validation, RNG, computation, aggregates, and warnings",
        "timing_notice": "Hardware/load-dependent local measurements; no latency threshold or clinical validation claim.",
        "timer": "time.perf_counter_ns",
        "warmup_runs_excluded": warmups,
        "measured_runs": runs,
        "inputs": inputs,
        "method": reference["method"],
        "software_versions": reference["software_versions"],
        "hardware": _hardware(),
        "git_commit": _git(root, "rev-parse", "HEAD"),
        "working_tree_dirty": None if status is None else bool(status),
        "simulation_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "benchmark_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "seeded_result_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
        "seeded_results_identical": True,
        "representative_result": reference,
        "raw_elapsed_ns": timings_ns,
        "summary_ms": {
            "median": statistics.median(timings_ns) / 1_000_000,
            "p95": ordered[math.ceil(.95 * runs) - 1] / 1_000_000,
            "min": ordered[0] / 1_000_000,
            "max": ordered[-1] / 1_000_000,
        },
        "p95_definition": "nearest rank: sorted sample at ceil(0.95 * measured_runs), one-based",
        "profile_file": str(profile) if profile is not None else None,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="baseline-collapse")
    parser.add_argument("--runs", type=int, default=30, help="Measured repetitions, 30..10000")
    parser.add_argument("--warmups", type=int, default=3, help="Untimed calls, 1..100")
    parser.add_argument("--replicates", type=int, default=10_000, help=f"Replicates per simulation, 1..{MAX_REPLICATES}")
    parser.add_argument("--seed", type=int, default=42, help=f"RNG seed, 0..{MAX_SEED}")
    parser.add_argument("--output", type=Path, help="Write the full JSON report instead of printing it")
    parser.add_argument("--profile", type=Path, help="Write cProfile stats for one additional untimed call")
    args = parser.parse_args(argv)
    if args.output is not None and args.profile is not None and args.output.resolve() == args.profile.resolve():
        parser.error("--output and --profile must use different paths")
    try:
        report = run_benchmark(scenario=args.scenario, runs=args.runs, warmups=args.warmups,
                               replicates=args.replicates, seed=args.seed, profile=args.profile)
        payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output is None:
            sys.stdout.write(payload)
        else:
            args.output.write_text(payload, encoding="utf-8")
    except (ValueError, StatisticalInputError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
