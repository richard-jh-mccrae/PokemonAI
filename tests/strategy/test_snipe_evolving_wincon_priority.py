"""ms 85164131 f22 (CRITICAL) — the evolving-wincon snipe priority, finally gated.

The fixture `ms_snipe_evolving_wincon_over_promotion_stack_f22.json` has existed since 2026-07-09 and
**no test consumed it**. `test_snipe_the_real_attacker.py` parametrises f75/f47/f39/f85; f22's only
trace in the tree was a comment beside the kill-switch default. So the CRITICAL correction that
motivated the whole `evolving_wincon_priority` mechanism had no regression gate at all.

The board: their Active is dead (a promotion is FORCED next turn) and their Bench holds

  [0] Cinderace     260/260, 1 Energy   — a 1-prize Stage-2 accelerator, ENERGIZED
  [1] Staryu         70/70,  bare       — the pre-evo of Mega Starmie ex, a 3-prize megaEx WINCON

Cinderace attracts three positional rungs at once — snipe-the-top-threat (+30), snipe-the-threat (+20,
energized) and snipe-the-forced-promotion (+40) — and their SUM (90) buried the +45 evolving-wincon
rung. The human filed it CRITICAL: "stomp out the eventual win condition". `evolving_wincon_priority`
stands those three down off the developing wincon so the pre-evo is chipped instead.

This also pins the DEGENERACY the fossil `Board.bench_threat_present` would have caused. Its docstring
claimed the evolving-threat snipe "stands down" when an energized benched body is present — i.e.
exactly here. Wiring that in zeroes Cinderace's three rungs (90 -> 0) AND Staryu's rung (45 -> 0),
leaving BOTH targets at 0.0, whereupon the argmax degenerates to index order and picks Cinderace: the
precise blunder. The field was a fossil of a rung retired 2026-06-30, and the doctrine had reversed
under it. `test_neither_target_scores_zero` is the tripwire.
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
    """The CRITICAL itself: chip the Staryu that becomes Mega Starmie ex (3 prizes), not the
    energized 1-prize Cinderace whose three positional rungs merely stack higher."""
    fx = _fx()
    dec = _pilot().explain(fx["obs"])
    assert all(c in dec.chosen for c in fx["correct"]), (
        f"chose {dec.chosen}, want {fx['correct']} ({fx.get('correct_label')})")
    assert dec.chosen == [STARYU]


@pytest.mark.req("REQ-READ-0006")
def test_neither_target_scores_zero():
    """The degeneracy tripwire. If BOTH targets score 0.0 the argmax silently collapses to index
    order — which lands on Cinderace, the blunder, while every rung reports 'stood down' as designed.
    A stand-down that zeroes every option is not a stand-down; it is a coin toss with a bad prior."""
    scores = {t.index: t.score for t in _pilot().explain(_fx()["obs"]).options}
    assert scores[STARYU] > 0, "the evolving-wincon rung must actually fire on the pre-evo"
    assert not all(s == 0 for s in scores.values()), "all targets zeroed -> argmax is index order"


@pytest.mark.req("REQ-READ-0006")
def test_the_kill_switch_off_restores_the_blunder_and_so_pins_why_it_exists():
    """With `evolving_wincon_priority` OFF, the three positional rungs no longer stand down and their
    sum (30 + 20 + 40 = 90) buries the evolving-wincon rung (45) — the Pilot chips Cinderace. This is
    the mechanism the switch exists to defeat; asserting it means a future 'simplification' that drops
    the stand-down cannot pass green.

    `snipe_relevance` is forced OFF because the blunder is a property of the ADDITIVE stack, and armed
    that stack is gone: the six target rungs stand down as a body (ADR-0085 decision 5), so there is
    no sum of 90 left to bury anything and `evolving_wincon_priority` has nothing to stand down. The
    scalar reaches Staryu on this board with the switch either way — it subsumes this stand-down
    rather than depending on it (ADR-0085 Amendment C) — so this test can only be posed on the OFF
    path, which is exactly where the mechanism it guards still lives.
    """
    dec = _pilot(evolving_wincon_priority=False, snipe_relevance=False).explain(_fx()["obs"])
    assert dec.chosen == [CINDERACE], "the kill-switch no longer changes the pick — has it gone inert?"
