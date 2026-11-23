#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  Starting MediaFlow Web Application"
echo "========================================"

# Detect Python binary
if [ -f ".venv/bin/python" ]; then
    PY_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
else
    PY_BIN="python"
fi

PORT="${1:-8000}"

# Try to open default browser if desktop display is available
if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    if command -v xdg-open >/dev/null 2>&1; then
        (sleep 1 && xdg-open "http://localhost:${PORT}") >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then
        (sleep 1 && open "http://localhost:${PORT}") >/dev/null 2>&1 &
    fi
fi

exec "$PY_BIN" server.py "$PORT"
