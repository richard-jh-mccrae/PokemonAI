"""A CRITICAL: snipe the developing-wincon pre-evo over the energized 1-prize accelerator.

The `evolving_wincon_priority` mechanism this file is named after is DELETED (ADR-0085 Amendment G);
`snipe_relevance`'s `forward` leg carries the CRITICAL by ORDERING rather than by a stand-down.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

FIXTURE = "ms_snipe_evolving_wincon_over_promotion_stack_f22.json"
CINDERACE, STARYU = 0, 1          # option indices on the captured DAMAGE select


def _fx():
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / FIXTURE).read_text(encoding="utf-8"))


def _pilot(**overrides):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot = _build_pilot("mega_starmie")[0]
    for k, v in overrides.items():
        setattr(pilot, k, v)
    return pilot


@pytest.mark.req("REQ-READ-0006")
def test_the_developing_wincon_preevo_is_sniped_over_the_energized_accelerator():
    fx = _fx()
    dec = _pilot().explain(fx["obs"])
    assert all(c in dec.chosen for c in fx["correct"]), (
        f"chose {dec.chosen}, want {fx['correct']} ({fx.get('correct_label')})")
    assert dec.chosen == [STARYU]


@pytest.mark.req("REQ-READ-0006")
def test_neither_target_scores_zero():
    """All-zero scores collapse the argmax to index order, which lands on Cinderace — the blunder —
    while every rung reports 'stood down' as designed."""
    scores = {t.index: t.score for t in _pilot().explain(_fx()["obs"]).options}
    assert scores[STARYU] > 0, "the evolving-wincon rung must actually fire on the pre-evo"
    assert not all(s == 0 for s in scores.values()), "all targets zeroed -> argmax is index order"


@pytest.mark.req("REQ-READ-0006")
def test_the_scalar_carries_the_critical_without_a_stand_down_switch():
    """Staryu must OUT-SCORE Cinderace, not merely outlive it: win-by-elimination satisfies the two
    tests above while meaning the retired stand-down came back by another route (ADR-0085 Amdt G)."""
    scores = {t.index: t.score for t in _pilot().explain(_fx()["obs"]).options}
    assert scores[STARYU] > scores[CINDERACE], "Staryu must WIN on ordering, not survive a stand-down"
