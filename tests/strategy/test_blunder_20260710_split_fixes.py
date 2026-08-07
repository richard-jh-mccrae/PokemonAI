"""Blunder round 2026-07-09 SPLIT-OUTS (dragapult_ex) — four proposals each needing a distinct
mechanism the parent fix could not provide.

The f32 maneuver is verified SINGLE-FRAME (a tempo play, so a partial maneuver is not catastrophic);
the lethal retreat-enabler stays deferred.
"""
import json
import sys
from pathlib import Path

import pytest

from poc_t4_flips import marks

REPO = Path(__file__).resolve().parents[2]

POFFIN = 1086
BOSS = 1182


def _pilot(deck):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(deck)
    return pilot


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _fired_ids(option):
    return {h.id for h, _w in option.fired}


@pytest.mark.req("REQ-GEN-0074")
def test_f14_grabs_the_item_lock_opener_over_evolution_and_redundant_base():
    """With an EMPTY Bench, a mid-Line evolution only stacks on the Active — the breadth stand-downs
    collapse those grabs so the item-lock opener wins."""
    fx = _fixture("dragapult_fetch_stranded_payoff_f14")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [1] Budew
    assert "develop-the-item-lock-opener" in _fired_ids(dec.options[fx["correct"][0]])


@pytest.mark.req("REQ-GEN-0075")
@pytest.mark.xfail(strict=True, reason="TURN-PLANNER SCOPE — deferred to #165 (Phase 1g), user ruling "
                   "2026-07-25: finish the individual value equations, then grill and implement the "
                   "planner. f32's correct play is a five-step maneuver whose value is the END STATE "
                   "(retreat Dreepy->Budew, evolve Dreepy->Drakloak, Recon, reconsider, Itchy-Pollen "
                   "item-lock); the standalone evolve at 32 beats retreat-to-wall at 30 and the "
                   "maneuver is simply better. The 2026-07-15 grill named this a cross-layer "
                   "requirement of the 1b swap and it regressed exactly as anticipated — no lethal "
                   "tier composes a retreat+evolve+lock sequence whose payoff is positional. STRICT "
                   "so it XPASSes and forces this mark's removal when the planner lands.")
def test_f32_retreats_to_wall_the_line_with_the_item_lock_disruptor():
    """The sound play is the retreat-to-promote-the-sacrificial-wall maneuver; step 1 rides tier 0."""
    fx = _fixture("dragapult_hammer_over_develop_f32")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [3] Retreat (wall the line)
    # The rung-id assertion here is DELETED with its rung (Issue #386): it gave this strict xfail a
    # SECOND cause, and the recorded reason is a seam-coverage gap. One xfail, one cause.


@pytest.mark.req("REQ-GEN-0075")
def test_f20_feeds_the_active_for_the_offensive_item_lock_maneuver():
    """The opponent CANNOT damage us here, so this is OFFENSIVE disruption, not defensive walling: the
    Energy goes to the Active so it can retreat into the item-lock body."""
    fx = _fixture("dragapult_retreat_to_item_lock_f20")
    pilot = _pilot("dragapult_ex")
    pilot.disruptor_lock_maneuver = True
    dec = pilot.explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [0] active Dreepy (step 1 of the maneuver)
    assert "feed-the-line-for-disruptor-lock" in _fired_ids(dec.options[fx["correct"][0]])


def test_f20_inert_with_the_maneuver_flag_off():
    """Kill-switch bookend. The shipped PROFILE runs the flag ON, so it is flipped off explicitly here."""
    fx = _fixture("dragapult_retreat_to_item_lock_f20")
    pilot = _pilot("dragapult_ex")
    pilot.disruptor_lock_maneuver = False
    dec = pilot.explain(fx["obs"])
    assert "feed-the-line-for-disruptor-lock" not in _fired_ids(dec.options[fx["correct"][0]])


@pytest.mark.req("REQ-GUST-0014")
def test_f10_develops_instead_of_gusting_a_harmless_active():
    """Gusting a benched body up would FREE the harmless Active, so `gust-for-the-stall` stands down."""
    fx = _fixture("dragapult_gust_wasted_in_setup_f10")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [2] Attach {P} -> Dreepy
    boss = next(o for o in dec.options if o.card_id == BOSS)
    # The `not in <deleted-rung>` line here is GONE with its rung (Issue #386) — it would be true of
    # every board in the game.


@pytest.mark.req("REQ-GEN-0076")
@pytest.mark.xfail(strict=True, reason=marks("dragapult_poffin_whiff_take_gust_ko_f79")[0].kwargs["reason"])
def test_f79_poffin_whiff_detected_after_tightening_bench_fill_filter():
    """The `bench_fill` filter is <=70 HP (the card's own text), so the whiff guard can see exhaustion."""
    fx = _fixture("dragapult_poffin_whiff_take_gust_ko_f79")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [4] Boss's Orders (gust-for-the-ko)
    poffin = next(o for o in dec.options if o.card_id == POFFIN)
    assert "dont-search-an-empty-deck" in _fired_ids(poffin)    # the whiff is now provable
