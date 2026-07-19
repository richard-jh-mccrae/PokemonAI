import os
import sys
from pathlib import Path

import pytest

# Make meta_tracker package importable without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# Tests live in per-subsystem subdirs (tests/<subsystem>/); keep tests/ itself on path
# so shared helpers (pilot_helpers, scouting_helpers) and `from conftest import ...` resolve
# from any subdir.
sys.path.insert(0, str(Path(__file__).resolve().parent))

if os.environ.get("CG_ENGINE") == "py":                # ADR-0050 M3: run the suite on the
    from cgpy.alias import install                     # cgpy twin instead of the DLL
    install()

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


# --- Blunder-labeler fixtures (WP3, tests/label/) ---------------------------------------------
# These live here, not in a tests/label/conftest.py, because the suite uses a single global
# `conftest` module (`from conftest import ...` resolves the root one via the sys.path entry above);
# a sibling conftest.py of the same basename shadows it and breaks that import in other subdirs.
# Session-scoped, so the engine-driven corpus generation runs once and only when a label test asks.

_FIXTURE_AGENTS = FIXTURES / "agents"
_SRC = [Path(__file__).resolve().parents[1] / "src"]


@pytest.fixture(scope="session")
def corpus_films(tmp_path_factory):
    """A real 2-game mega_starmie mirror corpus (films under a session tmp dir). Corpus films carry
    ``search_begin_input`` on their frame obs, so the labeler sees the same films the real pipeline
    does (no synthetic obs). Session-scoped: generated once for the whole label suite."""
    from sim.corpus import generate_corpus_run

    out = tmp_path_factory.mktemp("label_corpus")
    run_dir = generate_corpus_run(
        run_id="label_fixture", created_at="2026-07-19T00:00:00", git_rev="fixture",
        agents=["mega_starmie"], agents_root=_FIXTURE_AGENTS, out_root=out,
        agent_versions={"mega_starmie": "fixture"}, per_pairing=2, extra_syspath=_SRC)
    films = sorted(run_dir.rglob("*.json.gz"))
    assert films, "corpus generation produced no films"
    return films


@pytest.fixture(scope="session")
def one_replay(corpus_films):
    """The first corpus film, loaded (``.json.gz`` read transparently)."""
    from meta_tracker.parse import load_replay

    return load_replay(corpus_films[0])


@pytest.fixture(scope="session")
def ms_pilot():
    """The real engine-backed mega_starmie Pilot (``tune._build_pilot`` — the shared builder the
    tuner and every replay tool use)."""
    from train.tune import _build_pilot

    pilot, _ = _build_pilot("mega_starmie")
    return pilot


@pytest.fixture(scope="session")
def seed_model():
    """The committed seed value model (present, non-null)."""
    from common.value.model import ValueModel

    m = ValueModel.load()
    assert m.present, "committed seed value_model.json should be present"
    return m
