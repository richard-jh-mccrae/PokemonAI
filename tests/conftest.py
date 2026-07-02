import sys
from pathlib import Path

# Make meta_tracker package importable without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# Tests live in per-subsystem subdirs (tests/<subsystem>/); keep tests/ itself on path
# so shared helpers (pilot_helpers, scouting_helpers) and `from conftest import ...` resolve
# from any subdir.
sys.path.insert(0, str(Path(__file__).resolve().parent))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def require_kaggle_environments():
    """Quietly import kaggle_environments, or skip the test if it isn't installed.

    Drop-in for ``pytest.importorskip("kaggle_environments")`` that routes the *first*
    import through check_agent's muter, so the library's one-time OpenSpiel env-discovery
    dump (native stderr writes + INFO logs) never reaches the console. Later calls are
    cached no-ops.
    """
    import pytest

    from sim.check_agent import _import_make  # cheap: ke is imported lazily inside it
    try:
        _import_make()
    except ImportError:
        pytest.skip("kaggle_environments not installed")


def pytest_configure(config):
    config.addinivalue_line("markers", "req(id): trace a test to a requirement ID")
