"""Blunder round 2026-07-09 SPLIT-OUTS — applied 2026-07-10 via /update-strategy (dragapult_ex).

Four proposals that were split out of the 2026-07-09 dragapult blunder round because each needed a
distinct mechanism the parent fix couldn't provide. Grilled + authored 2026-07-10:

  - f14  `develop-the-item-lock-opener` (general-hypothesis): at an empty-Bench hand-search, grab the
         deck's item-lock opener (Budew) over a redundant base or an evolution that only stacks on the
         Active. Rides two BREADTH stand-downs (redundant in-play base; empty-Bench mid-Line evolution)
         plus `fetch-the-support` no longer crediting a win-condition-line evolution as an engine.
  - f32 + f20  `retreat-to-wall-the-line` (planner-code): the retreat-to-promote-the-sacrificial-wall
         maneuver — a fragile developing Dreepy retreats behind a benched Budew item-lock wall. Verified
         single-frame (the retreat is step 1, tier-0 in `_finish_turn_last`); the follow-through rides
         existing rungs. Unifies f32 with the deferred f20 retreat-to-promote-disruptor.
  - f10  `gust-for-the-stall` gated on `opp_active_can_damage_us`: don't gust a HARMLESS Active (Kyogre
         at 0 Energy) off to the bench — it just frees it; keep it pinned and develop. The +95 famine
         hard-stall is deliberately NOT gated (its canonical case is a harmless-now-but-forward-lethal
         Active — see tests/strategy/test_gust.py).
  - f79  the `bench_fill` fetch-filter tightened to <=70 HP (Buddy-Buddy Poffin only fetches Basics with
         70 HP or less), so the sound whiff guard `dont-search-an-empty-deck` sees the exhaustion.

Single-frame verification per the grill: the f32 maneuver is a TEMPO play (a partial maneuver is not
catastrophic), so verifying the retreat step is sound; the lethal retreat-enabler (f15) stays deferred.
"""
import json
import sys
from pathlib import Path

import pytest

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
    """f14 (CRITICAL): Active a lone Dreepy, bench EMPTY, Drakloak in the discard. At an Ultra Ball grab
    the agent took Drakloak (+53: a mid-Line evolution that only stacks on the Active, leaving the Bench
    empty). Correct is Budew — the item-lock opener that fills the Bench and buys tempo. The breadth
    stand-downs collapse the evolution/redundant-base grabs and `develop-the-item-lock-opener` (+30)
    wins."""
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
    """f32 + f20 (CRITICAL): fragile developing Dreepy Active, Budew (item_lock) benched, opp Gabite can
    damage the line. The sound play is the retreat-to-promote-the-sacrificial-wall maneuver, NOT the
    Crushing Hammer strip. Step 1 (Retreat) rides tier-0 in `_finish_turn_last` and wins the frame."""
    fx = _fixture("dragapult_hammer_over_develop_f32")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [3] Retreat (wall the line with Budew)
    assert "retreat-to-wall-the-line" in _fired_ids(dec.options[fx["correct"][0]])


@pytest.mark.req("REQ-GEN-0075")
def test_f20_feeds_the_active_for_the_offensive_item_lock_maneuver():
    """f20 (the ATTACH-enablement frame of the OFFENSIVE item-lock maneuver, ``disruptor_lock_maneuver``,
    BUILT 2026-07-13): turn 2, a fragile Dreepy Active (0 Energy), Budew (item_lock) benched, opponent's
    Gible can NOT damage us — so this is offensive disruption, not defensive walling. Attach the Crispin
    Energy to the ACTIVE Dreepy so it can retreat into Budew and Itchy-Pollen the opponent's Item turn.
    With the maneuver flag ON, ``feed-the-line-for-disruptor-lock`` fires and decide() picks the active
    recipient [0] over the bench Dreepy [1] (the pre-maneuver blunder)."""
    fx = _fixture("dragapult_retreat_to_item_lock_f20")
    pilot = _pilot("dragapult_ex")
    pilot.disruptor_lock_maneuver = True
    dec = pilot.explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [0] active Dreepy (step 1 of the maneuver)
    assert "feed-the-line-for-disruptor-lock" in _fired_ids(dec.options[fx["correct"][0]])


def test_f20_inert_with_the_maneuver_flag_off():
    """Kill-switch bookend: with ``disruptor_lock_maneuver`` OFF the signal is silent
    (`can_lock_line_with_disruptor` False) so the maneuver rung never fires — the flag is the ship-and-
    refine lever. (The shipped PROFILE runs it ON, so flip it off explicitly here.)"""
    fx = _fixture("dragapult_retreat_to_item_lock_f20")
    pilot = _pilot("dragapult_ex")
    pilot.disruptor_lock_maneuver = False
    dec = pilot.explain(fx["obs"])
    assert "feed-the-line-for-disruptor-lock" not in _fired_ids(dec.options[fx["correct"][0]])


@pytest.mark.req("REQ-GUST-0014")
def test_f10_develops_instead_of_gusting_a_harmless_active():
    """f10: the opp Active (Kyogre, 0 Energy) is harmless NOW — gusting a benched body up would just free
    Kyogre to the Bench. `gust-for-the-stall` stands down (gated on `opp_active_can_damage_us`) and the
    agent attaches Energy to develop instead, saving the premium Boss's Orders."""
    fx = _fixture("dragapult_gust_wasted_in_setup_f10")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [2] Attach {P} -> Dreepy
    boss = next(o for o in dec.options if o.card_id == BOSS)
    assert "gust-for-the-stall" not in _fired_ids(boss)         # the harmless-Active gust stands down


@pytest.mark.req("REQ-GEN-0076")
def test_f79_poffin_whiff_detected_after_tightening_bench_fill_filter():
    """f79: the deck holds no fetchable <=70-HP Basic, so Buddy-Buddy Poffin whiffs. With the `bench_fill`
    filter tightened to <=70 HP, the sound whiff guard `dont-search-an-empty-deck` (-60) now fires on the
    Poffin play. (The gust-KO is still the pick — Boss's Orders for the Phantom-Dive line.)"""
    fx = _fixture("dragapult_poffin_whiff_take_gust_ko_f79")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [4] Boss's Orders (gust-for-the-ko)
    poffin = next(o for o in dec.options if o.card_id == POFFIN)
    assert "dont-search-an-empty-deck" in _fired_ids(poffin)    # the whiff is now provable
