#!/usr/bin/env bash
set -euo pipefail

# Core CI intentionally has no services, credentials, or secrets. The #78 E2E
# and #79 integration workflows own browser and service-backed checks.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
backend_dir="$repo_root/backend"
python_bin="${PYTHON:-python}"

if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Required Python interpreter '$python_bin' was not found." >&2
  exit 127
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "Required uv executable was not found." >&2
  exit 127
fi

python_version="$($python_bin -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$python_version" != "3.12" ]]; then
  echo "Core CI requires Python 3.12; '$python_bin' reports $python_version." >&2
  exit 2
fi

cd "$backend_dir"
if [[ ! -f uv.lock ]]; then
  echo "backend/uv.lock is required for core CI; integrate #64 before enabling this check." >&2
  exit 1
fi

# Install the backend and dev extra only from the committed lock. pytest
# discovers every module under tests/, so new mandatory tests are included.
uv sync --locked --python "$python_bin" --extra dev
uv run --locked --python "$python_bin" pytest -q
