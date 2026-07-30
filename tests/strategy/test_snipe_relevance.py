"""Snipe Relevance — the pure scorer (ADR-0083, Issue #188).

Authored from the grill's WORKED EXAMPLES rather than harvested from the 19 corpus frames that chose
the design (ADR-0083 decision 7 bar 4, mirroring ADR-0080's "the five worked examples become the
acceptance fixtures"). The distinction is load-bearing: ~12 scorer shapes were measured against those
19 frames during the grill, so re-scoring the composite on them validates a fit against itself. These
assert per-LEG behaviour, which is the gap that let Lillie's Clefairy ex be right-for-the-wrong-reason
in the shipped rungs.

Every assertion is an ORDERING or a decision, never an intermediate magnitude — relevance numbers are
not a contract (the ADR-0080 `math.nextafter` discipline).
"""
import csv
import math
from pathlib import Path

import pytest

from common import snipe_relevance as sr

REPO = Path(__file__).resolve().parents[2]

# Card facts VERIFIED AT SOURCE (data/EN_Card_Data.csv, CLAUDE.md's cardinal rule):
#   678 Mega Lucario ex   Stage 1, 340 HP, evolves from Riolu (a SINGLE hop — no intermediate
#                         Lucario in this set), Aura Jab {F} 130 / Mega Brave {F}{F} 270
#   677 Riolu             Basic, 80 HP, Accelerating Stab {F} 30
#   676 Solrock           Basic, 110 HP — Cosmic Beam does nothing without Lunatone benched
#   673 Makuhita          Basic, 80 HP -> Hariyama (secondary line)
#   1031 Mega Starmie ex  Jetting Blow {W} 120 (50 bench rider), Nebula Beam (dot x3) 210
MEGA_LUCARIO_HP, MEGA_LUCARIO_FWD = 340, 270
RIOLU_HP, RIOLU_FWD = 80, 270          # a Riolu's line reaches Mega Lucario ex
SOLROCK_HP, SOLROCK_FWD = 110, 0       # ...and a Solrock's reaches nothing
RIDER = 50                             # Jetting Blow's bench-snipe rider


@pytest.mark.req("REQ-SNIPEREL-0001")
def test_the_normalizer_is_recomputed_from_the_card_set_not_pinned():
    """`K` is the exit rate back to the damage scale AND the normalizer, identical by construction
    (ADR-0083 Amendment A1 / ADR-0080 Amendment B). Recomputed from the CSV rather than pinned, so a
    future set re-derives it — the property that makes it falsifiable is the point."""
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
    """The identity that makes the exit a strict generalisation rather than a re-scaling: since
    relevance is `setback / MAX_ATTACK_DAMAGE`, `K x relevance` is the setback back in DAMAGE."""
    assert sr.K * sr.normalize(270) == pytest.approx(270.0)
    assert sr.K * sr.normalize(0) == pytest.approx(0.0)


# ─────────────────────────────────────────── the impossibility pair (82756021-57 / 83667237-107)

@pytest.mark.req("REQ-SNIPEREL-0003")
def test_identical_magnitudes_opposite_rulings_are_separated_by_the_categorical_read():
    """THE acceptance fixture. Both frames offer an 80-HP 1-prize Makuhita against a 340-HP 3-prize
    Mega Lucario ex at identical rider and identical turns-to-finish, and the human rules them
    OPPOSITE ways. Any magnitude-shaped successor fails this by construction — the arithmetic is the
    same on both sides. What separates them is `target_prize_redundant` (ADR-0044's body-identity
    Prize-Path read: on `107` the Mega is the opponent's redundant SECOND copy, off my path)."""
    common = dict(incoming_damage=270, turns_to_afford=1, hp_remaining=MEGA_LUCARIO_HP,
                  rider_damage=RIDER, prize_value=3, prizes_needed=6,
                  turns_to_ko_before=3.0, turns_to_ko_after=2.0)
    mega_57 = sr.target_relevance(**common, prize_redundant=False)   # 82756021-57: a live threat
    mega_107 = sr.target_relevance(**common, prize_redundant=True)   # 83667237-107: the 2nd copy

    makuhita = sr.target_relevance(incoming_damage=30, turns_to_afford=3,
                                   hp_remaining=RIOLU_HP, rider_damage=RIDER,
                                   prize_value=1, prizes_needed=6,
                                   turns_to_ko_before=1.0, turns_to_ko_after=1.0)

    assert mega_57["relevance"] > makuhita["relevance"], "57: the live Mega outranks the small"
    assert mega_107["relevance"] < makuhita["relevance"], "107: the redundant copy stands down"


# ─────────────────────────────────────────────────────────────── their_plan legs

@pytest.mark.req("REQ-SNIPEREL-0004")
def test_a_pre_evo_carrying_a_wincon_outranks_one_carrying_nothing():
    """The forward leg, and ADR-0080's own worked pair pointed at snipe: a Riolu banks toward Mega
    Lucario ex (Mega Brave 270) while a Solrock's line reaches nothing at all. Raw CURRENT-form
    damage orders these backwards — Solrock's 110 HP body out-bulks the 80-HP Riolu — which is why
    the leg reads the line rather than the body."""
    riolu = sr.target_relevance(forward_damage=RIOLU_FWD, is_strongest_forward=True,
                                hp_remaining=RIOLU_HP, rider_damage=RIDER, prize_value=1)
    solrock = sr.target_relevance(forward_damage=SOLROCK_FWD, is_strongest_forward=False,
                                  hp_remaining=SOLROCK_HP, rider_damage=RIDER, prize_value=1)
    assert riolu["relevance"] > solrock["relevance"]
    assert solrock["forward"] == 0.0


@pytest.mark.req("REQ-SNIPEREL-0004")
def test_the_forward_leg_stands_down_once_the_evolved_wincon_is_already_in_play():
    """ADR-0044's discriminator: chip the READY form directly, not the redundant pre-evo. The exact
    case a naive restore of `snipe-the-evolving-threat` regressed (test_45 / test_107)."""
    developing = sr.target_relevance(forward_damage=RIOLU_FWD, is_strongest_forward=True,
                                     forward_form_in_play=False)
    already_out = sr.target_relevance(forward_damage=RIOLU_FWD, is_strongest_forward=True,
                                      forward_form_in_play=True)
    assert developing["forward"] > 0.0
    assert already_out["forward"] == 0.0


@pytest.mark.req("REQ-SNIPEREL-0005")
def test_the_forced_promotion_leg_is_graded_and_cannot_bury_a_developing_wincon():
    """The `ms_snipe_evolving_wincon_preevo_f75` defect, pinned. A flat 1.0 on this leg saturates it
    and beats the Riolu's forward read, so the prototype took card 676 Solrock — the forced
    promotion — over card 677 Riolu, which is the fixture's ruling. Graded on the promoted body's own
    curve threat, a harmless forced promotion loses to a real developing win-condition."""
    harmless_forced = sr.target_relevance(incoming_damage=20, is_forced_promotion=True,
                                          hp_remaining=SOLROCK_HP, rider_damage=RIDER)
    developing_wincon = sr.target_relevance(forward_damage=RIOLU_FWD, is_strongest_forward=True,
                                            hp_remaining=RIOLU_HP, rider_damage=RIDER)
    assert developing_wincon["relevance"] > harmless_forced["relevance"]
    assert harmless_forced["forced"] < 1.0, "a saturating constant is the defect this pins"


@pytest.mark.req("REQ-SNIPEREL-0005")
def test_a_dangerous_forced_promotion_still_outranks_a_harmless_one():
    """The leg still does its ADR-0044 job — it is graded, not neutered."""
    scary = sr.target_relevance(incoming_damage=300, is_forced_promotion=True,
                                hp_remaining=200, rider_damage=RIDER)
    mild = sr.target_relevance(incoming_damage=20, is_forced_promotion=True,
                               hp_remaining=200, rider_damage=RIDER)
    assert scary["relevance"] > mild["relevance"]


@pytest.mark.req("REQ-SNIPEREL-0005")
def test_the_forced_promotion_leg_takes_no_imminence_discount():
    """A forced promotion IS the timing claim — the body attacks next turn by definition — so
    applying `turns_to_afford` on top double-counts the ADR-0044 read that established it."""
    far = sr.target_relevance(incoming_damage=200, turns_to_afford=3, is_forced_promotion=True)
    near = sr.target_relevance(incoming_damage=200, turns_to_afford=0, is_forced_promotion=True)
    assert far["forced"] == near["forced"] > 0.0


@pytest.mark.req("REQ-SNIPEREL-0006")
def test_imminence_subsumes_the_energized_tier_without_a_tier_constant():
    """`_ENERGIZED_SNIPE_TIER = 100000` retires as SUBSUMED, not re-expressed. An armed body
    (`turns_to_afford` 0) outranks an equally-large body three turns from attacking, purely through
    the graded discount."""
    armed = sr.target_relevance(incoming_damage=200, turns_to_afford=0,
                                hp_remaining=200, rider_damage=RIDER)
    latent = sr.target_relevance(incoming_damage=200, turns_to_afford=3,
                                 hp_remaining=200, rider_damage=RIDER)
    assert armed["relevance"] > latent["relevance"]


@pytest.mark.req("REQ-SNIPEREL-0007")
def test_the_adr_0044_reads_are_leg_scoped_and_do_not_zero_the_whole_target():
    """Decision 4, and the correction to decision 1's original framing. A mirage-flagged body still
    scores through the FORWARD leg — three corpus frames (`81905522-75`, `82523811-41`,
    `85164131-22`) have the human picking exactly such a body, and a whole-target gate makes them
    unreachable."""
    mirage_wincon = sr.target_relevance(incoming_damage=200, turns_to_afford=0,
                                        forward_damage=RIOLU_FWD, is_strongest_forward=True,
                                        promotion_mirage=True,
                                        hp_remaining=RIOLU_HP, rider_damage=RIDER)
    assert mirage_wincon["imminence"] == 0.0, "the imminence claim IS suppressed"
    assert mirage_wincon["forward"] > 0.0, "...but the developing-wincon claim survives"
    assert mirage_wincon["relevance"] > 0.0


@pytest.mark.req("REQ-SNIPEREL-0007")
def test_prize_redundancy_suppresses_imminence_the_same_way():
    redundant = sr.target_relevance(incoming_damage=270, turns_to_afford=0, prize_redundant=True,
                                    hp_remaining=200, rider_damage=RIDER)
    live = sr.target_relevance(incoming_damage=270, turns_to_afford=0, prize_redundant=False,
                               hp_remaining=200, rider_damage=RIDER)
    assert redundant["imminence"] == 0.0 < live["imminence"]


# ─────────────────────────────────────────────────────────────── the Brief asymmetry

@pytest.mark.req("REQ-SNIPEREL-0008")
def test_a_positive_brief_boost_sharpens_but_stands_down_on_the_adr_0044_reads():
    """ADR-0083 decision 5 + Amendment A3. A matched Brief MULTIPLIES the derived rank; it must never
    reach a body ADR-0044 says to skip, or authored scouting starts overriding the read instead of
    sharpening it."""
    base = dict(incoming_damage=200, turns_to_afford=0, hp_remaining=200, rider_damage=RIDER)
    plain = sr.target_relevance(**base)
    briefed = sr.target_relevance(**base, brief_priority=0.25)
    briefed_mirage = sr.target_relevance(**base, brief_priority=0.25, promotion_mirage=True)
    briefed_tera = sr.target_relevance(**base, brief_priority=0.25, is_tera=True)
    assert briefed["relevance"] > plain["relevance"]
    assert briefed_mirage["brief_multiplier"] == 1.0
    assert briefed_tera["brief_multiplier"] == 1.0


@pytest.mark.req("REQ-SNIPEREL-0008")
def test_a_negative_avoid_priority_always_applies_even_on_a_gated_body():
    """The asymmetry is deliberate: de-prioritising a draw engine is safe regardless of the gates,
    while boosting is not."""
    base = dict(incoming_damage=200, turns_to_afford=0, hp_remaining=200, rider_damage=RIDER)
    avoided = sr.target_relevance(**base, brief_priority=-0.5)
    avoided_gated = sr.target_relevance(**base, brief_priority=-0.5, is_tera=True)
    assert avoided["brief_multiplier"] < 1.0
    assert avoided_gated["brief_multiplier"] < 1.0


@pytest.mark.req("REQ-SNIPEREL-0008")
def test_a_brief_can_never_promote_a_whiff():
    """`0 x anything is 0` — the property `_BRIEF_THREAT_BOOST` relies on, carried over verbatim."""
    whiff = sr.target_relevance(incoming_damage=0, brief_priority=10.0,
                                hp_remaining=200, rider_damage=RIDER)
    assert whiff["relevance"] == 0.0


# ─────────────────────────────────────────────────────────────── my_route legs

@pytest.mark.req("REQ-SNIPEREL-0009")
def test_a_chip_that_removes_no_turn_scores_nothing_on_the_ko_delta_leg():
    """The user's ruling, verified against the real card facts: Mega Lucario ex 340 HP against Mega
    Starmie ex's Nebula Beam 210 is a 2-turn kill; a 50-damage snipe leaves 290, still 2 turns. The
    chip achieves nothing and the leg says so."""
    assert math.ceil(MEGA_LUCARIO_HP / 210) == 2
    assert math.ceil((MEGA_LUCARIO_HP - RIDER) / 210) == 2
    assert sr.ko_delta(2.0, 2.0) == 0.0


@pytest.mark.req("REQ-SNIPEREL-0009")
def test_the_two_chip_window_credits_a_threshold_the_first_chip_alone_misses():
    """`82756021-57`, load-bearing: the 340-HP Mega has `turns_to_ko` 3 against an Active that can
    only afford Jetting Blow 120. One chip saves nothing; two save a turn — and the human takes it.
    A one-chip-only read scores that frame's correct answer at zero."""
    assert sr.ko_delta(3.0, 3.0) == 0.0          # one chip: 340 -> 290, still 3
    assert sr.ko_delta(3.0, 2.0) > 0.0           # two chips: 340 -> 240, now 2


@pytest.mark.req("REQ-SNIPEREL-0009")
def test_ko_delta_is_zero_when_my_active_cannot_damage_the_body_at_all():
    """Fail-closed: an infeasible kill is no route to shorten, not a maximal one."""
    assert sr.ko_delta(None, None) == 0.0
    assert sr.ko_delta(0, None) == 0.0


@pytest.mark.req("REQ-SNIPEREL-0010")
def test_rider_reach_prefers_the_body_my_repeatable_rider_finishes_soonest():
    """`snipe_prize_reach`'s arithmetic: Makuhita at 80 HP is two Jetting Blow riders; Lunatone at
    110 is three, so it needs a dedicated gust-up instead of riding along."""
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
    """`_PREVENT_EX_SNIPE_BOOST` re-homed (decision 9). Dwebble -> Crustle does not hit me HARDER
    once evolved — it becomes immune to my ex attacker, closing my route through it permanently. A
    route fact, not a threat magnitude, and this turn is the last one in which the route exists."""
    closing = sr.target_relevance(incoming_damage=100, turns_to_afford=1,
                                  hp_remaining=120, rider_damage=RIDER, prevents_my_ex=True)
    ordinary = sr.target_relevance(incoming_damage=100, turns_to_afford=1,
                                   hp_remaining=120, rider_damage=RIDER, prevents_my_ex=False)
    assert closing["my_route"] == 1.0
    assert closing["relevance"] > ordinary["relevance"]


# ─────────────────────────────────────────────────────────────── the composition itself

@pytest.mark.req("REQ-SNIPEREL-0012")
def test_the_two_sides_are_conjunctive_so_either_alone_is_worthless():
    """The PRODUCT, and the reason it is not deny's flat `max`: a terrifying body I have no route
    through is a bad snipe, and so is a harmless body sitting on my route."""
    scary_no_route = sr.target_relevance(incoming_damage=350, turns_to_afford=0,
                                         hp_remaining=0, rider_damage=0,
                                         prize_value=0, prizes_needed=6,
                                         turns_to_ko_before=None, turns_to_ko_after=None)
    harmless_on_route = sr.target_relevance(incoming_damage=0, turns_to_afford=None,
                                            hp_remaining=50, rider_damage=RIDER,
                                            prize_value=3, prizes_needed=3)
    assert scary_no_route["relevance"] == 0.0
    assert harmless_on_route["relevance"] == 0.0


@pytest.mark.req("REQ-SNIPEREL-0012")
def test_no_sum_of_positional_legs_can_out_vote_a_single_stronger_one():
    """The deleted additive stack's documented blunder class, made UNREPRESENTABLE rather than
    capped: `top-threat 30 + forced-promotion 40 + evolving-threat 45 = 115` beat `60` on a KO-able
    body (`82754241-45`). Under a max-within-a-side product, three mid legs cannot exceed one high
    leg — the score is bounded by the best claim, never by their sum."""
    three_mid = sr.target_relevance(incoming_damage=120, turns_to_afford=0,
                                    forward_damage=120, is_strongest_forward=True,
                                    is_forced_promotion=True,
                                    hp_remaining=100, rider_damage=RIDER, prize_value=1)
    one_high = sr.target_relevance(incoming_damage=340, turns_to_afford=0,
                                   hp_remaining=100, rider_damage=RIDER, prize_value=1)
    assert one_high["their_plan"] > three_mid["their_plan"]


@pytest.mark.req("REQ-SNIPEREL-0012")
def test_relevance_stays_inside_the_unit_band():
    """The band is the contract every consumer scales against; a Brief boost must not escape it."""
    maxed = sr.target_relevance(incoming_damage=10_000, turns_to_afford=0, brief_priority=99.0,
                                hp_remaining=10, rider_damage=RIDER, prize_value=9, prizes_needed=1,
                                turns_to_ko_before=3.0, turns_to_ko_after=0.0, prevents_my_ex=True)
    assert 0.0 <= maxed["relevance"] <= 1.0
    assert 0.0 <= maxed["their_plan"] <= 1.0
    assert 0.0 <= maxed["my_route"] <= 1.0


@pytest.mark.req("REQ-SNIPEREL-0012")
def test_the_scorer_never_zeroes_on_tera_because_the_veto_is_an_ordering():
    """A benched Tera takes no attack damage (`rules.md §185`), but `Pilot._snipe_tera_veto` expresses
    that as `-KO_SCORE` ORDERING rather than removal — when a benched Tera is the only offered target
    the select is forced and the option must stay selectable. So this module must not zero it."""
    tera = sr.target_relevance(incoming_damage=200, turns_to_afford=0, is_tera=True,
                               hp_remaining=200, rider_damage=RIDER)
    assert tera["relevance"] > 0.0
