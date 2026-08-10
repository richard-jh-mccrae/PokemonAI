"""Promote/retreat DECIDER, PURE seam (common/promote_retreat_value.py) — ADR-0100, Issue #141.

Each test pins one of ADR-0100's twelve decisions as an executable assertion. Deliberately NO test
pins a raw score: every assertion is a RELATION, so a re-banding cannot invalidate it.
"""
from __future__ import annotations

import csv
import re
import statistics
from dataclasses import replace
from pathlib import Path

import pytest

from common.promote_retreat_value import (PromoteBody, PromoteRetreatInputs,
                                          RetreatSide, promote_value)
from common.strategy.combat import _EFFICIENCY
from common.strategy.context import ENERGY_RECOVER, KO_SCORE

REPO = Path(__file__).resolve().parents[2]

def pv(body: PromoteBody, retreat: RetreatSide | None = None):
    return promote_value(PromoteRetreatInputs(body=body, retreat=retreat))


# ---- decision 1: the layers SUM, and nothing recuses --------------------------------------------

def test_no_ko_or_win_magnitude_is_representable():
    """§1/§4/§5: the residual is STRICTLY sub-lethal, so summing it with the tactical KO layer cannot
    double-pay — a KO magnitude is structurally unrepresentable here, not merely unused."""
    fields = set(PromoteBody().__dataclass_fields__)
    assert not fields & {"win", "win_payoff", "lethal", "ko_value", "provable_win", "ko_score"}


def test_there_is_no_recusal_input():
    """§1: the shipped `active_can_ko` recusal is DELETED. A layer that cannot see a fact prices it
    0; it does not withdraw and leave the option unranked. So no input can suppress the equation."""
    fields = set(PromoteBody().__dataclass_fields__) | set(PromoteRetreatInputs().__dataclass_fields__)
    assert not fields & {"active_can_ko", "recuse", "abstain", "opp_can_punish"}


# ---- decision 2: `stay_forgone` is deleted — the option ranking IS the differential --------------

def test_stay_forgone_is_gone():
    """§2: at a MAIN menu the Active's attack is its OWN option, so subtracting it double-charged.
    The subtraction relocates from a term into the comparison; no field survives to re-introduce it."""
    fields = set(PromoteBody().__dataclass_fields__) | set(RetreatSide().__dataclass_fields__)
    assert not fields & {"stay_yield", "stay_forgone"}


# ---- decision 3: ONE currency, at a DERIVED rate -------------------------------------------------

def test_energy_recover_recomputes_from_the_card_set():
    """`ENERGY_RECOVER` is DERIVED, not tuned (§3): the median damage-per-Energy over attacks costing
    >= 2, the population an accel rider actually funds — a cost-1 chip is not what accel buys."""
    rates = []
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cost_txt, dmg_txt = (row.get("Cost") or "").strip(), (row.get("Damage") or "").strip()
            if cost_txt in ("", "n/a") or dmg_txt in ("", "n/a"):
                continue
            cost = len(re.findall(r"\{[A-Z]\}", cost_txt))
            printed = re.match(r"^(\d+)", dmg_txt)
            if cost < 2 or not printed or int(printed.group(1)) <= 0:
                continue
            rates.append(int(printed.group(1)) / cost)
    assert len(rates) == 305                              # the population this rate is measured over
    assert statistics.median(rates) == ENERGY_RECOVER


def test_energy_recover_sits_inside_the_bracket_two_rulings_impose():
    """Two rulings bracket the rate: ADR-0061's fueled-Aura-Jab-over-bare-Mega-Brave line from below,
    and ep81904064 f44 from above, where the retreat scores `3 x rate - 37.84` against 174.70."""
    lower = ((270 - _EFFICIENCY * 2) - (130 - _EFFICIENCY * 1)) / 3
    assert lower == pytest.approx(46.633, abs=0.001)
    assert ENERGY_RECOVER > lower                          # ADR-0061's Aura Jab line survives
    assert ENERGY_RECOVER < (174.70 + 37.84) / 3           # ep81904064 f44's attack-over-accel line


def test_the_attack_leg_is_race_discounted_against_a_standing_wall():
    """§3a: vs a standing wall the single hit is fake value — price the SEQUENCE. With no wall
    reading the reachable damage stands unchanged."""
    printed = PromoteBody(reach=70.0)
    racing = replace(printed, wall_progress=320.0 / 5)
    assert printed.my_yield() == pytest.approx(70.0)
    assert racing.my_yield() == pytest.approx(64.0)
    assert racing.my_yield() < printed.my_yield()


def test_the_accel_dividend_pays_what_the_attack_option_pays():
    """§3b: retreating INTO an accelerator must credit what attacking WITH it credits, so the
    dividend anchors on `ENERGY_RECOVER` and is need-gated by the unit count."""
    bare = PromoteBody(reach=100.0)
    accel = replace(bare, accel_units=3)
    assert accel.my_yield() - bare.my_yield() == pytest.approx(3 * ENERGY_RECOVER)


def test_the_accel_dividend_is_zero_when_no_recipient_can_use_it():
    """The need gate is the count itself: Energy nobody can pay an attack with is not development,
    so an accelerator firing blanks onto a full-but-useless bench earns exactly nothing."""
    assert PromoteBody(reach=100.0, accel_units=0).my_yield() == pytest.approx(100.0)


def test_a_FRACTIONAL_accel_dividend_is_paid_in_full_not_truncated():
    """ADR-0077 decision 3: `accel_units` is an EXPECTED count and arrives fractional, so the
    dividend must be linear across the range with no step at the integer boundaries."""
    bare = PromoteBody(reach=100.0)
    assert replace(bare, accel_units=2.5).my_yield() - bare.my_yield() \
        == pytest.approx(2.5 * ENERGY_RECOVER)
    # strictly increasing across an integer boundary — no truncation step
    yields = [replace(bare, accel_units=u).my_yield() for u in (1.75, 2.0, 2.25, 2.5)]
    assert yields == sorted(yields) and len(set(yields)) == 4


def test_a_fractional_dividend_below_one_unit_still_pays():
    """Truncation's worst case: a deck 0.8 of an Energy deep must not read identically to one
    provably empty. Zero stays zero only for a genuinely absent rider."""
    bare = PromoteBody(reach=100.0)
    assert replace(bare, accel_units=0.8).my_yield() > bare.my_yield()


# ---- decision 5: closure is a Δ`readiness_p` term, bounded by construction -------------------------

def test_closure_can_never_beat_actually_being_ready():
    """§5: `Δ <= 1` bounds the term below `damage(a)` by construction, so the property is structural
    rather than clamped; a body already reachable has Δ = 0 and earns no double credit."""
    ready = PromoteBody(reach=200.0, closure=0.0)
    one_card_short = PromoteBody(reach=0.0, closure=0.6 * 200.0)
    assert one_card_short.reach == 0.0
    assert pv(one_card_short).total < pv(ready).total
    assert pv(one_card_short).closure > 0.0               # but strictly better than nothing


def test_closure_is_monotonic_and_never_negative():
    grades = [pv(PromoteBody(closure=c)).closure for c in (0.0, 30.0, 90.0)]
    assert grades == sorted(grades)
    assert pv(PromoteBody(closure=-5.0)).closure == 0.0


# ---- decision 6: tempo_denied is derived from the Threat Clock, gated on live Items ---------------

def test_tempo_denied_is_the_threat_clock_step_gated_on_live_items():
    """§6: one development step's threat growth off the live curve, credited only when the opponent
    PROVABLY still holds Items — fail-CLOSED, because the term endorses a play."""
    locking = PromoteBody(reach=10.0, tempo_step=100.0, denies_items=True)
    unrecognised = replace(locking, denies_items=False)
    assert locking.tempo_denied() == pytest.approx(100.0)
    assert unrecognised.tempo_denied() == 0.0             # no matched Read -> no credit


def test_tempo_denied_fades_on_its_own_once_they_are_built():
    """The credit is how much their threat WOULD have grown, so it decays with no turn gate at all."""
    early = PromoteBody(tempo_step=120.0, denies_items=True)
    built = replace(early, tempo_step=0.0)
    assert built.tempo_denied() < early.tempo_denied()
    assert built.tempo_denied() == 0.0


# ---- decision 7: the endgame collapses to one dominance band ---------------------------------------

def test_a_fatal_promote_is_dominated_but_still_ordered():
    """§7a: subtracted at `KO_SCORE` as a finite BAND, not a veto — when EVERY option is fatal the
    residual must still order them, which a veto cannot."""
    fatal_weak = PromoteBody(reach=20.0, prizes=3, ko_active=1, opp_prizes_remaining=3)
    fatal_strong = replace(fatal_weak, reach=180.0)
    assert fatal_weak.fatal() == KO_SCORE
    assert pv(fatal_weak).total < 0 and pv(fatal_strong).total < 0     # both dominated
    assert pv(fatal_strong).total > pv(fatal_weak).total               # still ordered


def test_the_fatal_step_needs_the_clock_and_stands_down_on_a_trade():
    """Gated on §4's clock rather than the retired boolean, and stood down on a Knock-Out trade —
    trading while ahead is fine."""
    fatal = PromoteBody(prizes=3, ko_active=1, opp_prizes_remaining=3)
    assert replace(fatal, ko_active=2).fatal() == 0.0     # they cannot take it yet
    assert replace(fatal, takes_ko=True).fatal() == 0.0   # we are trading, not feeding


def test_near_goal_escalation_is_emergent_not_a_second_mechanism():
    """§7b: the fatal condition is `prizes >= opp_prizes_remaining`, so as their count falls more of
    our bodies become fatal automatically — modelling it twice would be two mechanisms for one effect."""
    two_prize = dict(prizes=2, ko_active=1)
    assert PromoteBody(**two_prize, opp_prizes_remaining=6).fatal() == 0.0
    assert PromoteBody(**two_prize, opp_prizes_remaining=3).fatal() == 0.0
    assert PromoteBody(**two_prize, opp_prizes_remaining=2).fatal() == KO_SCORE   # now fatal


def test_walking_onto_their_path_is_not_taxed_separately():
    """§7c: they attack the Active BECAUSE it is the Active, so path membership does not change
    whether it is hit — the flag is subsumed by `prizes x 100` plus the fatal step."""
    fields = set(PromoteBody().__dataclass_fields__)
    assert "on_their_path" not in fields


# ---- decision 8: build loss moved to the synthesized post-board -----------------------------------

def test_retreat_build_loss_is_owned_by_the_synthesized_post_board():
    """Issue #500 retires the local build recomposition; this seam keeps only resource premium."""
    assert RetreatSide().retreat_cost() == 0.0


def test_a_free_retreat_body_pays_nothing():
    """An Air Balloon (or a printed free retreat) discards no Energy, so it destroys no build and
    the free-pivot line is genuinely available."""
    assert RetreatSide().retreat_cost() == 0.0


def test_a_switch_class_item_pays_a_card_not_energy():
    """§11's rider: a Switch Item costs a CARD and no Energy, so it is priced by the same equation
    with the card's Worth as the cost rather than a build delta."""
    switch = RetreatSide(card_worth=10.0)
    assert switch.retreat_cost() == pytest.approx(10.0)


def test_the_resource_premium_rides_on_top_of_the_build_loss():
    """ADR-0069 §5c's premium — charged on worth ABOVE a reusable Basic, so a plain Basic pays
    nothing and only a one-shot is nudged."""
    plain = RetreatSide()
    one_shot = replace(plain, resource_premium=1.5)
    assert one_shot.retreat_cost() > plain.retreat_cost()


# ---- decision 9: ONE evaluator, and the A-side terms belong only to the whether-site ---------------

def test_the_pick_site_carries_no_a_side_terms():
    """§9: `preservation(A)` and `retreat_cost(A)` are CONSTANT across destinations, so they belong
    only on the whether-site's retreat option and could change no ordering at the pick site."""
    b = PromoteBody(reach=120.0, prizes=1, ko_active=2)
    pick = pv(b)
    assert pick.preservation == 0.0 and pick.retreat_cost == 0.0


def test_the_same_evaluator_answers_both_questions():
    """§9: with two paths the agent could retreat BECAUSE one body was worth promoting and then
    promote a different one. One evaluator makes the A-side terms a constant OFFSET, so no reorder."""
    a = RetreatSide(resource_premium=1.0)
    bodies = [PromoteBody(reach=r, prizes=1, ko_active=2) for r in (40.0, 130.0, 75.0)]
    pick_order = sorted(range(3), key=lambda i: -pv(bodies[i]).total)
    whether_order = sorted(range(3), key=lambda i: -pv(bodies[i], a).total)
    assert pick_order == whether_order


# ---- the two worked frames the user's counter-frames forced ----------------------------------------

def test_frame_mega_starmie_into_cinderace_retreats():
    """Exposure/preservation moved to canonical position; the residual cannot price it again."""
    cinderace = PromoteBody(reach=100.0, accel_units=3, prizes=1, ko_active=2)
    retreat = pv(cinderace, RetreatSide())
    assert retreat.preservation == retreat.exposure == 0.0
    assert retreat.total == cinderace.my_yield()


def test_frame_drakloak_into_budew_retreats():
    """ADR-0100's second worked frame: in rung currency `10 + 12` lost to a face-value 70; the tempo
    credit and the race discount price both honestly, so the retreat wins."""
    budew = PromoteBody(reach=10.0, prizes=1, ko_active=1, tempo_step=100.0, denies_items=True)
    drakloak_stays = PromoteBody(reach=70.0, wall_progress=320.0 / 5, prizes=1, ko_active=1)
    assert budew.my_yield() + budew.tempo_denied() > drakloak_stays.my_yield()


def test_frame_doomed_body_swapped_for_a_fresh_copy_of_itself():
    """The pure residual is equal; exact candidate position owns the survival difference."""
    fresh = PromoteBody(reach=170.0, prizes=3, ko_active=2)
    assert pv(fresh, RetreatSide()).total == pv(fresh).total


# ---- legibility (ADR-0019 full working) ------------------------------------------------------------

def test_total_is_the_transparent_sum_of_its_terms():
    """A wrong answer must be diagnosable term by term rather than as one number."""
    v = pv(PromoteBody(reach=120.0, wall_progress=None, accel_units=2, closure=30.0, prizes=2,
                       ko_active=2, tempo_step=40.0, denies_items=True,
                       opp_prizes_remaining=2),
           RetreatSide(resource_premium=1.5))
    assert v.total == pytest.approx(v.my_yield + v.closure - v.exposure + v.tempo_denied
                                    - v.fatal + v.preservation - v.retreat_cost)
