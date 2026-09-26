#!/usr/bin/env bash
# Start the FastAPI backend (serves the Phase 1/2A/2B API).
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
