"""Pytest setup: make the backend importable and keep tests away from your real takeovers.db."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["MINI_AKTORIA_DB"] = str(Path(tempfile.mkdtemp()) / "test_takeovers.db")
