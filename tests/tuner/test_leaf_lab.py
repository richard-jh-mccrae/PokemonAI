"""The leaf lab — offline leaf-quality measurement (develop rung, `docs/plans/turn-planner-develop-rung.md`).

The develop rung is only as good as its end-of-turn LEAF. The lab re-scores a tagged `turn_plan`
correction's board through `_engine_leaf_value` (cgpy-backed offline, so ANY leaf version is measurable
without a ladder run) and asks the one question that matters: **does the leaf rank the human's `correct`
option highest?** These tracers pin the per-correction metrics with the leaf stubbed (the cgpy wiring is
a CLI concern); the stub mirrors the real ep86090164 board (correct=[0] buried under a 4-way tie at 65).
"""
from types import SimpleNamespace

import pytest

from train.leaf_lab import evaluate_leaf_on_correction, is_leaf_frame


def _obs(n_options, context=0):
    return {"select": {"context": context, "option": [{"type": 0} for _ in range(n_options)]},
            "current": {}}


def _frame(*, obs=None, turn_plan=None, correct=None):
    return SimpleNamespace(obs=obs, turn_plan=turn_plan, correct=correct or [])


@pytest.mark.req("REQ-TUNER-0019")
def test_is_leaf_frame_accepts_turn_plan_and_main_select_pick_corrections():
    """The lab measures two correction shapes (`is_leaf_frame`): a turn-planner correction (carries a
    `turn_plan` payload — kept even with an empty `correct`, so an unscored setup turn is still counted)
    and any MAIN-select (context 0) pick correction that names a `correct` option — the second shape is
    what lets the whole tagged setup corpus drive leaf enrichment, not only the prose turn_plan ones."""
    assert is_leaf_frame(_frame(obs=_obs(4), turn_plan={"intended_line": "x"})) is True
    assert is_leaf_frame(_frame(obs=_obs(4, context=0), correct=[2])) is True


@pytest.mark.req("REQ-TUNER-0019")
def test_is_leaf_frame_rejects_unreseedable_and_targetless_frames():
    """Excluded: a non-MAIN pick correction (context != 0 — the offline sim reseeds ONLY from a
    MAIN-select board, so it could never be scored), a MAIN correction with no `correct` target, and an
    obs-less record. A turn_plan record is exempt from the context gate (its own domain)."""
    assert is_leaf_frame(_frame(obs=_obs(4, context=7), correct=[2])) is False   # non-MAIN pick
    assert is_leaf_frame(_frame(obs=_obs(4, context=0), correct=[])) is False     # no target
    assert is_leaf_frame(_frame(obs=None, correct=[2])) is False                  # no obs


def _pilot(values):
    p = SimpleNamespace(_planning=False)
    p._engine_leaf_value = lambda obs, step: values.get(step[0])
    return p


@pytest.mark.req("REQ-TUNER-0019")
def test_evaluate_reports_the_correct_pick_rank_and_top_tie():
    """The ep86090164 shape: leaf scores the correct pick [0] at 60, but four options tie at 65 above
    it. The lab must report `correct` is NOT top, its rank (5th — four strictly outscore it), and the
    degenerate 4-way tie at the top (the leaf can't discriminate)."""
    values = {0: 60.0, 1: 65.0, 2: 65.0, 3: 65.0, 4: 65.0, 5: 60.0, 6: 55.0, 7: 50.0}
    v = evaluate_leaf_on_correction(_pilot(values), SimpleNamespace(correct=[0], obs=_obs(8),
                                                                    episode_id=86090164))
    assert v["scored"] == 8
    assert v["correct_value"] == 60.0
    assert v["top_value"] == 65.0
    assert v["correct_is_top"] is False
    assert v["outscored_by"] == 4                       # opts 1-4 strictly above
    assert v["correct_rank"] == 5
    assert v["top_tie"] == 4                            # the 4-way degenerate tie


@pytest.mark.req("REQ-TUNER-0019")
def test_leaf_correct_when_the_human_pick_is_the_unique_top():
    """A healthy leaf: the correct pick is the strict maximum → correct_is_top, rank 1, no tie above."""
    v = evaluate_leaf_on_correction(_pilot({0: 90.0, 1: 40.0, 2: 55.0}),
                                    SimpleNamespace(correct=[0], obs=_obs(3), episode_id=1))
    assert v["correct_is_top"] is True
    assert v["correct_rank"] == 1
    assert v["outscored_by"] == 0
    assert v["top_tie"] == 1
