"""Path and seed setup for the quarantined teacher suite; mirrors tests/conftest.py."""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Repo root first so `deprecated.*` imports resolve; then the live trees the teacher rides.
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))
# Shared helpers live in the live tests/ tree (observation_helpers, fixtures); this dir carries
# the teacher-only helpers (bellman_helpers).
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("CGPY_SEED", "1178")

if os.environ.get("CG_ENGINE") == "py":
    from cgpy.alias import install
    install()
