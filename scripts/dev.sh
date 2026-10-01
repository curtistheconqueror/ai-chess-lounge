#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Run 'make setup' first."
  exit 1
fi

.venv/bin/alembic upgrade head

cleanup() {
  kill "${api_pid:-}" "${web_pid:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

.venv/bin/uvicorn lounge_api.main:app \
  --app-dir services/api \
  --reload \
  --host 0.0.0.0 \
  --port 8000 &
api_pid=$!

(cd apps/web && npm run dev) &
web_pid=$!

echo "AI Chess Lounge: http://localhost:5173"
wait -n "$api_pid" "$web_pid"
