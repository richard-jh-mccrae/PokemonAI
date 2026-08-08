"""Snipe Relevance — the pure scorer, per LEG (ADR-0085, Issue #188).

Authored from the grill's worked examples, NOT from the corpus frames that chose the design: the
candidate shapes were fitted on those frames, so re-scoring the composite on them validates a fit
against itself. Every assertion is an ORDERING, never an intermediate magnitude (ADR-0080).
"""
import csv
import math
from dataclasses import replace
from pathlib import Path

import pytest

from common import snipe_relevance as sr
from common.snipe_relevance import MyRouteInputs as Route
from common.snipe_relevance import TheirPlanInputs as Plan

REPO = Path(__file__).resolve().parents[2]

# Card facts VERIFIED at source (data/EN_Card_Data.csv): 678 Mega Lucario ex 340 HP / Mega Brave 270,
# a SINGLE hop from 677 Riolu 80 HP; 676 Solrock 110 HP; 1031 Jetting Blow 120 + 50 rider, Nebula 210.
MEGA_LUCARIO_HP, MEGA_LUCARIO_FWD = 340, 270
RIOLU_HP, RIOLU_FWD = 80, 270          # a Riolu's line reaches Mega Lucario ex
SOLROCK_HP, SOLROCK_FWD = 110, 0       # ...and a Solrock's reaches nothing
RIDER = 50                             # Jetting Blow's bench-snipe rider


@pytest.mark.req("REQ-SNIPEREL-0001")
def test_the_normalizer_is_recomputed_from_the_card_set_not_pinned():
    """ADR-0085 Amendment A1 / ADR-0080 Amendment B."""
    best = 0
    with (REPO / "data" / "EN_Card_Data.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            dmg = (row.get("Damage") or "").strip().rstrip("+x×")
            if dmg.isdigit():
                best = max(best, int(dmg))
    assert sr.MAX_ATTACK_DAMAGE == float(best)
    assert sr.K == sr.MAX_ATTACK_DAMAGE, "K must BE the normalizer, not a second constant"


@pytest.mark.req("REQ-SNIPEREL-0002")
def test_k_times_relevance_recovers_damage_so_the_exit_introduces_no_parameter():
    assert sr.K * sr.normalize(270) == pytest.approx(270.0)
    assert sr.K * sr.normalize(0) == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────── the impossibility pair

@pytest.mark.req("REQ-SNIPEREL-0003")
def test_identical_magnitudes_opposite_rulings_are_separated_by_the_categorical_read():
    """Two frames, identical arithmetic on both sides, opposite human rulings — so any
    magnitude-shaped successor fails by construction. `prize_redundant` is what separates them."""
    mega_route = Route(hp_remaining=MEGA_LUCARIO_HP, rider_damage=RIDER,
                       prize_value=3, prizes_needed=6,
                       turns_to_ko_before=3.0, turns_to_ko_after=2.0)
    # a live threat
    mega_57 = sr.target_relevance(plan=Plan(incoming_damage=270, turns_to_afford=1,
                                            prize_redundant=False), route=mega_route)
    # the opponent's redundant SECOND copy
    mega_107 = sr.target_relevance(plan=Plan(incoming_damage=270, turns_to_afford=1,
                                             prize_redundant=True), route=mega_route)

    makuhita = sr.target_relevance(
        plan=Plan(incoming_damage=30, turns_to_afford=3),
        route=Route(hp_remaining=RIOLU_HP, rider_damage=RIDER,
                    prize_value=1, prizes_needed=6,
                    turns_to_ko_before=1.0, turns_to_ko_after=1.0))

    assert mega_57["relevance"] > makuhita["relevance"], "57: the live Mega outranks the small"
    assert mega_107["relevance"] < makuhita["relevance"], "107: the redundant copy stands down"


# ─────────────────────────────────────────────────────────────── their_plan legs

@pytest.mark.req("REQ-SNIPEREL-0004")
def test_a_pre_evo_carrying_a_wincon_outranks_one_carrying_nothing():
    """Raw CURRENT-form damage orders these backwards (Solrock's 110 HP out-bulks Riolu's 80), which
    is why the forward leg reads the LINE rather than the body."""
    riolu = sr.target_relevance(
        plan=Plan(forward_damage=RIOLU_FWD, is_strongest_forward=True),
        route=Route(hp_remaining=RIOLU_HP, rider_damage=RIDER, prize_value=1))
    solrock = sr.target_relevance(
        plan=Plan(forward_damage=SOLROCK_FWD, is_strongest_forward=False),
        route=Route(hp_remaining=SOLROCK_HP, rider_damage=RIDER, prize_value=1))
    assert riolu["relevance"] > solrock["relevance"]
    assert solrock["forward"] == 0.0


@pytest.mark.req("REQ-SNIPEREL-0004")
def test_the_forward_leg_stands_down_once_the_evolved_wincon_is_already_in_play():
    """ADR-0044's discriminator: chip the READY form, not the redundant pre-evo."""
    developing = sr.target_relevance(plan=Plan(forward_damage=RIOLU_FWD, is_strongest_forward=True,
                                               forward_form_in_play=False), route=Route())
    already_out = sr.target_relevance(plan=Plan(forward_damage=RIOLU_FWD, is_strongest_forward=True,
                                                forward_form_in_play=True), route=Route())
    assert developing["forward"] > 0.0
    assert already_out["forward"] == 0.0


@pytest.mark.req("REQ-SNIPEREL-0005")
def test_the_forced_promotion_leg_is_graded_and_cannot_bury_a_developing_wincon():
    """A flat 1.0 saturates this leg and beats the forward read, taking the harmless forced promotion
    over a real developing win-condition."""
    harmless_forced = sr.target_relevance(
        plan=Plan(incoming_damage=20, is_forced_promotion=True),
        route=Route(hp_remaining=SOLROCK_HP, rider_damage=RIDER))
    developing_wincon = sr.target_relevance(
        plan=Plan(forward_damage=RIOLU_FWD, is_strongest_forward=True),
        route=Route(hp_remaining=RIOLU_HP, rider_damage=RIDER))
    assert developing_wincon["relevance"] > harmless_forced["relevance"]
    assert harmless_forced["forced"] < 1.0, "a saturating constant is the defect this covers"


@pytest.mark.req("REQ-SNIPEREL-0005")
def test_a_dangerous_forced_promotion_still_outranks_a_harmless_one():
    route = Route(hp_remaining=200, rider_damage=RIDER)
    scary = sr.target_relevance(plan=Plan(incoming_damage=300, is_forced_promotion=True),
                                route=route)
    mild = sr.target_relevance(plan=Plan(incoming_damage=20, is_forced_promotion=True),
                               route=route)
    assert scary["relevance"] > mild["relevance"]


@pytest.mark.req("REQ-SNIPEREL-0005")
def test_the_forced_promotion_leg_takes_no_imminence_discount():
    """A forced promotion IS the timing claim, so `turns_to_afford` on top double-counts it."""
    far = sr.target_relevance(plan=Plan(incoming_damage=200, turns_to_afford=3,
                                        is_forced_promotion=True), route=Route())
    near = sr.target_relevance(plan=Plan(incoming_damage=200, turns_to_afford=0,
                                         is_forced_promotion=True), route=Route())
    assert far["forced"] == near["forced"] > 0.0


@pytest.mark.req("REQ-SNIPEREL-0006")
def test_imminence_subsumes_the_energized_tier_without_a_tier_constant():
    """`_ENERGIZED_SNIPE_TIER = 100000` retires as SUBSUMED, not re-expressed."""
    route = Route(hp_remaining=200, rider_damage=RIDER)
    armed = sr.target_relevance(plan=Plan(incoming_damage=200, turns_to_afford=0), route=route)
    latent = sr.target_relevance(plan=Plan(incoming_damage=200, turns_to_afford=3), route=route)
    assert armed["relevance"] > latent["relevance"]


@pytest.mark.req("REQ-SNIPEREL-0007")
def test_the_adr_0044_reads_are_leg_scoped_and_do_not_zero_the_whole_target():
    """ADR-0085 decision 4: a mirage-flagged body still scores through the FORWARD leg, because a
    whole-target gate makes the frames where the human picks exactly such a body unreachable."""
    mirage_wincon = sr.target_relevance(
        plan=Plan(incoming_damage=200, turns_to_afford=0,
                  forward_damage=RIOLU_FWD, is_strongest_forward=True, promotion_mirage=True),
        route=Route(hp_remaining=RIOLU_HP, rider_damage=RIDER))
    assert mirage_wincon["imminence"] == 0.0, "the imminence claim IS suppressed"
    assert mirage_wincon["forward"] > 0.0, "...but the developing-wincon claim survives"
    assert mirage_wincon["relevance"] > 0.0


@pytest.mark.req("REQ-SNIPEREL-0007")
def test_prize_redundancy_suppresses_imminence_the_same_way():
    route = Route(hp_remaining=200, rider_damage=RIDER)
    redundant = sr.target_relevance(plan=Plan(incoming_damage=270, turns_to_afford=0,
                                              prize_redundant=True), route=route)
    live = sr.target_relevance(plan=Plan(incoming_damage=270, turns_to_afford=0,
                                         prize_redundant=False), route=route)
    assert redundant["imminence"] == 0.0 < live["imminence"]


# ─────────────────────────────────────────────────────────────── the Brief asymmetry

@pytest.mark.req("REQ-SNIPEREL-0008")
def test_a_positive_brief_boost_sharpens_but_stands_down_on_the_adr_0044_reads():
    """A Brief MULTIPLIES the derived rank and must never reach a body ADR-0044 says to skip, or
    authored scouting overrides the read instead of sharpening it (ADR-0085 decision 5 / Amdt A3)."""
    # `brief_boost` is the CALLER's `_BRIEF_THREAT_BOOST`; the scorer reads only the priority's SIGN.
    plan = Plan(incoming_damage=200, turns_to_afford=0)
    base = dict(route=Route(hp_remaining=200, rider_damage=RIDER), brief_boost=1.25)
    plain = sr.target_relevance(plan=plan, **base)
    briefed = sr.target_relevance(plan=replace(plan, brief_priority=1.0), **base)
    briefed_mirage = sr.target_relevance(
        plan=replace(plan, brief_priority=1.0, promotion_mirage=True), **base)
    briefed_tera = sr.target_relevance(
        plan=replace(plan, brief_priority=1.0, is_tera=True), **base)
    assert briefed["relevance"] > plain["relevance"]
    assert briefed["brief_multiplier"] == pytest.approx(1.25), "the caller's constant, not a new one"
    assert briefed_mirage["brief_multiplier"] == 1.0
    assert briefed_tera["brief_multiplier"] == 1.0


@pytest.mark.req("REQ-SNIPEREL-0008")
def test_a_negative_avoid_priority_always_applies_even_on_a_gated_body():
    """De-prioritising is safe regardless of the gates; boosting is not."""
    plan = Plan(incoming_damage=200, turns_to_afford=0, brief_priority=-1.0)
    base = dict(route=Route(hp_remaining=200, rider_damage=RIDER), brief_boost=1.25)
    avoided = sr.target_relevance(plan=plan, **base)
    avoided_gated = sr.target_relevance(plan=replace(plan, is_tera=True), **base)
    assert avoided["brief_multiplier"] < 1.0
    assert avoided_gated["brief_multiplier"] < 1.0
    # ONE constant governs both directions — the suppression is the boost's mirror.
    assert avoided["brief_multiplier"] == pytest.approx(1 / 1.25)


@pytest.mark.req("REQ-SNIPEREL-0008")
def test_a_brief_can_never_promote_a_whiff():
    whiff = sr.target_relevance(plan=Plan(incoming_damage=0, brief_priority=10.0),
                                route=Route(hp_remaining=200, rider_damage=RIDER),
                                brief_boost=1.25)
    assert whiff["relevance"] == 0.0


# ─────────────────────────────────────────────────────────────── my_route legs

@pytest.mark.req("REQ-SNIPEREL-0009")
def test_a_chip_that_removes_no_turn_scores_nothing_on_the_ko_delta_leg():
    assert math.ceil(MEGA_LUCARIO_HP / 210) == 2
    assert math.ceil((MEGA_LUCARIO_HP - RIDER) / 210) == 2
    assert sr.ko_delta(2.0, 2.0) == 0.0


@pytest.mark.req("REQ-SNIPEREL-0009")
def test_the_two_chip_window_credits_a_threshold_the_first_chip_alone_misses():
    """A one-chip-only read scores the human's answer at zero wherever two chips save the turn."""
    assert sr.ko_delta(3.0, 3.0) == 0.0          # one chip: 340 -> 290, still 3
    assert sr.ko_delta(3.0, 2.0) > 0.0           # two chips: 340 -> 240, now 2


@pytest.mark.req("REQ-SNIPEREL-0009")
def test_ko_delta_is_zero_when_my_active_cannot_damage_the_body_at_all():
    """Fail-CLOSED: an infeasible kill is no route to shorten, not a maximal one."""
    assert sr.ko_delta(None, None) == 0.0
    assert sr.ko_delta(0, None) == 0.0


@pytest.mark.req("REQ-SNIPEREL-0010")
def test_rider_reach_prefers_the_body_my_repeatable_rider_finishes_soonest():
    assert sr.rider_reach(80, RIDER) == pytest.approx(1 / 2)
    assert sr.rider_reach(110, RIDER) == pytest.approx(1 / 3)
    assert sr.rider_reach(80, RIDER) > sr.rider_reach(110, RIDER)
    assert sr.rider_reach(80, 0) == 0.0


@pytest.mark.req("REQ-SNIPEREL-0010")
def test_prize_share_saturates_rather_than_overshooting_my_requirement():
    assert sr.prize_share(3, 6) == pytest.approx(0.5)
    assert sr.prize_share(3, 2) == 1.0
    assert sr.prize_share(1, 0) == 0.0


@pytest.mark.req("REQ-SNIPEREL-0011")
def test_a_line_that_will_become_immune_to_my_ex_attacker_is_maximal_route_now():
    """`_PREVENT_EX_SNIPE_BOOST` re-homed (ADR-0085 decision 9): the evolved form closes my route
    permanently rather than hitting harder, so this is a route fact, not a threat magnitude."""
    plan = Plan(incoming_damage=100, turns_to_afford=1)
    closing = sr.target_relevance(plan=plan, route=Route(hp_remaining=120, rider_damage=RIDER,
                                                         prevents_my_ex=True))
    ordinary = sr.target_relevance(plan=plan, route=Route(hp_remaining=120, rider_damage=RIDER,
                                                          prevents_my_ex=False))
    assert closing["my_route"] == 1.0
    assert closing["relevance"] > ordinary["relevance"]


# ─────────────────────────────────────────────────────────────── the composition itself

@pytest.mark.req("REQ-SNIPEREL-0012")
def test_the_two_sides_are_conjunctive_so_either_alone_is_worthless():
    """A PRODUCT, not deny's flat `max`."""
    scary_no_route = sr.target_relevance(
        plan=Plan(incoming_damage=350, turns_to_afford=0),
        route=Route(hp_remaining=0, rider_damage=0, prize_value=0, prizes_needed=6,
                    turns_to_ko_before=None, turns_to_ko_after=None))
    harmless_on_route = sr.target_relevance(
        plan=Plan(incoming_damage=0, turns_to_afford=None),
        route=Route(hp_remaining=50, rider_damage=RIDER, prize_value=3, prizes_needed=3))
    assert scary_no_route["relevance"] == 0.0
    assert harmless_on_route["relevance"] == 0.0


@pytest.mark.req("REQ-SNIPEREL-0012")
def test_no_sum_of_positional_legs_can_out_vote_a_single_stronger_one():
    """The deleted additive stack's blunder class, made UNREPRESENTABLE rather than capped: under a
    max-within-a-side product the score is bounded by the best claim, never by a sum of claims."""
    route = Route(hp_remaining=100, rider_damage=RIDER, prize_value=1)
    three_mid = sr.target_relevance(
        plan=Plan(incoming_damage=120, turns_to_afford=0, forward_damage=120,
                  is_strongest_forward=True, is_forced_promotion=True), route=route)
    one_high = sr.target_relevance(plan=Plan(incoming_damage=340, turns_to_afford=0), route=route)
    assert one_high["their_plan"] > three_mid["their_plan"]


@pytest.mark.req("REQ-SNIPEREL-0012")
def test_relevance_stays_inside_the_unit_band():
    """The [0,1] band is the contract every consumer scales against."""
    maxed = sr.target_relevance(
        plan=Plan(incoming_damage=10_000, turns_to_afford=0, brief_priority=99.0),
        route=Route(hp_remaining=10, rider_damage=RIDER, prize_value=9, prizes_needed=1,
                    turns_to_ko_before=3.0, turns_to_ko_after=0.0, prevents_my_ex=True),
        brief_boost=1.25)
    assert 0.0 <= maxed["relevance"] <= 1.0
    assert 0.0 <= maxed["their_plan"] <= 1.0
    assert 0.0 <= maxed["my_route"] <= 1.0


@pytest.mark.req("REQ-SNIPEREL-0012")
def test_the_scorer_never_zeroes_on_tera_because_the_veto_is_an_ordering():
    """`Pilot._snipe_tera_veto` expresses the immunity (`rules.md §185`) as `-KO_SCORE` ORDERING, not
    removal, because a lone benched Tera is a FORCED select — so this module must not zero it."""
    tera = sr.target_relevance(plan=Plan(incoming_damage=200, turns_to_afford=0, is_tera=True),
                               route=Route(hp_remaining=200, rider_damage=RIDER))
    assert tera["relevance"] > 0.0
