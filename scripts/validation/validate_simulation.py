"""Measured primitive-level calibration; independent scalar rejection oracle.

The shipped primitive supports equal true rates. Production effect validation is
unchanged. NumPy is used ONLY to replay the documented PCG64 draw stream; pooled
test decisions, exact small-trial distributions and uncertainty use stdlib math.
"""
import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

SEEDS = (42, 31415, 27182)
BATCHES = (25_000, 100_000)
CASES = (
    {"name": "regular_null", "n": 5000, "pc": .2, "pt": .2, "dropout": 0., "alpha": .05},
    {"name": "dropout_null", "n": 5000, "pc": .2, "pt": .2, "dropout": .25, "alpha": .01},
    {"name": "baseline_collapse", "n": 903, "pc": .1, "pt": .075, "dropout": 0., "alpha": .05},
    {"name": "rare_null", "n": 10, "pc": .01, "pt": .01, "dropout": 0., "alpha": .05},
    {"name": "empty_arm_null", "n": 1, "pc": .2, "pt": .2, "dropout": .9, "alpha": .05},
)


def decision(nc, nt, xc, xt, alpha):
    """Integer cross-product form of the pooled-z test, with stdlib tails."""
    total = nc + nt
    events = xc + xt
    if nc == 0 or nt == 0 or events == 0 or events == total:
        return False, False, True
    z = (xt * nc - xc * nt) * math.sqrt(total / (nc * nt * events * (total - events)))
    significant = math.erfc(abs(z) / math.sqrt(2)) < alpha
    return significant, significant and z < 0, False


def exact_distribution(case):
    """Enumerate independent retained/event counts, including zero variance."""
    n, dropout = case["n"], case["dropout"]
    def arm(p):
        return [(r, x, math.comb(n, r) * (1-dropout)**r * dropout**(n-r)
                 * math.comb(r, x) * p**x * (1-p)**(r-x))
                for r in range(n+1) for x in range(r+1)]
    sums = [0., 0., 0.]
    mass = 0.
    for nc, xc, wc in arm(case["pc"]):
        for nt, xt, wt in arm(case["pt"]):
            weight = wc * wt
            mass += weight
            for i, flag in enumerate(decision(nc, nt, xc, xt, case["alpha"])):
                sums[i] += weight * flag
    if abs(mass - 1) > 1e-12:
        raise AssertionError("Exact distribution probability mass")
    return dict(zip(("two_sided", "favorable", "invalid"), sums))


def replay(case, reps, seed):
    # Shared RNG lineage is intentional: this checks decisions/aggregation, NOT
    # independently validates NumPy's binomial sampler or random-number quality.
    import numpy as np
    rng = np.random.Generator(np.random.PCG64(seed))
    nc = rng.binomial(case["n"], 1-case["dropout"], size=reps)
    nt = rng.binomial(case["n"], 1-case["dropout"], size=reps)
    xc = rng.binomial(nc, case["pc"])
    xt = rng.binomial(nt, case["pt"])
    counts = [0, 0, 0]
    for row in zip(nc, nt, xc, xt):
        # Python ints prevent NumPy int overflow in cross-products.
        for i, flag in enumerate(decision(*(int(v) for v in row), case["alpha"])):
            counts[i] += flag
    return dict(zip(("two_sided", "favorable", "invalid"), counts))


def wilson(successes, trials, z=5.):
    p = successes / trials
    denominator = 1 + z*z/trials
    center = (p + z*z/(2*trials)) / denominator
    radius = z * math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials)) / denominator
    return [max(0., center-radius), min(1., center+radius)]


def measure():
    from app.statistics.simulation import simulate_binary
    rows = []
    for case in CASES:
        exact = exact_distribution(case) if case["n"] <= 10 else None
        for reps in BATCHES:
            for seed in SEEDS:
                args = dict(n_c=case["n"], n_t=case["n"], p_c=case["pc"], p_t=case["pt"],
                            d_c=case["dropout"], d_t=case["dropout"], alpha=case["alpha"], reps=reps, seed=seed)
                actual = simulate_binary(**args)
                if actual != simulate_binary(**args):
                    raise AssertionError("Same seed/batch not repeatable")
                counts = replay(case, reps, seed)
                for label, field in (("two_sided", "significant_two_sided_fraction"),
                                     ("favorable", "significant_favorable_fraction"),
                                     ("invalid", "invalid_test_fraction")):
                    if actual[field] != counts[label]/reps:
                        raise AssertionError(f"Scalar rejection/denominator mismatch: {case['name']} {label}")
                for label in ("two_sided", "favorable"):
                    p = counts[label]/reps
                    if abs(actual["mcse_"+label] - math.sqrt(p*(1-p)/reps)) > 1e-15:
                        raise AssertionError("Separate MCSE mismatch")
                if actual["invalid_test_policy"] != "nonrejection_over_all_replicates":
                    raise AssertionError("Invalid test policy mismatch")
                rows.append({"case": case, "request": args, "result": actual, "oracle_counts": counts,
                             "wilson_5sigma": {k: wilson(v, reps) for k, v in counts.items()}, "exact": exact})
    summary = []
    for case in CASES:
        for reps in BATCHES:
            selected = [r for r in rows if r["case"] == case and r["request"]["reps"] == reps]
            total = reps * len(SEEDS)
            counts = {k: sum(r["oracle_counts"][k] for r in selected) for k in ("two_sided", "favorable", "invalid")}
            intervals = {k: wilson(v, total) for k, v in counts.items()}
            exact = selected[0]["exact"]
            reference = exact or ({"two_sided": case["alpha"], "favorable": case["alpha"]/2}
                                 if case["pc"] == case["pt"] else {})
            # Prespecified 5-sigma Wilson interval, aggregated across three
            # seeds. Sparse cases compare exact finite-N size, not nominal alpha.
            for label, expected in reference.items():
                lo, hi = intervals[label]
                if not lo-1e-15 <= expected <= hi+1e-15:
                    raise AssertionError(f"Calibration disagreement: {case['name']} {label} {expected} outside {lo, hi}")
            summary.append({"name": case["name"], "reps_per_seed": reps, "total_replicates": total,
                            "fractions": {k: v/total for k, v in counts.items()}, "wilson_5sigma": intervals,
                            "reference": reference})
    scaling = []
    for case in CASES[:3]:
        for label in ("two_sided", "favorable"):
            small, large = [s for s in summary if s["name"] == case["name"]]
            def se(s):
                p = s["fractions"][label]
                return math.sqrt(p*(1-p)/s["total_replicates"])
            ratio = se(large)/se(small)
            if not .45 <= ratio <= .55:
                raise AssertionError("MCSE scaling outside prespecified .45–.55 interval")
            scaling.append({"name": case["name"], "fraction": label, "mcse_ratio_4x_replicates": ratio,
                            "small_mcse": se(small), "large_mcse": se(large)})
    return rows, summary, scaling


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "backend"], cwd=ROOT, text=True)
    if dirty:
        parser.error("Backend source must match the recorded clean checkout")
    source = ROOT / "backend/app/statistics/simulation.py"
    rows, summary, scaling = measure()
    report = {"status": "pass", "captured_at": datetime.now(timezone.utc).isoformat(), "checkout_commit": commit,
              "simulation_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "command": ["python", "scripts/validation/validate_simulation.py", "--output", str(args.output)],
              "prespecified": {"cases": CASES, "seeds": SEEDS, "batches": BATCHES,
                               "calibration": "5-sigma Wilson interval aggregated across seeds; sparse exact distribution",
                               "mcse_scaling_ratio": [.45, .55]},
              "limitations": ["Primitive-level evidence, not HTTP or UI acceptance.",
                              "Replay shares NumPy PCG64/binomial sampling; scalar test and exact distribution are independent.",
                              "Null approximation checks apply only to the prespecified well-populated regimes.",
                              "MCSE is simulation-estimate uncertainty, not reduced clinical-trial variance.",
                              "No clinical utility, predictive accuracy or historical trial rescue claim."],
              "summary": summary, "mcse_scaling": scaling, "runs": rows}
    # Write evidence only after every check succeeds. Historical reports are immutable.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": "pass", "runs": len(rows), "summary": summary, "mcse_scaling": scaling}))


if __name__ == "__main__":
    main()
