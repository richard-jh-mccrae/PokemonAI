"""The GRAB-side refresh value (`_grab_refresh_value`, ADR-0122 amendment) — and the residual it
finally discharges.

**This file used to pin the opposite outcome, on purpose.** Its own docstring recorded the state of
play: *"The overall pick at f29 stays the seam-C chain opener (Team Rocket's Petrel, +15) — the
Petrel-vs-Lillie's residual is filed for human re-review."* The 0.1/card tie-break it tested was
built to separate Lillie's from Judge WITHOUT disturbing the band, so it could never take the frame
back from Petrel; the deferral was honest and it is now discharged by developer ruling (2026-08-06):

> *"86088989-29 has an empty hand and 6 prize cards remaining. playing meowth ex to then fetch a
> lillies and get 8 cards is the better play"*

The fix is a value equation, not a weight. `_grab_refresh_value` prices a grabbed refresh at the
SWING playing it will produce — `_refresh_swing`, the identical quantity `_refresh_swing_tactical`
scores at the PLAY seam — so the grab reads the two facts the flat band could not:

* **magnitude** — Lillie's draws 8 here (its printed prize-conditional: exactly 6 Prizes remaining),
  Judge 4;
* **the gift** — Judge shuffles BOTH hands and refills a 2-card opponent to 4; Lillie's touches only
  mine. `own_draw_count` alone (8 ≻ 4) never saw this, and would rank a big symmetric refill above a
  smaller one-sided one on a board where that is backwards.

    Lillie's   CYCLE 20 − shed 0 (empty hand) − gift 0     = +20
    Judge      CYCLE 20 − shed 0              − gift 8×2   = +4

The flat `grab-a-draw-supporter-in-setup` (+10) is RETIRED in the same change rather than left
underneath, on ADR-0069 §7's discipline (*"the rungs the decider replaced are DELETED, not shadowed,
so nothing can double-count"*) — it is a category credit for precisely what the swing now measures,
and stacking them is what made f71 tie at 8.00 and fall to the option index.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

PETREL, JUDGE, LILLIES = 1219, 1213, 1227


def _record(episode: str, frame: int):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089)."""
    from corpus_helpers import corpus_record
    return corpus_record(episode, frame)


def _pilot():
    """A FRESH pilot per test — the Pilot is stateful across `explain()` calls (corpus discipline)."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("mega_lucario")[0]


def _by_card(dec):
    out = {}
    for t in dec.options:
        out.setdefault(t.card_id, t)
    return out


@pytest.mark.req("REQ-DISRUPT-0001")
def test_lillies_outranks_judge_by_the_swing_not_by_a_tiebreak():
    """ep86088989 f29: Lillie's beats Judge, and the MARGIN is the point. A sub-point tie-break put
    them 0.4 apart; the swing puts them 16 apart, because it prices the 8-vs-4 draw AND the two cards
    Judge hands the opponent. A regression to any flat category credit collapses this gap."""
    dec = _pilot().explain(_record("86088989", 29).obs)
    by_card = _by_card(dec)
    judge, lillies = by_card[JUDGE], by_card[LILLIES]
    assert lillies.score > judge.score
    assert lillies.score - judge.score == pytest.approx(16.0)


@pytest.mark.req("REQ-DISRUPT-0001")
def test_the_swing_takes_the_frame_back_from_the_chain_opener():
    """**The discharged residual.** This assertion is the exact inverse of the one this file shipped
    with, and it is the developer's ruling: with an empty hand at six prizes, fetching the 8-card
    Lillie's beats opening a tutor chain.

    Petrel's `grab-the-chain-opener` (+15) is untouched — it still fires and still scores 15. What
    changed is that a refresh is no longer capped beneath it by construction."""
    dec = _pilot().explain(_record("86088989", 29).obs)
    by_card = _by_card(dec)
    petrel, lillies = by_card[PETREL], by_card[LILLIES]
    assert lillies.score > petrel.score
    assert any(h.id == "grab-the-chain-opener" for h, _ in petrel.fired)
    assert dec.chosen and dec.options[dec.chosen[0]].card_id == LILLIES


@pytest.mark.req("REQ-DISRUPT-0001")
def test_the_category_rung_is_retired_so_the_swing_cannot_double_count():
    """ADR-0069 §7's discipline, applied here: the flat `grab-a-draw-supporter-in-setup` (+10) is a
    category credit for the very thing the swing measures, so it is DELETED rather than left
    underneath. Left in place it lifted an unplayable Lillie's to an exact 8.00 tie with Fighting
    Gong on ml f71 — a tie the option index then broke the wrong way (`test_blunder_20260710.py::
    test_grab_lunar_cycle_fuel_f71`, which is the guard that caught it)."""
    from common.strategy.general_strategy import GENERAL_STRATEGY
    assert not any(h.id == "grab-a-draw-supporter-in-setup" for h in GENERAL_STRATEGY.hypotheses)


@pytest.mark.req("REQ-DISRUPT-0001")
def test_a_refresh_that_cannot_be_played_this_turn_is_halved_not_ignored():
    """The one thing the grab adds to the play-side number is WHEN it can be cashed, and it uses the
    shared convention (`grading.halve(1)`, ADR-0070 §6) rather than a rate invented here — the same
    treatment `deploy_value` gives its own `supporter_quota_spent` leg.

    ml f71 is the case: the Supporter quota is already spent, so Lillie's swing halves to +10 and,
    with the retired category credit no longer propping it, the playable Fighting Gong wins."""
    rec = _record("85058574", 71)
    dec = _pilot().explain(rec.obs)
    by_card = _by_card(dec)
    assert LILLIES in by_card, "f71 offers a Lillie's — the fixture changed"
    assert by_card[LILLIES].score < 0.0        # −12 unplayable + halved swing, no flat band under it
    assert dec.chosen and dec.options[dec.chosen[0]].card_id == 1142   # Fighting Gong
