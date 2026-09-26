#!/usr/bin/env bash
# Run the Phase 1 backend test suite.
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python -m pytest backend/tests/ -v
