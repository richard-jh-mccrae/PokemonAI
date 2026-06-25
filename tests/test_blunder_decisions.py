"""Replay -> Decision extraction for the blunder inspector.

Decisions come from the full-information ``visualize`` film (both hands visible),
not the per-seat agent Observation (which hides the opponent).
"""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.decisions import iter_decisions

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def test_iter_decisions_yields_taggable_decisions_from_film():
    """REQ-BLUNDER-0001: each option-decision with a recorded choice becomes a
    Decision carrying seat, turn, the select context, and the chosen option(s)."""
    decisions = iter_decisions(load_replay(FIXTURE))

    # 42 frames present a select with options *and* a recorded choice; the
    # coin-flip / deck-submission frame (no ``selected``) is not a Decision.
    assert len(decisions) == 43

    first = decisions[0]
    assert first.seat == 0               # current.yourIndex (the acting player)
    assert first.turn == 0
    assert first.select_context == "IsFirst"
    assert first.chosen == [0]           # selection read from the NEXT film frame (offset +1)


def test_decision_embeds_selfcontained_full_info_snapshot():
    """REQ-BLUNDER-0002: a Decision embeds the legal options and an *independent*
    full-information snapshot -- both hands visible, decoupled from the source
    replay so the record survives replay mutation/deletion (the 'embed' guarantee)."""
    replay = load_replay(FIXTURE)
    main = next(d for d in iter_decisions(replay) if d.select_context == "Main")

    # full-information snapshot: both seats present, both hands visible
    players = main.current["players"]
    assert len(players) == 2
    assert all(len(p["hand"]) == 7 for p in players)

    # the Main decision exposes the real legal move set
    assert {o["type"] for o in main.options} >= {"Play", "End"}

    # snapshot is independent of the source replay: mutating the film must NOT
    # change an already-extracted Decision.
    captured = main.current["turn"]
    replay["steps"][0][0]["visualize"][main.frame]["current"]["turn"] = 999
    assert main.current["turn"] == captured
