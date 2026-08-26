"""Replay -> Decision extraction for the blunder inspector.

Decisions come from the full-information ``visualize`` film (both hands visible),
not the per-seat agent Observation (which hides the opponent).
"""
import pytest
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.decisions import iter_decisions
from train.blunder.service import (
    decisions_payload, frame_details_payload, frames_index_payload, frames_payload,
)
from train.blunder.shell import _SHELL_HTML

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _timed_replay():
    def prompt(seat, remaining):
        return {
            "current": {"yourIndex": seat, "turn": 1},
            "select": {"context": "Main", "type": "Main", "option": [{"type": "End"}]},
            "selected": [0], "obs": {"remainingOverageTime": remaining},
        }

    film = [
        {"current": {"yourIndex": 0, "turn": 1},
         "select": {"context": "Main", "type": "Main", "option": [{"type": "End"}]}},
        prompt(1, 10.0), prompt(0, 20.0), prompt(1, 7.5),
        {"selected": [0], "obs": {"remainingOverageTime": 18.0}},
    ]
    return {
        "info": {"EpisodeId": 1},
        "steps": [
            [{"visualize": film}, {}],
            [{"observation": {"remainingOverageTime": 6.0}},
             {"observation": {"remainingOverageTime": 17.25}}],
        ],
    }


def test_iter_decisions_yields_taggable_decisions_from_film():
    """REQ-BLUNDER-0001: each option-decision with a recorded choice becomes a
    Decision carrying seat, turn, the select context, and the chosen option(s)."""
    decisions = iter_decisions(load_replay(FIXTURE))

    # 42 frames present a select with options *and* a recorded choice; the
    # coin-flip / deck-submission frame (no ``selected``) is not a Decision.
    assert len(decisions) == 43

    first = decisions[0]
    assert first.seat == 0               # current.yourIndex (acting player)
    assert first.turn == 0
    assert first.select_context == "IsFirst"
    assert first.chosen == [0]           # selection read from NEXT film frame (offset +1)


def test_decision_embeds_selfcontained_full_info_snapshot():
    """Both hands visible, decoupled from the source replay so the record survives replay
    mutation/deletion."""
    replay = load_replay(FIXTURE)
    main = next(d for d in iter_decisions(replay) if d.select_context == "Main")

    # full-information snapshot: both seats present, both hands visible
    players = main.current["players"]
    assert len(players) == 2
    assert all(len(p["hand"]) == 7 for p in players)

    # Main decision exposes the real legal move set
    assert {o["type"] for o in main.options} >= {"Play", "End"}

    # snapshot independent of source replay: mutating film must NOT
    # change an already-extracted Decision.
    captured = main.current["turn"]
    replay["steps"][0][0]["visualize"][main.frame]["current"]["turn"] = 999
    assert main.current["turn"] == captured


def test_decision_carries_pilot_ready_obs_aligned_to_its_options():
    """The obs carries runtime-ready int enums; the film records it one frame AFTER the
    prompt, like `selected`."""
    main = next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == "Main")
    assert main.obs is not None
    assert isinstance(main.obs["select"]["type"], int)                  # runtime-ready enum
    assert len(main.obs["select"]["option"]) == len(main.options)       # aligned to Decision
    assert all(0 <= c < len(main.obs["select"]["option"]) for c in main.chosen)


def test_decision_time_uses_the_next_same_seat_clock_and_terminal_state():
    replay = _timed_replay()
    decisions = iter_decisions(replay)

    assert [decision.decision_seconds for decision in decisions] == pytest.approx(
        [2.5, 2.0, 1.5, 0.75])
    assert decisions[-1].snapshot()["decision_seconds"] == pytest.approx(0.75)


def test_decision_time_reaches_both_shell_payloads_and_visible_ui():
    replay = _timed_replay()

    listed = decisions_payload(replay)["decisions"]
    frames = frames_payload(replay)["frames"]

    assert listed[0]["decision_seconds"] == pytest.approx(2.5)
    assert frames[0]["decision_seconds"] == pytest.approx(2.5)
    assert frames[-1]["decision_seconds"] is None
    assert "decision time" in _SHELL_HTML
    assert "decision_seconds" in _SHELL_HTML


def test_frames_use_full_decision_telemetry_for_both_selfplay_seats():
    replay = _timed_replay()
    live_by_seat = {
        0: [
            {"bellman": True, "chosen": [0], "diagnostics": {}},
            {"bellman": True, "chosen": [0], "decision_seconds": 0.456},
        ],
        1: [
            {"bellman": True, "chosen": [0], "decision_seconds": 0.234},
            {"bellman": True, "chosen": [0], "decision_seconds": 0.567},
        ],
    }

    frames = frames_payload(replay, live_records_by_seat=live_by_seat)["frames"]

    assert [frame["decision_seconds"] for frame in frames] == pytest.approx(
        [2.5, 0.234, 0.456, 0.567, None])


def test_frames_and_shell_show_strategy_search_timing():
    replay = _timed_replay()
    final = {
        "search_seconds": 60.0, "first_found_seconds": 5.1,
        "stabilized_seconds": 5.1, "strategy_wave": "first",
        "strategy_focus_position": 3, "strategy_focus_count": 8,
    }
    live = {0: [{"bellman": True, "chosen": [0],
                 "diagnostics": {
                     "terminal_proof": {"attempted": True, "elapsed_ms": 125.0},
                     "production": {"final_incumbent": final},
                 }},
                {"bellman": True, "chosen": [0]}]}

    frames = frames_payload(replay, live_records_by_seat=live)["frames"]

    assert frames[0]["search_timing"]["remaining_seconds"] == pytest.approx(54.9)
    assert frames[0]["lethal_proof_seconds"] == pytest.approx(0.125)
    assert "Lethal solver" in _SHELL_HTML
    assert "Final sequence first found" in _SHELL_HTML
    assert "Strategy focus position" in _SHELL_HTML


def test_frames_distil_search_trace_instead_of_shipping_it_to_the_browser():
    """The trace is ~650 KB per Decision and no pane reads it, so it must stay server-side while the
    verdict fields the pane DOES read survive."""
    replay = _timed_replay()
    live = {0: [{"bellman": True, "chosen": [0], "margin": 1.5,
                 "diagnostics": {"terminal_proof": {"attempted": True, "elapsed_ms": 125.0}}},
                {"bellman": True, "chosen": [0]}]}

    frames = frames_payload(replay, live_records_by_seat=live)["frames"]

    assert "diagnostics" not in frames[0]["live"]
    assert frames[0]["live"]["margin"] == 1.5
    assert frames[0]["live"]["chosen"] == [0]
    assert frames[0]["lethal_proof_seconds"] == pytest.approx(0.125)


def test_frames_and_shell_present_the_complete_ledger_decision_contract():
    replay = _timed_replay()
    ledger = {
        "schema": "ledger.telemetry", "record_type": "decision", "record_id": "d1",
        "decision": {
            "variant": "ledger", "selection": [0], "chosen_action_id": "a",
            "policy_reason": "positive_continuation", "seat": 0, "index": 0,
        },
        "observation": {"select": {"context": 0}},
        "opponent_snapshot": {"identity": "opp-1"},
        "actions": [{"id": "a", "selection": [0], "identity": "play"}],
        "root": {"total": 10.0, "components": [{"feature": "board", "value": 10.0}]},
        "candidates": [{
            "action_id": "a", "disposition": "continues_turn", "status": "estimated",
            "delta": {"total": 3.0, "components": [{"feature": "tempo", "value": 3.0}]},
            "gaps": ["chain capped; scored mid-effect board"], "successors": [{}],
            "policy_tie_break": [1], "policy_evidence": {"reason": "develop"},
        }],
        "search": {"nodes_visited": 1, "stop_reason": "complete", "failure": None},
        "behavior_identity": {"evaluator": "ledger-linear-v1"},
        "configuration": {"compute": {"identity": "default"}},
        "timing": {"decision_seconds": 0.25}, "completeness": "estimated",
    }

    frame = frames_payload(replay, live_records_by_seat={0: [ledger]})["frames"][0]

    assert frame["live"] is None
    assert frame["ledger"] == ledger
    assert frame["ledger"]["decision"]["policy_reason"] == "positive_continuation"
    assert frame["ledger"]["candidates"][0]["delta"]["total"] == 3.0
    assert "Ledger decision" in _SHELL_HTML
    assert "candidate roster" in _SHELL_HTML
    assert "legal observation" in _SHELL_HTML
    assert "opponent snapshot" in _SHELL_HTML


def test_frames_index_keeps_full_ledger_details_off_the_initial_page_load():
    replay = _timed_replay()
    ledger = {
        "schema": "ledger.telemetry", "record_type": "decision",
        "decision": {"seat": 0, "selection": [0]},
        "configuration": {"large": "x" * 1000},
    }
    full = frames_payload(replay, live_records_by_seat={0: [ledger]})

    indexed = frames_index_payload(full)
    details = frame_details_payload(full, frame=0)

    assert indexed["frames"][0]["has_details"] is True
    assert "ledger" not in indexed["frames"][0]
    assert "live" not in indexed["frames"][0]
    assert details == {"frame": 0, "live": None, "ledger": ledger}


def test_frames_open_on_a_board_that_has_cards_on_it():
    """A real film opens on the coin flip, whose board is empty — nothing is dealt yet — so landing
    the viewer on frame 0 shows a blank board."""
    replay = load_replay(FIXTURE)
    film = replay["steps"][0][0]["visualize"]

    opening = frames_payload(replay)["opening_frame"]

    assert opening > 0
    assert not any(player.get(area) for player in film[0]["current"]["players"]
                   for area in ("active", "bench", "hand"))
    assert any(player.get(area) for player in film[opening]["current"]["players"]
               for area in ("active", "bench", "hand"))
