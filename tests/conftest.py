import os
import sys
from pathlib import Path

import pytest

# Make meta_tracker package importable without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# Keep tests/ itself on path so shared helpers and `from conftest import ...` resolve from any
# per-subsystem subdir.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# cgpy is deliberately UNSEEDED by default; a suite wants the opposite. `game.py` re-reads the var
# per `battle_start`, so this covers every call whatever the import order, and `setdefault` yields.
os.environ.setdefault("CGPY_SEED", "1178")             # 178 = the issue that earned this line

if os.environ.get("CG_ENGINE") == "py":                # ADR-0050 M3: run the suite on the
    from cgpy.alias import install                     # cgpy twin instead of the DLL
    install()

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def on_cgpy_twin() -> bool:
    """True when the suite is running against the cgpy twin (``CG_ENGINE=py``)."""
    try:
        from cgpy.alias import installed
    except Exception:                                  # cgpy absent: the native arm, by definition
        return False
    return installed()


#: A PARITY marker, not a native-only one: cgpy cannot reseed an arbitrary mid-battle board, so it
#: answers None there. Delete this when the twin grows live-board reseeding; never weaken the assert.
needs_live_board_search = pytest.mark.skipif(
    on_cgpy_twin(),
    reason="asserts a live-board search round-trip; cgpy cannot reseed an arbitrary live board")


def require_kaggle_environments():
    """Drop-in for ``pytest.importorskip("kaggle_environments")`` that routes the FIRST import
    through check_agent's muter, so the one-time OpenSpiel env dump never reaches the console."""
    import pytest

    from sim.check_agent import _import_make  # cheap: ke is imported lazily inside it
    try:
        _import_make()
    except ImportError:
        pytest.skip("kaggle_environments not installed")


def pytest_configure(config):
    config.addinivalue_line("markers", "req(id): trace a test to a requirement ID")
