"""Run both measured validators against a fresh local backend, then stop it."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "backend"], cwd=ROOT, text=True)
    if dirty:
        parser.error("Backend must match its recorded clean checkout")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    base = f"http://127.0.0.1:{port}"
    with (output / "backend.log").open("w") as log:
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                   "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 20
            while True:
                if server.poll() is not None:
                    raise RuntimeError(f"Backend exited; see {output / 'backend.log'}")
                try:
                    with urlopen(base + "/healthz", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("Local backend did not become healthy")
                time.sleep(.1)
            for filename, extra, report in (
                ("validate_analytic_http.py", ["--base-url", base, "--engine-commit", commit], "analytic.json"),
                ("validate_simulation.py", [], "simulation.json"),
            ):
                with (output / (filename + ".log")).open("w") as validator_log:
                    subprocess.run([sys.executable, str(ROOT / "scripts/validation" / filename), *extra,
                                    "--output", str(output / report)], cwd=ROOT, env=env,
                                   stdout=validator_log, stderr=validator_log, check=True)
            analytic = json.loads((output / "analytic.json").read_text())
            simulation = json.loads((output / "simulation.json").read_text())
            print(json.dumps({"status": "pass", "checkout_commit": commit,
                              "analytic_designs": analytic["design_cases"], "stress_cases": analytic["stress_cases"],
                              "simulation_runs": len(simulation["runs"]), "evidence_directory": str(output)}))
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
