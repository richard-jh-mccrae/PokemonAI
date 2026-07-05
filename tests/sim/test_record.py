"""Tier-5 corpus recorder (grilled 2026-07-05): battle.py's process-isolated match loop, captured
into a cabt-`visualize`-shaped film the existing value extractor + blunder reader consume UNCHANGED —
the finish plan's "one corpus format across every replay tool" decision.
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
    """A recorded match emits a `visualize` film the shipped readers parse: `_film` returns the frames,
    `winner_index` reads the seat-0 win from rewards, and `iter_decisions` recovers each prompt's choice
    with the +1-offset obs — so the corpus is mineable by the exact tooling the selfplay corpus uses."""
    from sim.record import MatchRecorder
    from train.blunder.decisions import _film, iter_decisions
    from meta_tracker.parse import winner_index

    rec = MatchRecorder()
    rec.step(_obs(0, [{"a": 1}, {"a": 2}]), [1])     # seat 0 picks option 1 among two
    rec.step(_obs(1, [{"a": 3}]), [0])               # seat 1 picks the lone option
    rec.finish({"current": {"yourIndex": 0, "result": 0}, "select": None}, winner=0)

    replay = rec.replay(episode_id=42, team_names=["A#0", "B#1"])
    assert winner_index(replay) == 0                 # seat 0 won → rewards[0] > rewards[1]
    film = _film(replay)
    assert len(film) == 3                            # two prompts + the terminal frame
    decisions = iter_decisions(replay)
    assert [d.chosen for d in decisions] == [[1], [0]]   # each prompt's recorded choice, +1-offset
    assert [d.seat for d in decisions] == [0, 1]         # acting seat from the prompt frame
    assert all(d.obs is not None for d in decisions)     # obs present → Tuner/value mineable


@pytest.mark.req("REQ-SIM-0011")
def test_recorded_film_yields_value_feature_rows_through_the_real_extractor():
    """The recorded film is training-usable end-to-end: the SHIPPED value extractor
    (`train.value.extract.rows_from_replay`) mines a full-length feature vector per decision and labels
    it by the eventual winner — proving the gauntlet corpus feeds the Automatic Value Model with no new reader."""
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
    assert rows                                           # the real extractor produced rows
    feats, won = rows[-1]
    assert len(feats) == len(FEATURE_NAMES)              # a complete objective-feature vector
    assert won == 1.0                                     # the seat-0 board is labelled a win (winner=0)


@pytest.mark.req("REQ-SIM-0012")
def test_recorder_maps_winner_to_seat_indexed_rewards():
    """The win label is seat-indexed and honest: a seat-1 win reads back as winner 1, and a draw
    (``winner=None``) carries NO win label (equal rewards) so the extractor skips it — a flipped or
    fabricated label would silently poison the corpus."""
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
    """Threading a recorder through play_match's REAL engine loop captures a full mirror game whose film
    the value extractor mines into many labelled states — the corpus comes off the SAME loop the A/B
    already runs (process isolation, no in-process two-deck collision). No recorder → battle path
    unchanged (the existing REQ-SIM-0007 game test still passes)."""
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
    assert result.winner in (0, 1, None)                 # engine resolved a verdict
    replay = rec.replay(episode_id=1, team_names=["mega_starmie#0", "mega_starmie#1"])
    pilot, _ = _build_pilot("mega_starmie")
    rows = list(rows_from_replay(pilot, replay))
    assert len(rows) > 10                                # a real game yields many mineable states
