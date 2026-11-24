#!/usr/bin/env bash
# Run Tello Mission Control without Docker (macOS / Linux).
#
#   ./start.sh          install what's missing, build the web UI, start the app
#   ./start.sh --mock   same, but always with the pretend drone
#
# Then open http://localhost:8000 (or the port set by TELLO_API_PORT in .env).
# Run it once on your normal Wi-Fi first: the drone's Wi-Fi has no internet,
# so nothing can be downloaded once you have joined it.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { cp .env.template .env; echo "Created .env from the template (pretend drone is on)."; }

# --- backend: Python 3.12 or 3.13 in backend/.venv -------------------------
if [ ! -x backend/.venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 backend/.venv
  else
    PY=""
    for c in python3.12 python3.13 python3; do
      if command -v "$c" >/dev/null 2>&1 &&
         "$c" -c 'import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,13) else 1)'; then
        PY="$c"; break
      fi
    done
    [ -n "$PY" ] || { echo "Need Python 3.12 or 3.13 (or install uv: https://docs.astral.sh/uv/)." >&2; exit 1; }
    "$PY" -m venv backend/.venv
  fi
fi
if [ ! -f backend/.venv/.installed ] || [ backend/requirements.txt -nt backend/.venv/.installed ]; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python backend/.venv/bin/python -r backend/requirements.txt
  else
    backend/.venv/bin/python -m pip install -r backend/requirements.txt
  fi
  touch backend/.venv/.installed
fi

# --- web UI: built once, rebuilt when the source changes -------------------
if [ ! -f frontend/dist/index.html ] ||
   [ -n "$(find frontend/src frontend/index.html frontend/package.json -newer frontend/dist/index.html -print -quit)" ]; then
  command -v npm >/dev/null 2>&1 || { echo "Need Node.js 20 or newer (https://nodejs.org)." >&2; exit 1; }
  (cd frontend && npm ci && npm run build)
fi

# --- run -------------------------------------------------------------------
[ "${1:-}" = "--mock" ] && export TELLO_USE_MOCK_DRONE=true
PORT="${TELLO_API_PORT:-$(sed -n 's/^TELLO_API_PORT=//p' .env | tail -1)}"
PORT="${PORT:-8000}"
echo
echo "  Open http://localhost:${PORT}   (Ctrl+C to stop)"
echo
# Run from the repo root so photos, sequences and the flight log land in ./data,
# the same folder Docker uses.
exec backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend \
  --host 0.0.0.0 --port "$PORT" --env-file .env
