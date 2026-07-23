"""Eval harness (tools/sim/eval_spike, ADR-0053 WP2 design D4): duplicate-POSITION replay plumbing.
Opening extraction is pure film parsing (engine-free); the fork driver gets a live smoke test that
one playout from a real opening runs end-to-end via search_begin/search_step. This is plumbing +
smoke — NOT the variance-reduction verdict (that is corpus-gated)."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
MEGA = FIXTURE_AGENTS / "mega_starmie"
SRC = [REPO / "src"]


# ---- opening extraction (engine-free) --------------------------------------------------------

def _frame(context, type_, *, seed=True, option=True):
    obs = {"select": {"context": context, "type": type_,
                      "option": [{"index": 0}] if option else []},
           "current": {"yourIndex": 0}}
    if seed:
        obs["search_begin_input"] = "SEED"
    return {"obs": obs}


@pytest.mark.req("REQ-SIM-0023")
def test_opening_frames_keeps_only_plain_main_seedbearing():
    """Only plain-MAIN (context 0, type 0) frames WITH a fork seed AND options qualify as
    identical-position replay points — the only fork-deterministic class. Everything else (a
    non-MAIN select, a seedless frame, an optionless frame) is excluded."""
    from sim.eval_spike import opening_frames, first_opening
    replay = {"steps": [[{"visualize": [
        _frame(0, 0),                          # plain MAIN + seed + options -> KEEP
        _frame(1, 1),                          # non-MAIN select -> drop
        _frame(0, 0, seed=False),              # no fork seed -> drop
        _frame(0, 0, option=False),            # no options -> drop
    ]}]]}
    openings = opening_frames(replay)
    assert len(openings) == 1
    assert openings[0]["select"]["context"] == 0 and openings[0]["search_begin_input"] == "SEED"
    assert first_opening(replay) is openings[0]
    assert first_opening({"steps": []}) is None


# ---- fork driver (live smoke) ----------------------------------------------------------------

def _fixture_pilot():
    """A Pilot on the fixture mega_starmie deck (the deck the film below is played with), so the
    fork's own-zone seeding matches the recorded game."""
    from sim.battle import read_deck
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.pilot import Pilot
    from common.scouting.provider import EngineCardStatProvider
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    return Pilot(Strategy(), read_deck(MEGA), general_strategy=GENERAL_STRATEGY,
                 stats=EngineCardStatProvider(), functions=fns, effects=CardEffects.load(),
                 lethal_verify=True)


@pytest.fixture(scope="module")
def one_film():
    from sim.corpus import generate_corpus_run
    from meta_tracker.parse import load_replay
    import tempfile
    out = Path(tempfile.mkdtemp())
    run_dir = generate_corpus_run(
        run_id="spike", created_at="2026-07-19T00:00:00", git_rev="x", agents=["mega_starmie"],
        agents_root=FIXTURE_AGENTS, out_root=out, agent_versions={"mega_starmie": "x"},
        per_pairing=1, extra_syspath=SRC)
    return load_replay(sorted(run_dir.rglob("*.json.gz"))[0])


@pytest.mark.req("REQ-SIM-0023")
def test_a_real_film_yields_a_plain_main_opening(one_film):
    """A real game has at least one plain-MAIN, seed-bearing opening to fork from."""
    from sim.eval_spike import first_opening
    assert first_opening(one_film) is not None


@pytest.mark.req("REQ-SIM-0023")
def test_fork_playout_drives_a_position_to_terminal(one_film):
    """The driver forks from a real opening and drives the Pilot's policy to an engine verdict via
    search_begin/search_step — the position-replay plumbing runs end-to-end. (Plumbing, not a
    measurement: the playout's fork tiers are off and unrevealed order is reshuffled.)"""
    from sim.eval_spike import first_opening, fork_playout
    pilot = _fixture_pilot()
    out = fork_playout(pilot, first_opening(one_film), max_steps=400)
    assert out["error"] is None
    assert out["steps"] > 0
    assert out["terminal"] is True and out["result"] in (0, 1, None)


@pytest.mark.req("REQ-SIM-0023")
def test_fork_playout_is_a_noop_without_a_seed():
    """A seedless obs is a clean no-op (never a crash) — a spike must never take down the harness."""
    from sim.eval_spike import fork_playout
    out = fork_playout(_fixture_pilot(), {"current": {"yourIndex": 0}})
    assert out == {"steps": 0, "terminal": False, "result": None, "error": "no seed"}
