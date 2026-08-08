"""Tier-5 corpus recorder: battle.py's match loop captured into a cabt-`visualize`-shaped film the
existing value extractor + blunder reader consume UNCHANGED — one corpus format across every tool.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
MEGA = FIXTURE_AGENTS / "mega_starmie"
SRC = [REPO / "src"]                                     # source fixture isn't self-contained


def _obs(seat, options, turn=1):
    return {"current": {"yourIndex": seat, "turn": turn},
            "select": {"context": 0, "type": 0, "option": options}}


def _board_obs(seat, *, result=None):
    """A minimally-complete agent obs `_board` can read (two Actives, six hidden prizes each)."""
    players = [{"active": [{"id": 666, "hp": 210, "energies": []}], "bench": [], "hand": [],
                "prize": [None] * 6},
               {"active": [{"id": 678, "hp": 440, "energies": []}], "bench": [], "hand": [],
                "prize": [None] * 6}]
    cur = {"yourIndex": seat, "turn": 6, "players": players}
    if result is not None:
        cur["result"] = result
    select = None if result is not None else {"context": 0, "type": 0, "option": [{"a": 1}, {"a": 2}]}
    return {"current": cur, "select": select}


@pytest.mark.req("REQ-SIM-0010")
def test_recorder_film_round_trips_through_the_film_readers():
    from sim.record import MatchRecorder
    from train.blunder.decisions import _film, iter_decisions
    from meta_tracker.parse import winner_index

    rec = MatchRecorder()
    rec.step(_obs(0, [{"a": 1}, {"a": 2}]), [1])
    rec.step(_obs(1, [{"a": 3}]), [0])
    rec.finish({"current": {"yourIndex": 0, "result": 0}, "select": None}, winner=0)

    replay = rec.replay(episode_id=42, team_names=["A#0", "B#1"])
    assert winner_index(replay) == 0
    film = _film(replay)
    assert len(film) == 3                            # two prompts + the terminal frame
    decisions = iter_decisions(replay)
    assert [d.chosen for d in decisions] == [[1], [0]]   # +1-offset
    assert [d.seat for d in decisions] == [0, 1]
    assert all(d.obs is not None for d in decisions)     # obs present -> Tuner/value mineable


@pytest.mark.req("REQ-SIM-0011")
def test_recorded_film_yields_value_feature_rows_through_the_real_extractor():
    """The SHIPPED extractor, so the gauntlet corpus needs no new reader."""
    from sim.record import MatchRecorder
    from train.value.extract import rows_from_replay
    from train.tune import _build_pilot
    from common.value.features import FEATURE_NAMES

    pilot, _ = _build_pilot("mega_starmie")
    rec = MatchRecorder()
    rec.step(_board_obs(0), [1])                          # decision frame 0 → +1 obs = seat-1 board
    rec.step(_board_obs(1), [0])                          # decision frame 1 → +1 obs = terminal board
    rec.finish(_board_obs(0, result=0), winner=0)
    replay = rec.replay(episode_id=7, team_names=["A#0", "B#1"])

    rows = list(rows_from_replay(pilot, replay))
    assert rows
    feats, won = rows[-1]
    assert len(feats) == len(FEATURE_NAMES)
    assert won == 1.0                                     # seat-0 board, winner=0


@pytest.mark.req("REQ-SIM-0012")
def test_recorder_maps_winner_to_seat_indexed_rewards():
    """A draw carries NO win label (equal rewards) so the extractor skips it rather than guessing."""
    from sim.record import MatchRecorder
    from meta_tracker.parse import winner_index

    r1 = MatchRecorder()
    r1.step(_obs(0, [{"a": 1}]), [0])
    r1.finish({"current": {"result": 1}, "select": None}, winner=1)
    assert winner_index(r1.replay(episode_id=1, team_names=["a", "b"])) == 1

    draw = MatchRecorder()
    draw.step(_obs(0, [{"a": 1}]), [0])
    draw.finish({"current": {}, "select": None}, winner=None)
    assert winner_index(draw.replay(episode_id=2, team_names=["a", "b"])) is None   # no label on a draw


@pytest.mark.req("REQ-SIM-0013")
def test_play_match_with_a_recorder_yields_a_mineable_film():
    """The corpus comes off the SAME loop the A/B runs — process isolation, no two-deck collision."""
    from sim.battle import AgentServer, play_match, read_deck
    from sim.record import MatchRecorder
    from train.value.extract import rows_from_replay
    from train.tune import _build_pilot

    deck = read_deck(MEGA)
    rec = MatchRecorder()
    a, b = AgentServer(MEGA, SRC), AgentServer(MEGA, SRC)
    try:
        result = play_match(a, b, deck, deck, recorder=rec)
    finally:
        a.close()
        b.close()
    assert result.winner in (0, 1, None)
    replay = rec.replay(episode_id=1, team_names=["mega_starmie#0", "mega_starmie#1"])
    pilot, _ = _build_pilot("mega_starmie")
    rows = list(rows_from_replay(pilot, replay))
    assert len(rows) > 10
