"""The leaf lab — offline leaf-quality measurement, and the Discrimination Gate's instrument.

It re-scores a tagged correction's board offline and asks whether the leaf ranks the human's
`correct` option highest. The scorer reads `ComposerResult.fanned` — the composer's own depth-0
differencing, taken off the shipped call rather than re-derived. These tracers stub the scorer."""
from types import SimpleNamespace

import pytest

from train.leaf_lab import evaluate_leaf_on_correction, is_leaf_frame


def _obs(n_options, context=0):
    return {"select": {"context": context, "option": [{"type": 0} for _ in range(n_options)]},
            "current": {}}


def _frame(*, obs=None, turn_plan=None, correct=None, episode_id=1, seat=0, scope="decision",
           subject=7, agent="dragapult_ex"):
    """A stand-in Correction carrying the four `identity_key` fields, because a lab row is keyed by them."""
    return SimpleNamespace(obs=obs, turn_plan=turn_plan, correct=correct or [], agent=agent,
                           episode_id=episode_id, seat=seat, scope=scope, subject=subject)


@pytest.mark.req("REQ-TUNER-0019")
def test_is_leaf_frame_accepts_turn_plan_and_main_select_pick_corrections():
    """Two shapes: a `turn_plan` payload (kept even with an empty `correct`), and a MAIN-select pick."""
    assert is_leaf_frame(_frame(obs=_obs(4), turn_plan={"intended_line": "x"})) is True
    assert is_leaf_frame(_frame(obs=_obs(4, context=0), correct=[2])) is True


@pytest.mark.req("REQ-TUNER-0019")
def test_is_leaf_frame_rejects_unreseedable_and_targetless_frames():
    """The offline sim reseeds ONLY from a MAIN-select board; a turn_plan record is exempt from that."""
    assert is_leaf_frame(_frame(obs=_obs(4, context=7), correct=[2])) is False   # non-MAIN pick
    assert is_leaf_frame(_frame(obs=_obs(4, context=0), correct=[])) is False     # no target
    assert is_leaf_frame(_frame(obs=None, correct=[2])) is False                  # no obs


@pytest.mark.req("REQ-TUNER-0019")
def test_is_leaf_frame_rejects_retired_match_scope_even_with_a_turn_plan():
    """Issue #353: a whole-game note is never one scored leaf move, even if hand-written data
    bypasses the writer and carries fields that would otherwise qualify."""
    assert is_leaf_frame(_frame(scope="match", obs=_obs(4), correct=[2])) is False
    assert is_leaf_frame(_frame(scope="match", obs=_obs(4), turn_plan={"intended_line": "x"})) is False


@pytest.fixture(autouse=True)
def _stub_the_scoring_source(monkeypatch):
    """Feed `evaluate_leaf_on_correction` per-option values without running the real scorer. The stub
    sits at the module boundary because `board_leaf_values` now builds a StateModel and composes."""
    from train import leaf_lab
    real = leaf_lab.board_leaf_values

    def shim(pilot, obs):
        values = getattr(pilot, "_test_values", None)
        if values is None:                       # a real pilot → the real (composer-backed) scorer
            return real(pilot, obs)
        n = len((obs.get("select") or {}).get("option") or [])
        return [values.get(i) for i in range(n)]

    monkeypatch.setattr(leaf_lab, "board_leaf_values", shim)


def _pilot(values):
    """A stand-in pilot carrying the per-option values `_stub_the_scoring_source` hands back."""
    return SimpleNamespace(_planning=False, _test_values=dict(values))


@pytest.mark.req("REQ-TUNER-0019")
def test_a_decision_scope_DECLINE_has_no_rank_and_the_lab_invents_none():
    """Issue #229 D3. A DECLINE (`correct: []`) names no option, so there is nothing to rank; two
    layers say so — not a leaf frame at all, and `unscorable: True` if scored anyway."""
    decline = _frame(obs=_obs(3, context=0), correct=[], scope="decision")
    assert is_leaf_frame(decline) is False
    v = evaluate_leaf_on_correction(_pilot({0: 90.0, 1: 40.0, 2: 55.0}), decline)
    assert v["unscorable"] is True
    assert v["correct"] == []
    assert (v["correct_value"], v["correct_rank"], v["correct_is_top"]) == (None, None, None)


@pytest.mark.req("REQ-TUNER-0019")
def test_evaluate_reports_the_correct_pick_rank_and_top_tie():
    """correct [0] scores 60 under a 4-way tie at 65: not top, rank 5, and a degenerate top tie."""
    values = {0: 60.0, 1: 65.0, 2: 65.0, 3: 65.0, 4: 65.0, 5: 60.0, 6: 55.0, 7: 50.0}
    v = evaluate_leaf_on_correction(_pilot(values), _frame(correct=[0], obs=_obs(8),
                                                              episode_id=86090164))
    assert v["scored"] == 8
    assert v["correct_value"] == 60.0
    assert v["top_value"] == 65.0
    assert v["correct_is_top"] is False
    assert v["correct_is_unique_top"] is False
    assert v["outscored_by"] == 4                       # opts 1-4 strictly above
    assert v["correct_rank"] == 5
    assert v["top_tie"] == 4                            # the 4-way degenerate tie


@pytest.mark.req("REQ-TUNER-0019")
def test_leaf_correct_when_the_human_pick_is_the_unique_top():
    """A healthy leaf: the correct pick is the strict maximum → correct_is_top AND unique_top, rank 1."""
    v = evaluate_leaf_on_correction(_pilot({0: 90.0, 1: 40.0, 2: 55.0}),
                                    _frame(correct=[0], obs=_obs(3), episode_id=1))
    assert v["correct_is_top"] is True
    assert v["correct_is_unique_top"] is True
    assert v["correct_rank"] == 1
    assert v["outscored_by"] == 0
    assert v["top_tie"] == 1


@pytest.mark.req("REQ-TUNER-0019")
def test_shared_top_is_lenient_hit_but_not_a_unique_top():
    """`correct_is_top` is lenient (it shares the max); `correct_is_unique_top` is not — the argmax
    rung breaks a tie by option order, not by intent, so it lands on `correct` only by luck."""
    v = evaluate_leaf_on_correction(_pilot({0: 90.0, 1: 90.0, 2: 55.0}),
                                    _frame(correct=[0], obs=_obs(3), episode_id=1))
    assert v["correct_is_top"] is True                  # shares the max → lenient hit
    assert v["correct_is_unique_top"] is False          # but NOT the sole max → not the rung's guaranteed pick
    assert v["top_tie"] == 2


# ── Option Equivalence Class awareness (ADR-0091 decision 4, Issue #247) ─────────────────────

def _body(cid=1030, *, serial=1, hp=70):
    return {"appearThisTurn": False, "energies": [], "energyCards": [], "hp": hp, "id": cid,
            "maxHp": 70, "playerIndex": 0, "preEvolution": [], "serial": serial, "tools": []}


def _twin_obs(bodies, n_extra=0):
    """A MAIN-select board whose first options each pick one bench body, plus optional distinct
    filler options that can never join a class."""
    opts = [{"area": 5, "index": i, "playerIndex": 0, "type": 3} for i in range(len(bodies))]
    opts += [{"type": 14 + j} for j in range(n_extra)]
    return {"select": {"context": 0, "option": opts},
            "current": {"yourIndex": 0, "looking": None,
                        "players": [{"active": [], "bench": list(bodies), "hand": [], "discard": []},
                                    {"active": [], "bench": [], "hand": [], "discard": []}]}}


def test_a_tie_WITHIN_one_class_reports_as_SOLE_top():
    """Two options that are the same decision tying is correct behaviour, not a failure to discriminate."""
    obs = _twin_obs([_body(serial=1), _body(serial=2)])
    row = evaluate_leaf_on_correction(_pilot({0: 65.0, 1: 65.0}), _frame(obs=obs, correct=[0]))
    assert row["correct_is_top"] is True
    assert row["correct_is_unique_top"] is True, "one decision, tied with itself"
    assert row["top_tie"] == 1, "ties count CLASSES, not raw options"


def test_a_tie_ACROSS_two_classes_is_still_not_sole_top():
    """The negative half — the measure must not become vacuous. Two genuinely different bodies tying
    at the top is a leaf that cannot discriminate, exactly as before."""
    obs = _twin_obs([_body(serial=1), _body(cid=1031, serial=2)])
    row = evaluate_leaf_on_correction(_pilot({0: 65.0, 1: 65.0}), _frame(obs=obs, correct=[0]))
    assert row["correct_is_top"] is True
    assert row["correct_is_unique_top"] is False
    assert row["top_tie"] == 2


def test_a_class_tying_with_an_unrelated_option_counts_both():
    obs = _twin_obs([_body(serial=1), _body(serial=2)], n_extra=1)
    row = evaluate_leaf_on_correction(_pilot({0: 65.0, 1: 65.0, 2: 65.0}),
                                      _frame(obs=obs, correct=[0]))
    assert row["top_tie"] == 2, "the twins are one, the stranger is another"
    assert row["correct_is_unique_top"] is False


def test_a_class_scored_TWO_WAYS_is_reported_as_CLASS_ASYMMETRY():
    """An index-order-dependent greedy rollout (Issue #254) prices byte-identical bodies differently."""
    obs = _twin_obs([_body(serial=1), _body(serial=2), _body(serial=3)])
    row = evaluate_leaf_on_correction(_pilot({0: 1167.0, 1: 95.4, 2: 95.4}),
                                      _frame(obs=obs, correct=[0]))
    assert row["class_asymmetry"] == [{"options": [0, 1, 2], "spread": pytest.approx(1071.6)}]


def test_a_symmetric_class_reports_NO_asymmetry():
    obs = _twin_obs([_body(serial=1), _body(serial=2)])
    row = evaluate_leaf_on_correction(_pilot({0: 65.0, 1: 65.0}), _frame(obs=obs, correct=[0]))
    assert "class_asymmetry" not in row


def test_float_non_associativity_is_NOT_an_asymmetry():
    """A 2.8e-14 spread from summing the same terms in a different order, not two prices. An instrument
    that can never report clean is one readers skip, so the tolerance makes "zero" expressible."""
    obs = _twin_obs([_body(serial=1), _body(serial=2)])
    row = evaluate_leaf_on_correction(
        _pilot({0: 124.83000000000001, 1: 124.82999999999998}), _frame(obs=obs, correct=[0]))
    assert "class_asymmetry" not in row


def test_a_difference_the_leaf_can_EXPRESS_is_still_an_asymmetry():
    """The negative half: the tolerance sits six orders below the 0.001 the leaf's own values are
    rounded to, so it swallows nothing the leaf could have meant."""
    obs = _twin_obs([_body(serial=1), _body(serial=2)])
    row = evaluate_leaf_on_correction(_pilot({0: 124.83, 1: 124.829}), _frame(obs=obs, correct=[0]))
    assert row["class_asymmetry"] == [{"options": [0, 1], "spread": pytest.approx(0.001)}]


def test_asymmetry_does_not_touch_the_gated_verdict():
    """Reported, never gating — the doctrine the tie metrics already carry. The gate reads
    `correct_is_top`, and an asymmetric class must not change it."""
    obs = _twin_obs([_body(serial=1), _body(serial=2)])
    row = evaluate_leaf_on_correction(_pilot({0: 95.4, 1: 1167.0}), _frame(obs=obs, correct=[0]))
    assert row["class_asymmetry"]
    assert row["correct_is_top"] is True, "the human's option IS top, up to indistinguishability"
