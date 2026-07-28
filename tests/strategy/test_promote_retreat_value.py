"""Promote/retreat DECIDER, PURE seam (common/promote_retreat_value.py) — ADR-0073, issue #141.

The design proof for the Sub-lethal Residual. Each test pins one of ADR-0073's twelve decisions as
an executable assertion, plus the two worked frames the user's counter-frames forced. This is seam
1 of the phase's three (pure function · live Pilot · gates): the equation is pure over MEASUREMENTS,
so every ruling is assertable here without constructing a board.

Deliberately NO test pins a raw score. 1c is a ~10x re-banding of the whole family, and ADR-0072's
rewrite of f29 from a score claim to a decision claim is the prior art for why: a magnitude target
would have to be re-tuned by the next phase and would say nothing about correctness. Every
assertion below is a RELATION — this beats that, this is bounded by that, this is zero.
"""
from __future__ import annotations

import csv
import statistics
from dataclasses import replace
from pathlib import Path

import pytest

from common.grading import HORIZON
from common.promote_retreat_value import (PRIZE_DAMAGE_RATE, PromoteBody, PromoteRetreatInputs,
                                          RetreatSide, promote_value)
from common.strategy.context import ENERGY_RECOVER, KO_SCORE

REPO = Path(__file__).resolve().parents[2]


def pv(body: PromoteBody, retreat: RetreatSide | None = None):
    return promote_value(PromoteRetreatInputs(body=body, retreat=retreat))


# ---- decision 1: the layers SUM, and nothing recuses --------------------------------------------

def test_no_ko_or_win_magnitude_is_representable():
    """§1/§4/§5: the residual is STRICTLY sub-lethal, which is what makes summing it with the
    tactical KO layer honest rather than double-paying. There is no win, lethal or KO-value field to
    pass, so a KO magnitude is structurally unrepresentable here — not merely unused."""
    fields = set(PromoteBody().__dataclass_fields__)
    assert not fields & {"win", "win_payoff", "lethal", "ko_value", "provable_win", "ko_score"}


def test_there_is_no_recusal_input():
    """§1: the shipped `active_can_ko` recusal is DELETED. A layer that cannot see a fact prices it
    0; it does not withdraw and leave the option unranked. So no input can suppress the equation."""
    fields = set(PromoteBody().__dataclass_fields__) | set(PromoteRetreatInputs().__dataclass_fields__)
    assert not fields & {"active_can_ko", "recuse", "abstain", "opp_can_punish"}


# ---- decision 2: `stay_forgone` is deleted — the option ranking IS the differential --------------

def test_stay_forgone_is_gone():
    """§2: subtracting the Active's forgone attack double-charged it, because at a MAIN menu that
    attack is its OWN option scoring `dmg - eff`. The subtraction relocates from a term into the
    comparison, which is strictly more accurate — so no field survives to re-introduce it."""
    fields = set(PromoteBody().__dataclass_fields__) | set(RetreatSide().__dataclass_fields__)
    assert not fields & {"stay_yield", "stay_forgone"}


# ---- decision 3: ONE currency, at a DERIVED rate -------------------------------------------------

def test_prize_damage_rate_recomputes_from_the_card_set():
    """§3: the Prize Damage Rate is DERIVED, so a reviewer can recompute it and a future set can
    re-derive it. This test IS that recomputation — the median HP-per-prize over every body in
    `data/EN_Card_Data.csv` at the `docs/rules.md` §6 prize values (Mega ex 3, ex 2, else 1).

    Pinning the literal instead would make the constant tuned-by-another-name."""
    prizes = {"n/a": 1, "Pokémon ex": 2, "Mega Pokémon ex": 3}
    bodies = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hp = int(row["HP"]) if (row.get("HP") or "").strip().isdigit() else 0
            if hp > 0:                                    # Trainers / Energy report no HP
                bodies[row["Card ID"]] = hp / prizes[(row.get("Rule") or "n/a").strip()]
    assert len(bodies) == 1061                            # the population ADR-0073 measured
    assert statistics.median(bodies.values()) == PRIZE_DAMAGE_RATE


def test_a_prize_is_worth_a_hundred_damage_not_twelve():
    """§3's whole point: exposing a 3-prize Mega Evolution Pokémon *ex* costs 300 damage, not the
    36 the superseded `_PRIZE_UNIT = 12` charged — which is why the shipped equation would feed the
    win condition to the opponent to gain a body that could attack."""
    mega = PromoteBody(prizes=3, ko_active=1)
    assert mega.exposure() == pytest.approx(300.0)


def test_the_attack_leg_is_race_discounted_against_a_standing_wall():
    """§3a: vs a standing wall the single hit is fake value — price the SEQUENCE. Drakloak's 70 into
    a 320 HP wall is a five-turn race, and crediting face-value chip would lose the retreat-to-Budew
    frame. When no wall reading applies, the reachable damage stands unchanged."""
    printed = PromoteBody(reach=70.0)
    racing = replace(printed, wall_progress=320.0 / 5)
    assert printed.my_yield() == pytest.approx(70.0)
    assert racing.my_yield() == pytest.approx(64.0)
    assert racing.my_yield() < printed.my_yield()


def test_the_accel_dividend_pays_what_the_attack_option_pays():
    """§3b: retreating INTO Cinderace must credit what attacking WITH Cinderace credits. The shipped
    `_DIVIDEND = 5` was ~45x short of the per-Energy value the SAME rider earns on the attack
    option, so the dividend re-anchors on `ENERGY_RECOVER` and is need-gated by the unit count."""
    bare = PromoteBody(reach=100.0)
    accel = replace(bare, accel_units=3)
    assert accel.my_yield() - bare.my_yield() == pytest.approx(3 * ENERGY_RECOVER)


def test_the_accel_dividend_is_zero_when_no_recipient_can_use_it():
    """The need gate is the count itself: Energy nobody can pay an attack with is not development,
    so an accelerator firing blanks onto a full-but-useless bench earns exactly nothing."""
    assert PromoteBody(reach=100.0, accel_units=0).my_yield() == pytest.approx(100.0)


def test_a_FRACTIONAL_accel_dividend_is_paid_in_full_not_truncated():
    """ADR-0076 decision 3: the deck-fuel leg is now `CountTriple.expected`, so `accel_units` is an
    EXPECTED count and arrives fractional. `my_yield` used to coerce it with `int(...)`, which floored
    2.5 to 2 and silently binned 0.5 x ENERGY_RECOVER = 37.5 points — a whole half-Energy of
    development, on the very frames the expectation exists to serve.

    The dividend must be linear in the units across the fractional range: an eighth of an Energy more
    fuel is an eighth of ENERGY_RECOVER more yield, with no step at the integer boundaries."""
    bare = PromoteBody(reach=100.0)
    assert replace(bare, accel_units=2.5).my_yield() - bare.my_yield() \
        == pytest.approx(2.5 * ENERGY_RECOVER)
    # strictly increasing across an integer boundary — no truncation step
    yields = [replace(bare, accel_units=u).my_yield() for u in (1.75, 2.0, 2.25, 2.5)]
    assert yields == sorted(yields) and len(set(yields)) == 4


def test_a_fractional_dividend_below_one_unit_still_pays():
    """The truncation's worst case: `int()` turned every sub-unit expectation into exactly zero, so a
    deck 0.8 of an Energy deep read identically to one provably empty. The floor stays at zero for a
    genuinely absent rider (the test above), but a real fraction is real value."""
    bare = PromoteBody(reach=100.0)
    assert replace(bare, accel_units=0.8).my_yield() > bare.my_yield()


# ---- decision 4: exposure is PER-BODY, CLOCK-GRADED and AREA-CORRECT ------------------------------

def test_exposure_is_continuous_in_the_clock_not_a_cliff():
    """§4: the retired `opp_can_punish` was BOOLEAN — a 300-damage cliff. A body one point short of
    being killable must not price identically to one that dies next turn, so exposure is graded by
    the clock and strictly decreasing in it."""
    grades = [PromoteBody(prizes=2, ko_active=t).exposure() for t in (1, 2, 3, 4)]
    assert grades == sorted(grades, reverse=True)
    assert len(set(grades)) == len(grades)                # strictly, not a plateau


def test_exposure_is_read_per_body():
    """§4: the retired read resolved MY best benched win-condition and applied that verdict to every
    candidate — the survival-read transposition of #137's "a Budget is PER-TARGET-BODY" hazard. Two
    candidates on one board with different prize values must price differently."""
    on_the_same_board = dict(ko_active=1, opp_prizes_remaining=6)
    mega = PromoteBody(prizes=3, **on_the_same_board)
    chump = PromoteBody(prizes=1, **on_the_same_board)
    assert mega.exposure() > chump.exposure()


def test_preservation_is_the_clock_difference_between_the_areas():
    """§4: what retreating BUYS is the body's exposure standing minus its exposure benched. B
    arrives in the ACTIVE area; A departs to the BENCH, whose leg is the Bench Harvest at the
    unavoidable (RESCUE) reading."""
    doomed = PromoteBody(prizes=3, ko_active=1, ko_bench=5)
    assert doomed.preservation() == pytest.approx(
        3 * PRIZE_DAMAGE_RATE * (1.0 - 0.5 ** 4))


def test_a_bench_immune_tera_body_earns_full_preservation_credit():
    """§4: card text, not tuning — "as long as this Pokémon is on your Bench, prevent all damage
    done to this Pokémon by attacks" (35 bodies in this set, including two in our own decks). Its
    bench clock is the full HORIZON, because benched it can only be reached by a gust."""
    tera = PromoteBody(prizes=2, ko_active=1, ko_bench=HORIZON)
    assert tera.preservation() == pytest.approx(2 * PRIZE_DAMAGE_RATE * (1.0 - 0.5 ** (HORIZON - 1)))
    assert tera.preservation() == pytest.approx(2 * PRIZE_DAMAGE_RATE, abs=1.0)


def test_preservation_is_zero_for_a_body_no_safer_on_the_bench():
    """A body the opponent reaches just as fast benched is not RESCUED by retreating, so retreating
    it banks nothing — and a bench clock reading shorter than the Active one is a redirect artefact,
    never a cost of retreating."""
    assert PromoteBody(prizes=3, ko_active=2, ko_bench=2).preservation() == 0.0
    assert PromoteBody(prizes=3, ko_active=4, ko_bench=1).preservation() == 0.0


# ---- decision 5: closure is a Δ`readiness_p` term, bounded by construction -------------------------

def test_closure_can_never_beat_actually_being_ready():
    """§5: `Δ <= 1` bounds the term below `damage(a)` by construction, so the shipped interim
    `min(1.0, p) x _READY` clamp disappears — the property becomes structural rather than clamped.
    A body already reachable has Δ = 0 and earns no double credit."""
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
    """§6: `_STALL` + `_ITEM_LOCK_TEMPO` paid 32 points for ONE card feature through ONE gate. The
    honest version is one development step's threat growth off the live curve, credited only when
    the opponent PROVABLY still holds Items — fail-CLOSED, because the term endorses a play."""
    locking = PromoteBody(reach=10.0, tempo_step=100.0, denies_items=True)
    unrecognised = replace(locking, denies_items=False)
    assert locking.tempo_denied() == pytest.approx(100.0)
    assert unrecognised.tempo_denied() == 0.0             # no matched Read -> no credit


def test_tempo_denied_fades_on_its_own_once_they_are_built():
    """The credit is how much their threat WOULD have grown, so it decays without a turn gate — the
    `turn <= 3` proxy the shipped `_item_lock_live` needed dies with it."""
    early = PromoteBody(tempo_step=120.0, denies_items=True)
    built = replace(early, tempo_step=0.0)
    assert built.tempo_denied() < early.tempo_denied()
    assert built.tempo_denied() == 0.0


# ---- decision 7: the endgame collapses to one dominance band ---------------------------------------

def test_a_fatal_promote_is_dominated_but_still_ordered():
    """§7a: subtracted at `KO_SCORE` — the constant that already means "dominates any sub-lethal
    quantity" — and a finite BAND, not a veto. When EVERY option is fatal the residual must still
    order them, which a veto cannot."""
    fatal_weak = PromoteBody(reach=20.0, prizes=3, ko_active=1, opp_prizes_remaining=3)
    fatal_strong = replace(fatal_weak, reach=180.0)
    assert fatal_weak.fatal() == KO_SCORE
    assert pv(fatal_weak).total < 0 and pv(fatal_strong).total < 0     # both dominated
    assert pv(fatal_strong).total > pv(fatal_weak).total               # still ordered


def test_the_fatal_step_needs_the_clock_and_stands_down_on_a_trade():
    """Gated on decision 4's clock rather than the retired boolean: they must actually be able to
    take it next turn. And it stands down on a Knock-Out trade — trading while ahead is fine
    (ruling 5)."""
    fatal = PromoteBody(prizes=3, ko_active=1, opp_prizes_remaining=3)
    assert replace(fatal, ko_active=2).fatal() == 0.0     # they cannot take it yet
    assert replace(fatal, takes_ko=True).fatal() == 0.0   # we are trading, not feeding


def test_near_goal_escalation_is_emergent_not_a_second_mechanism():
    """§7b: `_NEAR_GOAL`/`_GOAL_BAND` DELETE. The fatal condition is `prizes >= opp_prizes_remaining`,
    so as their count falls progressively more of our bodies become fatal automatically — the
    escalation is a consequence of the condition, and modelling it twice would be two mechanisms for
    one effect."""
    two_prize = dict(prizes=2, ko_active=1)
    assert PromoteBody(**two_prize, opp_prizes_remaining=6).fatal() == 0.0
    assert PromoteBody(**two_prize, opp_prizes_remaining=3).fatal() == 0.0
    assert PromoteBody(**two_prize, opp_prizes_remaining=2).fatal() == KO_SCORE   # now fatal


def test_walking_onto_their_path_is_not_taxed_separately():
    """§7c: `_PATH_TAX` DELETES as subsumed, on a card-mechanics argument — the promoted body
    becomes the ACTIVE, and they attack the Active BECAUSE it is the Active. Path membership does
    not change whether it is hit, and what the flag really encoded is now `prizes x 100` plus the
    fatal step."""
    fields = set(PromoteBody().__dataclass_fields__)
    assert "on_their_path" not in fields


# ---- decision 8: retreat cost is the BUILD it destroys ---------------------------------------------

def test_retreat_costs_the_build_the_discard_destroys():
    """§8: the exact mirror of the attach decider (1a prices an attach as `+build`; a retreat pays
    `-build`), so the two cannot disagree about what an Energy is worth. Worked: Mega Starmie ex at
    3/3 of Nebula Beam stands at 210; after paying retreat 2 it stands at (1/3)^2 x 210 = 23, so the
    retreat costs 187 damage of build — two turns of attaching thrown away."""
    built = RetreatSide(build_before=210.0, build_after=(1 / 3) ** 2 * 210.0)
    assert built.retreat_cost() == pytest.approx(187.0, abs=0.5)


def test_a_free_retreat_body_pays_nothing():
    """An Air Balloon (or a printed free retreat) discards no Energy, so it destroys no build and
    the free-pivot line is genuinely available."""
    assert RetreatSide(build_before=210.0, build_after=210.0).retreat_cost() == 0.0


def test_a_switch_class_item_pays_a_card_not_energy():
    """§11's rider: a Switch Item costs a CARD and no Energy, so it is priced by the same equation
    with the card's Worth as the cost rather than a build delta."""
    switch = RetreatSide(card_worth=10.0)
    assert switch.retreat_cost() == pytest.approx(10.0)


def test_the_resource_premium_rides_on_top_of_the_build_loss():
    """ADR-0069 §5c's premium — charged on worth ABOVE a reusable Basic, so a plain Basic pays
    nothing and only a one-shot is nudged."""
    plain = RetreatSide(build_before=100.0, build_after=40.0)
    one_shot = replace(plain, resource_premium=1.5)
    assert one_shot.retreat_cost() > plain.retreat_cost()


# ---- decision 9: ONE evaluator, and the A-side terms belong only to the whether-site ---------------

def test_the_pick_site_carries_no_a_side_terms():
    """§9: `preservation(A)` and `retreat_cost(A)` are CONSTANT across destinations, so they belong
    only on the whether-site's retreat option and are correctly absent from the pick site, where
    they could change no ordering. The forced promote likewise has no A-side terms at all."""
    b = PromoteBody(reach=120.0, prizes=1, ko_active=2)
    pick = pv(b)
    assert pick.preservation == 0.0 and pick.retreat_cost == 0.0


def test_the_same_evaluator_answers_both_questions():
    """§9: the whether-site priced the retreat off its own best-destination loop while a SEPARATE
    path picked the body at the follow-up SWITCH — so the agent could retreat BECAUSE one body was
    worth promoting and then promote a different one. One evaluator makes the A-side terms a
    constant OFFSET, which cannot reorder the destinations."""
    a = RetreatSide(body=PromoteBody(prizes=3, ko_active=1, ko_bench=HORIZON),
                    build_before=90.0, build_after=10.0)
    bodies = [PromoteBody(reach=r, prizes=1, ko_active=2) for r in (40.0, 130.0, 75.0)]
    pick_order = sorted(range(3), key=lambda i: -pv(bodies[i]).total)
    whether_order = sorted(range(3), key=lambda i: -pv(bodies[i], a).total)
    assert pick_order == whether_order


# ---- the two worked frames the user's counter-frames forced ----------------------------------------

def test_frame_mega_starmie_into_cinderace_retreats():
    """ADR-0073's first worked frame. Mega Starmie ex (3 prizes, doomed in the Active Spot) retreats
    into Cinderace (1 prize, 50 x2 Weakness, 3 accel). In rung currency it came out WRONG — the 3
    prizes preserved scored ZERO, so `their_yield` 12 vs `my_yield` 20 said stay. In damage the 300
    preserved prizes dominate and the retreat is right."""
    cinderace = PromoteBody(reach=100.0, accel_units=3, prizes=1, ko_active=2)
    starmie = PromoteBody(prizes=3, ko_active=1, ko_bench=HORIZON)
    retreat = pv(cinderace, RetreatSide(body=starmie))
    # 3 prizes x 100, less the residue of a bench clock that is long but not infinite (2^-8).
    assert retreat.preservation == pytest.approx(300.0, abs=2.0)
    assert retreat.total > 0                                     # retreat, not stay
    assert retreat.preservation > retreat.exposure               # and the prizes are WHY


def test_frame_drakloak_into_budew_retreats():
    """ADR-0073's second worked frame. Drakloak (70 damage into a 320 HP wall — a five-turn race)
    retreats into Budew (10 damage + an Item lock). In rung currency `10 + 12` lost to a face-value
    70; at the Threat-Clock tempo credit the lock is worth a development step and the race discount
    prices the chip honestly, so the retreat wins."""
    budew = PromoteBody(reach=10.0, prizes=1, ko_active=1, tempo_step=100.0, denies_items=True)
    drakloak_stays = PromoteBody(reach=70.0, wall_progress=320.0 / 5, prizes=1, ko_active=1)
    # Exposures cancel (both 1-prize bodies on the same clock), so the comparison is the yields.
    assert budew.exposure() == drakloak_stays.exposure()
    assert budew.my_yield() + budew.tempo_denied() > drakloak_stays.my_yield()


def test_frame_doomed_body_swapped_for_a_fresh_copy_of_itself():
    """§4's consequence: the identical Knock Out cancels and the clock DIFFERENCE decides. Retreating
    a doomed 3-prize attacker into a fresh copy of the same attacker takes the same KO either way —
    so the three prizes SAVED are the whole decision, and no new term is needed to see it."""
    fresh = PromoteBody(reach=170.0, prizes=3, ko_active=2)
    doomed = PromoteBody(reach=170.0, prizes=3, ko_active=1, ko_bench=HORIZON)
    assert pv(fresh, RetreatSide(body=doomed)).total > pv(fresh).total


# ---- legibility (ADR-0019 full working) ------------------------------------------------------------

def test_total_is_the_transparent_sum_of_its_terms():
    """A wrong answer must be diagnosable term by term rather than as one number."""
    v = pv(PromoteBody(reach=120.0, wall_progress=None, accel_units=2, closure=30.0, prizes=2,
                       ko_active=2, ko_bench=6, tempo_step=40.0, denies_items=True,
                       opp_prizes_remaining=2),
           RetreatSide(body=PromoteBody(prizes=3, ko_active=1, ko_bench=HORIZON),
                       build_before=210.0, build_after=23.0, resource_premium=1.5))
    assert v.total == pytest.approx(v.my_yield + v.closure - v.exposure + v.tempo_denied
                                    - v.fatal + v.preservation - v.retreat_cost)
