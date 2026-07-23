"""expert — one-step engine-fork value lookahead over the option menu (s3b §D1, homed in label/).

For a single-pick decision the expert forks the engine from the frame, plays each legal option, and
reads the value net on the resulting board — with a terminal override (the engine's own win/loss/draw
verdict outranks the net, same invariant as the planner's rungs). Seat-consistent: a turn-ender that
passes control to the opponent is read as ``1 − P(opponent wins)``.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def _first_forkable_main(pilot, replay, model):
    """The first single-pick MAIN frame the expert can actually fork. The expert forks the **prompt
    obs** ``film[i].obs`` — the state AT the decision, whose ``select.option`` menu matches the moves
    the recorded ``chosen`` indexes (NOT ``film[i+1].obs``, the post-choice state vread reads).
    Returns (prompt_obs, my_seat, option_count, vals) or None."""
    from train.label.expert import evaluate_options, is_single_pick

    from train.blunder.decisions import _film

    film = _film(replay)
    for i, frame in enumerate(film):
        sel = frame.get("select")
        if not (isinstance(sel, dict) and sel.get("option") and sel.get("context") == 0):
            continue
        prompt_obs = frame.get("obs")                           # the obs AT the decision (menu matches)
        if not prompt_obs or not prompt_obs.get("search_begin_input") or not is_single_pick(sel):
            continue
        assert len(prompt_obs["select"]["option"]) == len(sel["option"])   # menu alignment invariant
        vals = evaluate_options(pilot, prompt_obs, model)
        if vals:
            return prompt_obs, (prompt_obs.get("current") or {}).get("yourIndex"), len(sel["option"]), vals
    return None


@pytest.mark.req("REQ-LABEL-0004")
def test_is_single_pick_gates_multi_pick_out():
    from train.label.expert import is_single_pick

    assert is_single_pick({"minCount": 1, "maxCount": 1, "option": [1, 2, 3]})
    assert is_single_pick({"minCount": 0, "maxCount": 1, "option": [1, 2]})
    assert not is_single_pick({"minCount": 2, "maxCount": 2, "option": [1, 2, 3]})   # discard-2
    assert not is_single_pick({"maxCount": 3, "option": [1, 2, 3, 4]})


@pytest.mark.req("REQ-LABEL-0004")
def test_evaluate_options_scores_the_real_menu(ms_pilot, one_replay, seed_model):
    got = _first_forkable_main(ms_pilot, one_replay, seed_model)
    assert got is not None, "the corpus film should have at least one forkable single-pick MAIN"
    obs, my_seat, n_opts, vals = got
    assert isinstance(vals, dict) and vals                       # {option_index: V}
    assert set(vals) <= set(range(n_opts))                       # keys are legal option positions
    assert all(0.0 <= v <= 1.0 for v in vals.values())           # every V is a probability


@pytest.mark.req("REQ-LABEL-0004")
def test_terminal_override_beats_the_net(ms_pilot, seed_model):
    """A resulting board the engine calls decided returns the sound 1.0/0.0/0.5, never the net's guess."""
    from train.label.expert import _read_v

    # engine verdict = seat 0 wins.
    assert _read_v(ms_pilot, {"current": {"result": 0, "yourIndex": 0}}, seed_model, my_seat=0) == 1.0
    assert _read_v(ms_pilot, {"current": {"result": 0, "yourIndex": 1}}, seed_model, my_seat=1) == 0.0
    assert _read_v(ms_pilot, {"current": {"result": 2, "yourIndex": 0}}, seed_model, my_seat=0) == 0.5


@pytest.mark.req("REQ-LABEL-0004")
def test_non_forkable_frame_returns_none(ms_pilot, seed_model):
    from train.label.expert import evaluate_options

    # no search_begin_input → cannot fork → None (a ladder-film / mulligan frame).
    obs = {"search_begin_input": None, "select": {"minCount": 1, "maxCount": 1, "option": [{}]},
           "current": {"yourIndex": 0, "players": [{}, {}]}}
    assert evaluate_options(ms_pilot, obs, seed_model) is None


@pytest.mark.req("REQ-LABEL-0004")
def test_null_model_fails_loud(ms_pilot, one_replay):
    from common.value.model import ValueModel
    from train.label.expert import evaluate_options

    null = ValueModel.load(REPO / "nope.json")
    obs = {"search_begin_input": "x", "select": {"minCount": 1, "maxCount": 1, "option": [{}]},
           "current": {"yourIndex": 0, "players": [{}, {}]}}
    with pytest.raises(ValueError):
        evaluate_options(ms_pilot, obs, null)
