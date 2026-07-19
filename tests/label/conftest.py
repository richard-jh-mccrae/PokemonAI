"""Shared fixtures for the blunder-labeler suite (WP3, ADR-0053).

The labeler mines the corpus films the S1 generator writes, so the tests exercise it against a
**real** two-game corpus generated the same way (``sim.corpus.generate_corpus_run`` over the
``mega_starmie`` fixture agent — the exact path ``tests/sim/test_corpus`` proves). Corpus films carry
``search_begin_input`` on their frame obs (the design's central claim, re-verified live at build),
so vread/triage/expert all see the same films the real pipeline does — no synthetic obs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
SRC = [REPO / "src"]


@pytest.fixture(scope="session")
def corpus_films(tmp_path_factory):
    """A real 2-game mega_starmie mirror corpus (films under a session tmp dir). Session-scoped: the
    engine-driven generation runs once for the whole label suite."""
    from sim.corpus import generate_corpus_run

    out = tmp_path_factory.mktemp("label_corpus")
    run_dir = generate_corpus_run(
        run_id="label_fixture", created_at="2026-07-19T00:00:00", git_rev="fixture",
        agents=["mega_starmie"], agents_root=FIXTURE_AGENTS, out_root=out,
        agent_versions={"mega_starmie": "fixture"}, per_pairing=2, extra_syspath=SRC)
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
    """The real engine-backed mega_starmie Pilot (``tune._build_pilot`` — the same builder the tuner
    and every replay tool use)."""
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
