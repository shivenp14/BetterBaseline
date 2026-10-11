#!/usr/bin/env bash
set -euo pipefail

frontend_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(cd "$frontend_dir/.." && pwd)"
backend_dir="$repo_root/backend"
tmp_dir="$(mktemp -d)"
server_pid=""
cleanup() {
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

command -v uv >/dev/null || { echo "uv is required; install it and retry." >&2; exit 127; }
cd "$backend_dir"
export UV_CACHE_DIR="$tmp_dir/uv-cache"
uv sync --locked --extra dev
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
uv run --locked --extra dev python -m uvicorn app.main:app --host 127.0.0.1 --port "$port" >"$tmp_dir/uvicorn.log" 2>&1 &
server_pid=$!
for attempt in $(seq 1 50); do
  if curl --silent --fail "http://127.0.0.1:$port/healthz" >/dev/null; then break; fi
  if ! kill -0 "$server_pid" 2>/dev/null; then cat "$tmp_dir/uvicorn.log" >&2; exit 1; fi
  sleep 0.2
done
curl --silent --fail "http://127.0.0.1:$port/healthz" >/dev/null || { cat "$tmp_dir/uvicorn.log" >&2; exit 1; }

cd "$frontend_dir"
./node_modules/.bin/tsc --strict --target ES2020 --module commonjs --moduleResolution node \
  --esModuleInterop --skipLibCheck --rootDir . --outDir "$tmp_dir/compiled" \
  lib/api.ts lib/workspace-state.ts tests/backend-integration.test.ts tests/api-adapter.test.ts
NEXT_PUBLIC_API_MODE=live NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$port" node "$tmp_dir/compiled/tests/backend-integration.test.js"
NEXT_PUBLIC_API_MODE=live NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$port" node "$tmp_dir/compiled/tests/api-adapter.test.js"
