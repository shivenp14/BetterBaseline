#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
python_bin="${CAPTURE_PYTHON:-$repo_root/backend/.venv/bin/python}"
output="${CAPTURE_OUTPUT:-/tmp/betterbaseline-integration}"
mkdir -p "$output"
export PAGE_URL="${PAGE_URL:-http://localhost:3000}" API_URL="${API_URL:-http://127.0.0.1:8765}"
export CAPTURE_PYTHON="$python_bin" CAPTURE_OUTPUT="$output"
# Frontend must already be built with this API_URL and live mode.
PYTHONPATH="$repo_root/tests/integration/offline_guard:$repo_root/backend" ALLOWED_ORIGINS="$PAGE_URL" \
  "$python_bin" -m uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT:-8765}" > "$output/backend.log" 2>&1 &
api_pid=$!
(cd frontend && exec node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3000) > "$output/frontend.log" 2>&1 &
ui_pid=$!
trap 'kill "$api_pid" "$ui_pid" 2>/dev/null || true' EXIT
for i in {1..60}; do
  if ! kill -0 "$api_pid" "$ui_pid" 2>/dev/null; then
    cat "$output/backend.log" "$output/frontend.log" >&2
    exit 1
  fi
  if curl --silent --fail "$API_URL/healthz" >/dev/null && curl --silent --fail "$PAGE_URL" >/dev/null; then break; fi
  sleep 0.5
done
PYTHONPATH="$repo_root/tests/integration/offline_guard" "$python_bin" - <<'PY'
import socket
for address in [('1.1.1.1', 443), ('example.invalid', 443)]:
    try:
        with socket.socket() as probe:
            probe.connect(address)
    except OSError as error:
        assert 'offline guard' in str(error), error
    else:
        raise AssertionError('Backend egress guard failed')
PY
node tests/integration/capture_browser.mjs
