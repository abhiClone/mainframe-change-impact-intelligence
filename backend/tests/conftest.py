"""Ensure the project root is importable so tests can use `backend.*`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
