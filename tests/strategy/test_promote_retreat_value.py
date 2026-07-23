"""Promote/retreat value oracle (common/promote_retreat_value.py) —
docs/plans/promote-retreat-grill-spec.md §Settled design.

PURE unit tests: the design proof for the 1-exchange two-sided shadow. Each test pins one of the six
grill rulings (2026-07-22) as an executable assertion, plus the two walked corpus frames encoded at
the input level. While the oracle is REPORTING-ONLY (emitted on `OptionTrace.promote_retreat_shadow`)
these tests are what must hold before the `baseline_promote`/`baseline_retreat` rungs are swapped.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from common.promote_retreat_value import PromoteRetreatInputs as PRI
from common.promote_retreat_value import promote_retreat_value as prv


# ---- readiness leg (my_yield) — the two walked frames, encoded at input level -------------------

def test_readiness_carries_same_prize_pick_f104():
    """83007714-104: two Mega Starmie ex (SAME 3-prize body); the ready 3-Energy Hero's-Cape copy
    out-ranks the empty one on pure `can_attack_now` readiness — `their_yield` is equal, so the pick
    is all my_yield. The 'first-bench-slot blindness' the ladder's per-option fix targets."""
    ready = PRI(is_wincon=True, can_attack_now=True, is_best_target=True,
                prize_value=3, opp_prizes_remaining=4)
    empty = PRI(is_wincon=True, can_attack_now=False, is_best_target=False,
                prize_value=3, opp_prizes_remaining=4)
    assert prv(ready).total > prv(empty).total


def test_readiness_carries_cross_body_pick_f120():
    """82753102-120: promote the 1-prize accelerator that CAN act (Cinderace) over the empty line
    piece (Staryu), both 1-prize. Holds on band value alone — the speculative retreat-to-win is NOT
    priced here (ruling 4), yet the pick is still correct."""
    cinderace = PRI(can_attack_now=True, is_accelerator=True, bench_underpowered=True,
                    prize_value=1, opp_prizes_remaining=6)
    staryu = PRI(can_attack_now=False, prize_value=1, opp_prizes_remaining=6)
    assert prv(cinderace).total > prv(staryu).total


# ---- ruling 1: forgone attack is a SUBTRACTION inside the differential (voluntary retreat) -------

def test_forced_promote_has_no_retreat_cost_or_forgone():
    """A forced promote (TO_ACTIVE, `is_switch=False`) pays no retreat Energy and forgoes no attack —
    those terms are the voluntary-retreat side only."""
    forced = PRI(is_switch=False, can_attack_now=True, retreat_energy_worth=8.0, stay_yield=30.0)
    v = prv(forced)
    assert v.retreat_cost == 0.0
    assert v.stay_forgone == 0.0


def test_forgone_attack_subtracts_and_can_flip_the_sign():
    """Ruling 1: the current Active's forgone attack is an opportunity-cost subtraction, not a veto.
    A voluntary retreat whose destination band value is small nets NEGATIVE when staying would have
    landed a real (sub-lethal) attack — i.e. 'don't retreat, attack' falls out of the same term."""
    base = PRI(is_switch=True, can_attack_now=True, prize_value=1, opp_prizes_remaining=6)
    stay_nothing = replace(base, stay_yield=0.0)
    stay_big = replace(base, stay_yield=30.0)
    assert prv(stay_nothing).total > 0            # nothing forgone -> the pivot is worth it
    assert prv(stay_big).total < 0                # a real attack forgone -> don't retreat
    assert prv(stay_big).total < prv(stay_nothing).total


def test_retreat_cost_subtracts_on_switch_only():
    a = PRI(is_switch=True, can_attack_now=True, retreat_energy_worth=0.0)
    b = PRI(is_switch=True, can_attack_now=True, retreat_energy_worth=8.0)
    assert prv(b).total < prv(a).total
    assert prv(b).retreat_cost == 8.0


# ---- ruling 3: readiness leg is EXPECTED VALUE over closure (not the fail-closed floor) ----------

def test_ev_over_closure_is_monotonic_and_capped():
    """Ruling 3: an unready wincon whose enabler is FETCHABLE earns P(fetch) x the ready credit —
    expected value, not the fail-closed floor (which would ignore the upside). Monotonic in P, and
    capped at the ready credit (never exceeds actually being ready)."""
    base = PRI(is_wincon=True, can_attack_now=False, prize_value=2,
               opp_prizes_remaining=6, opp_can_punish=False)   # opp_can_punish off to isolate my_yield
    p0 = prv(replace(base, fetch_enables_p=0.0)).my_yield
    p5 = prv(replace(base, fetch_enables_p=0.5)).my_yield
    p1 = prv(replace(base, fetch_enables_p=1.0)).my_yield
    assert p0 == 0.0                              # fail-closed floor would stop here; EV does not
    assert 0.0 < p5 < p1                          # strictly increasing in P
    ready = prv(PRI(is_wincon=True, can_attack_now=True, opp_can_punish=False)).my_yield
    assert p1 <= ready                            # closure can never beat being ready


# ---- rulings 4/5: the win and provable-KO branches are NOT priced here (handed up) --------------

def test_win_branch_has_no_input():
    """Ruling 4: the equation never prices a match win — there is no win/lethal payoff field to pass,
    so `P x win` is structurally unrepresentable. The lethal solver owns it."""
    fields = set(PRI().__dataclass_fields__)
    assert not fields & {"win", "win_payoff", "lethal", "ko_prizes", "provable_win"}


def test_provable_ko_suppresses_the_fatal_prize_step_and_stays_in_band():
    """Ruling 5: a provable retreat->KO is the planner's; here it only suppresses the fatal-prize
    step (KOing while ahead is a fine trade), and NO lethal magnitude (~1000) ever enters — the
    shadow stays in the positional band."""
    exposed = PRI(is_wincon=True, can_attack_now=True, is_best_target=True,
                  prize_value=3, opp_prizes_remaining=3, provable_ko=False)
    trading = replace(exposed, provable_ko=True)
    assert prv(trading).their_yield < prv(exposed).their_yield     # step stands down on the KO trade
    assert abs(prv(exposed).total) < 100.0                          # band, never a lethal magnitude


# ---- ruling: their_yield prize-map asymmetry (Group D / interpose) ------------------------------

def test_prize_map_prefers_the_cheap_soaker_over_a_fatal_wincon():
    """`dont-promote-into-their-prize-reach`: a 3-prize wincon promoted into an opponent at 3 prizes
    (KOing it hands them the game) nets BELOW a 1-prize body that can soak and act."""
    fatal_wincon = PRI(is_wincon=True, can_attack_now=True, is_best_target=True,
                       prize_value=3, opp_prizes_remaining=3)
    cheap_soaker = PRI(can_attack_now=True, prize_value=1, opp_prizes_remaining=3)
    assert prv(cheap_soaker).total > prv(fatal_wincon).total


def test_their_yield_zero_when_opponent_cannot_punish():
    """ADR-0064 Decision 4: if the opponent's board literally cannot KO the body next turn, exposing
    it is free — `their_yield` is 0 regardless of its prize value."""
    safe = PRI(is_wincon=True, can_attack_now=True, prize_value=3,
               opp_prizes_remaining=3, opp_can_punish=False)
    assert prv(safe).their_yield == 0.0


def test_near_goal_prizes_cost_more():
    """The prize-map weight is super-linear near the opponent's goal: the same body exposed while they
    have 1 prize left costs more `their_yield` than while they have 5."""
    far = PRI(is_wincon=True, can_attack_now=True, prize_value=1, opp_prizes_remaining=5)
    near = PRI(is_wincon=True, can_attack_now=True, prize_value=1, opp_prizes_remaining=1)
    assert prv(near).their_yield > prv(far).their_yield


# ---- ruling 6: retreat-as-disruption folds into their_yield as a bounded tempo term -------------

def test_tempo_denied_credits_item_lock_bounded_by_opp_prizes():
    """Ruling 6: an item-lock body (Budew) earns a positive tempo-denied credit (a turn the opponent
    can't develop) — folded into the same currency, and bounded by the prizes they have left."""
    lock = PRI(is_switch=True, is_staller=True, is_item_lock=True, can_attack_now=False,
               prize_value=1, opp_prizes_remaining=3)
    no_lock = replace(lock, is_item_lock=False)
    assert prv(lock).tempo_denied > 0.0
    assert prv(lock).total > prv(no_lock).total
    # bounded: with the opponent already on their last prize, the credit cannot balloon
    starved = replace(lock, opp_prizes_remaining=0)
    assert prv(starved).tempo_denied == 0.0


def test_path_tax_is_a_small_brake():
    """`dont-promote-onto-their-path`: walking the body onto the opponent's cheapest prize path is a
    small positional brake below every positive driver, not a veto."""
    off_path = PRI(can_attack_now=True, prize_value=1, opp_prizes_remaining=6)
    on_path = replace(off_path, on_their_path=True)
    assert prv(on_path).total < prv(off_path).total


# ---- legibility (ADR-0019 full-working): total is the transparent sum of its terms ---------------

def test_total_is_the_sum_of_its_terms():
    v = prv(PRI(is_switch=True, is_wincon=True, can_attack_now=True, is_best_target=True,
                is_accelerator=True, bench_underpowered=True, is_item_lock=True,
                prize_value=2, opp_prizes_remaining=2, on_their_path=True,
                retreat_energy_worth=8.0, stay_yield=10.0))
    assert v.total == pytest.approx(
        v.my_yield - v.their_yield + v.tempo_denied - v.retreat_cost - v.stay_forgone)
