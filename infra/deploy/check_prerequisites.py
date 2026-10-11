"""Fail early on missing deployment handoffs; no fixture success fallback."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ("backend/pyproject.toml", "backend/uv.lock", "backend/app/main.py", "backend/app/settings.py",
            "frontend/package-lock.json")


def check(root=ROOT):
    problems = [f"Missing {path} (#64/#68 handoff required)" for path in REQUIRED
                if not (root / path).is_file()]
    api = root / "frontend/lib/api.ts"
    if not api.is_file() or "fetch(" not in api.read_text():
        problems.append("Frontend API adapter has no fetch boundary (#76 required); fixtures cannot verify live deployment")
    return problems


if __name__ == "__main__":
    problems = check()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(1)
    print("Source prerequisites present. Run real container/browser/offline checks; this is not acceptance.")
