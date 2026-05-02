#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT/frontend"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}/health"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"

wait_for_url() {
  local url="$1"
  local attempts="$2"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  return 1
}

open_url() {
  local url="$1"

  if command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$url"
  elif command -v explorer.exe >/dev/null 2>&1; then
    explorer.exe "$url"
  else
    printf 'Open this URL in your browser: %s\n' "$url"
  fi
}

if [ ! -d "$FRONTEND" ]; then
  echo "Frontend directory not found: $FRONTEND" >&2
  exit 1
fi

echo "Starting Neraium backend on port ${BACKEND_PORT}..."
(cd "$ROOT" && python -m uvicorn api.main:app --port "$BACKEND_PORT") &
BACKEND_PID=$!

echo "Waiting for backend..."
if ! wait_for_url "$BACKEND_URL" 30; then
  echo "Backend did not become ready at $BACKEND_URL" >&2
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
  exit 1
fi

echo "Starting Neraium frontend on port ${FRONTEND_PORT}..."
(
  cd "$FRONTEND"
  if [ ! -d node_modules ]; then
    npm install
  fi
  npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

echo "Waiting for frontend..."
if ! wait_for_url "$FRONTEND_URL" 45; then
  echo "Frontend did not become ready at $FRONTEND_URL" >&2
  kill "$BACKEND_PID" "$FRONTEND_PID" >/dev/null 2>&1 || true
  exit 1
fi

open_url "$FRONTEND_URL"

echo
echo "Neraium is running:"
echo "  Backend:  http://127.0.0.1:${BACKEND_PORT}"
echo "  Frontend: ${FRONTEND_URL}"
echo
echo "Press Ctrl+C here to stop both services."

cleanup() {
  echo
  echo "Stopping Neraium..."
  kill "$BACKEND_PID" "$FRONTEND_PID" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM
wait
