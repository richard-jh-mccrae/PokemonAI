"""ms 85164131 f22 (CRITICAL) — the evolving-wincon snipe priority, finally gated.

⚠️ **The MECHANISM this file is named after no longer exists** (ADR-0085 Amendment G, 2026-07-30).
`evolving_wincon_priority`, `Board.evolving_wincon_on_bench` and the three rungs it stood down are all
DELETED; the f22 CRITICAL is now carried by `snipe_relevance`'s `forward` leg, which reaches the same
pick by ORDERING rather than by standing anything down. Everything below the next paragraph describes
the pre-2026-07-30 additive machinery and is kept as the historical record of WHY the correction was
filed — read it in the past tense. The live assertion is
`test_the_scalar_carries_the_critical_without_a_stand_down_switch`.

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
def test_the_scalar_carries_the_critical_without_a_stand_down_switch():
    """**The witness for retiring `evolving_wincon_priority`** (ADR-0085 Amendment G, user-ruled
    2026-07-30).

    This test used to assert the opposite direction: with the kill-switch OFF, the three positional
    rungs stopped standing down, their sum `30 + 20 + 40 = 90` buried the `+45` evolving-wincon rung,
    and the Pilot chipped Cinderace — the CRITICAL blunder. That assertion is no longer *posable*.
    The deletion pass removed all six rungs, so there is no sum of 90 left to bury anything, no
    stand-down left to switch off, and `board.evolving_wincon_on_bench` had ZERO readers. The flag was
    measured inert on this very frame — Staryu either way — and was retired rather than left in
    `PROFILE` advertising a behaviour it no longer had.

    What replaces it is the claim the flag was really making: **the developing win-condition pre-evo
    outranks the energized current attacker on f22.** The scalar reaches that by ORDERING rather than
    by standing anything down — Staryu earns the `forward` leg (its line reaches Mega Starmie ex, a
    3-prize wincon not yet in play) while Cinderace's 1-prize body has no forward payoff to bank. So
    the doctrine is asserted directly against the shipped instrument, which is the only place it now
    lives, and a regression in the `forward` leg fails here rather than silently reinstating a
    CRITICAL.

    The PICK itself is asserted by `test_..._is_sniped_over_the_energized_accelerator` above and the
    non-degeneracy by `test_neither_target_scores_zero`; this asserts the one thing neither covers and
    the retirement turns on — that Staryu **out-scores** Cinderace rather than merely outliving it.
    Win-by-elimination would satisfy both other tests while meaning the stand-down had come back by
    another route.
    """
    scores = {t.index: t.score for t in _pilot().explain(_fx()["obs"]).options}
    assert scores[STARYU] > scores[CINDERACE], "Staryu must WIN on ordering, not survive a stand-down"
