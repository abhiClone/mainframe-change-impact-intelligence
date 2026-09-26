#!/usr/bin/env bash
# Run the backend test suite (166 tests: Phase 1 + 2A + 2B + audit-remediation regressions).
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python -m pytest backend/tests/ -v
