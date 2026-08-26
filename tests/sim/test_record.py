"""Corpus recorder: battle.py matches captured as correction-readable films."""
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


def test_recorder_keeps_legal_observations_but_uses_god_state_for_the_visual_board():
    from sim.record import MatchRecorder

    obs = _board_obs(1)
    terminal = _board_obs(0, result=0)
    god_players = [
        {"hand": [{"id": 1}], "prize": [{"id": 2}]},
        {"hand": [{"id": 3}], "prize": [{"id": 4}]},
    ]
    visualizer = [
        {"current": {"yourIndex": 0, "players": god_players}, "logs": [{"type": "Draw"}]},
        {"current": {"yourIndex": 0, "players": god_players}, "logs": []},
    ]
    recorder = MatchRecorder()
    recorder.step(obs, [0])
    recorder.finish(terminal, winner=0, visualizer=visualizer)

    film = recorder.replay(episode_id=1, team_names=["a", "b"])["steps"][0][0]["visualize"]

    assert film[0]["obs"] is obs
    assert film[0]["obs"]["current"]["players"][0]["prize"] == [None] * 6
    assert film[0]["current"]["players"] == god_players
    assert film[0]["current"]["yourIndex"] == 1
    assert film[0]["logs"] == [{"type": "Draw"}]


@pytest.mark.req("REQ-SIM-0013")
def test_play_match_with_a_recorder_yields_a_mineable_film():
    """The corpus comes off the SAME loop the A/B runs — process isolation, no two-deck collision."""
    from sim.battle import AgentServer, play_match, read_deck
    from sim.record import MatchRecorder
    from train.blunder.decisions import iter_decisions

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
    decisions = iter_decisions(replay)
    assert len(decisions) > 10 and all(decision.obs is not None for decision in decisions)
    film = replay["steps"][0][0]["visualize"]
    assert all(isinstance(player.get("hand"), list)
               for frame in film for player in frame["current"]["players"])
    assert all(all(isinstance(card, dict) for card in player.get("prize") or [])
               for frame in film for player in frame["current"]["players"])
