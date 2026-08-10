"""Tier 5 — the Automatic Value Model (ADR-0042): features, the pure-Python logistic, the absent-safe
runtime, and the planner leaf blend.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


@pytest.mark.req("REQ-VALUE-0001")
def test_null_model_is_absent_safe_and_neutral():
    """No artifact / malformed / shape-drifted → the null model: present False, predict 0.5 (zero
    influence), never raises. The closed-form heuristic stays the clean fallback (ADR-0007)."""
    from common.value import ValueModel
    null = ValueModel.load(REPO / "does_not_exist.json")
    assert null.present is False and null.predict([1.0] * 17) == 0.5
    bad = REPO / "tests" / "value" / "_bad.json"
    bad.write_text(json.dumps({"features": ["wrong"], "weights": [1.0]}), encoding="utf-8")
    try:
        assert ValueModel.load(bad).present is False        # feature-list drift → refuse
    finally:
        bad.unlink()


@pytest.mark.req("REQ-VALUE-0002")
def test_features_are_stable_and_total():
    """The vector matches FEATURE_NAMES length, is pure over a Board, and maps a None path-turn to
    the finite sentinel (a valid in-distribution row, not a NaN hole)."""
    from common.pilot import Board
    from common.value.features import FEATURE_NAMES, features_from_board
    feats = features_from_board(Board())                    # an empty board — all defaults, no crash
    assert len(feats) == len(FEATURE_NAMES) and feats[0] == 1.0   # bias intercept
    b = Board(my_path_turns=None, their_path_turns=4.0, race_ahead=None)
    v = features_from_board(b)
    assert v[FEATURE_NAMES.index("my_path_turns")] == 12.0   # sentinel for unknown
    assert v[FEATURE_NAMES.index("their_path_turns")] == 4.0


@pytest.mark.req("REQ-VALUE-0003")
def test_logistic_learns_a_separable_signal_and_round_trips():
    """A trained model round-trips through the JSON wire into a predictor ranking a win above a loss."""
    from common.value.features import FEATURE_NAMES
    from common.value.model import ValueModel
    from train.value.logistic import fit, standardize, log_loss
    n = len(FEATURE_NAMES)
    rows, labels = [], []
    for k in range(200):
        y = k % 2
        r = [1.0] + [float(y)] + [0.0] * (n - 2)            # feature[1] carries the label exactly
        rows.append(r); labels.append(float(y))
    mean, std = standardize(rows)
    w = fit(rows, labels, mean=mean, std=std)
    assert log_loss(w, rows, labels, mean, std) < 0.05      # learns the separable signal
    model = ValueModel(weights=w, mean=mean, std=std)
    win = [1.0, 1.0] + [0.0] * (n - 2)
    lose = [1.0, 0.0] + [0.0] * (n - 2)
    assert model.predict(win) > 0.9 > 0.1 > model.predict(lose)


def _neutral_board(pilot):
    """A minimal real Board, so `_win_prob`'s None is the MODEL being absent rather than a raise."""
    obs = {"current": {"yourIndex": 0,
                       "players": [{"active": None, "bench": [], "hand": [], "prizes": 6},
                                   {"active": None, "bench": [], "hand": [], "prizes": 6}]},
           "select": {"context": 0, "type": 0, "minCount": 1, "maxCount": 1, "option": [{"type": 14}]}}
    return pilot._board(obs, obs["select"])


@pytest.mark.req("REQ-VALUE-0004")
def test_the_value_model_is_off_and_now_reaches_no_decision_at_all():
    """The model is default-OFF and cannot move a decision: there is no leaf blend, and `_win_prob` —
    its only reader — is telemetry. If a blend is rebuilt, the cap invariant belongs back here."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _ = _build_pilot("mega_starmie")
    assert pilot.value_model is None                        # DEFAULT OFF (learned seam gates on its A/B)
    assert not hasattr(pilot, "_value_term"), (
        "`_value_term` is back — a learned term is reaching the leaf again, so the cap invariant "
        "this test used to assert is owed again and must be restored here rather than assumed")
    # `_win_prob` is the surviving reader and it is telemetry-only: no model, no claim.
    assert pilot._win_prob(_neutral_board(pilot)) is None


@pytest.mark.req("REQ-VALUE-0007")
def test_extraction_pilot_carries_the_read_so_matchup_features_are_live():
    """Without a Scout, `favorability` and `posture_confidence` collapse to neutral defaults in EVERY
    training row, so the model's two matchup features are dead however varied the corpus."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _ = _build_pilot("mega_starmie")
    assert pilot.scout is not None                        # the Read is present → favorability computable
    assert pilot.posture is True                          # posture ON, mirroring main.py's default


@pytest.mark.req("REQ-VALUE-0006")
def test_favorability_sanity_gate_detects_a_live_matchup_weight():
    """Favorability's fitted |weight| must clear `eps`; it sat at ~0 in the mirror-only seed because
    favorability never varied. A dead weight FAILS the gate — park T5 rather than flip it."""
    from train.value.sanity import favorability_is_live
    live = {"features": ["bias", "favorability", "prize_diff"], "weights": [0.1, 0.42, 0.3]}
    dead = {"features": ["bias", "favorability", "prize_diff"], "weights": [0.1, 0.001, 0.3]}
    assert favorability_is_live(live, eps=0.05) is True
    assert favorability_is_live(dead, eps=0.05) is False
    assert favorability_is_live({"features": ["bias"], "weights": [0.1]}, eps=0.05) is False  # absent → not live
    # WEAK-but-real (right sign, many-SE off zero) is LIVE at the default boundary — board primitives
    # legitimately dominate the matchup prior, so "live" must not demand a large weight.
    weak = {"features": ["bias", "favorability"], "weights": [0.1, 0.047]}
    assert favorability_is_live(weak) is True                    # default eps → weak-but-real is live
    assert favorability_is_live(weak, eps=0.05) is False         # a strength bar would wrongly reject it


@pytest.mark.req("REQ-VALUE-0005")
def test_hypothetical_board_build_does_not_pollute_live_memory():
    """`_board_hypothetical` must not perturb the live turn-scoped memory. Structural since ADR-0068
    decision 2: the build reads both memories off the Carried State snapshot and writes neither."""
    from common.strategy.strategy import Plan
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _ = _build_pilot("mega_starmie")
    pilot._phase_prev = Plan.STABILIZE                      # a live hysteresis state …
    pilot._my_path_prev = frozenset({678})                 # … and a live sticky path
    obs = {"current": {"yourIndex": 0, "turn": 6,
                       "players": [{"active": [{"id": 666, "hp": 210, "energies": []}],
                                    "bench": [], "hand": [], "prize": [None] * 6},
                                   {"active": [{"id": 678, "hp": 440, "energies": []}],
                                    "bench": [], "prize": [None] * 6, "hand": []}]}}
    before = pilot.carried()                                # the declared channel's snapshot
    pilot._board_hypothetical(obs)                          # build a FUTURE board for features
    assert pilot._phase_prev is Plan.STABILIZE              # live memory untouched …
    assert pilot._my_path_prev == frozenset({678})         # … both members
    assert pilot.carried() == before                        # … and the channel as a whole

    # The same guarantee now extends to a full option re-score inside a simulated line (the second
    # site that used to carry its own hand-written save/restore pair).
    pilot._evaluate(dict(obs, select={"option": []}), carried=pilot.carried())

# temp: paths-filter selective-testing diagnostic, single-file no-op change, safe to discard
    assert pilot.carried() == before
