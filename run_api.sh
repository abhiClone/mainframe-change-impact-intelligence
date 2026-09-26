#!/usr/bin/env bash
# Start the Phase 1 FastAPI backend (serves the dependency/impact API).
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
