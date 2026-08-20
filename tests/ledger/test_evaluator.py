"""The Ledger's pinned consequences: every action pays full cost, only end-turn is free.

Each test builds two real boards and asserts the SIGN of the swing between them — the exact
judgments the plan names (docs/plans/PokemonAI_Ledger_Plan.md §1): a useless attachment is
negative, overkill counters add nothing, a dead fetch waits, bench slots are scarce goods."""
from __future__ import annotations

from ledger_helpers import (AIR_BALLOON, DARK_E, DARKNESS, DRAGAPULT, DRAKLOAK, DREEPY, FIRE,
                            FIRE_E, IGNITION, LUNATONE, MAKUHITA, MEGA_STARMIE, PSYCHIC,
                            PSYCHIC_E, STARYU, ULTRA_BALL, UNKNOWN, WATER, WATER_E, body,
                            player, printout)

import pytest

from common.board import BoardState
from common.ledger import LedgerContext, LedgerWeights, evaluate


def board(**kwargs):
    decklist = kwargs.pop("decklist", None)
    return BoardState.root(printout(**kwargs), decklist=decklist)


def ctx(**kwargs):
    return LedgerContext.build(weights=LedgerWeights(), **kwargs)


def swing(before, after, context=None):
    context = context or ctx()
    return evaluate(after, context).total - evaluate(before, context).total


# --- only ending the turn is worth zero: useless plays price negative ---

def test_dark_energy_on_paid_dragapult_is_negative():
    """Fire+Psychic already fill every attack slot; a dark fills nothing, so attaching it
    trades hand worth for zero board gain."""
    before = board(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)),
                             hand=[DARK_E]))
    after = board(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC, DARKNESS)),
                            hand=[]))
    assert swing(before, after) < 0


def test_fire_energy_on_bare_dragapult_is_positive():
    before = board(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    after = board(me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[]))
    assert swing(before, after) > 0


def test_dark_energy_on_bare_dreepy_is_negative_once_its_line_is_gone():
    """Dreepy's own attacks cost Psychic and Fire+Psychic — no colorless slot. Dragapult's
    one-colorless Jet Headbutt could someday take the dark, so the reach gate must be CLOSED
    (no evolution left anywhere) for the unit to be unusable even speculatively."""
    no_line = [DARK_E] * 10                      # a decklist holding no Drakloak or Dragapult
    before = board(me=player(active=body(DREEPY, 1), hand=[DARK_E]), decklist=no_line)
    after = board(me=player(active=body(DREEPY, 1, energies=(DARKNESS,)), hand=[]),
                  decklist=no_line)
    assert swing(before, after) < 0


def test_dark_energy_on_bare_dreepy_earns_gated_credit_while_dragapult_is_in_hand():
    """The approved forward-credit rule, in its smallest form: the same dark unit is worth
    attaching once the evolution whose colorless slot it will pay is actually in hand."""
    holding = [DARK_E, DRAGAPULT]
    before = board(me=player(active=body(DREEPY, 1), hand=holding))
    after = board(me=player(active=body(DREEPY, 1, energies=(DARKNESS,)), hand=[DRAGAPULT]))
    assert swing(before, after) > 0


# --- damage counters: overkill destroys nothing ---

def test_overkill_counters_add_nothing():
    """Six counters into a 30-HP body waste three; splitting the spill into a live body is
    strictly better, and pure overkill never beats the exact kill."""
    start = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=30, max_hp=100),
                                                body(LUNATONE, 8, hp=60, max_hp=60)]))
    dumped = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=0, max_hp=100),
                                                 body(LUNATONE, 8, hp=60, max_hp=60)]))
    split = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=0, max_hp=100),
                                                body(LUNATONE, 8, hp=30, max_hp=60)]))
    context = ctx()
    assert evaluate(split, context).total > evaluate(dumped, context).total
    assert swing(start, dumped, context) > 0    # knocking the body down still helps
    assert swing(start, split, context) > swing(start, dumped, context)


def test_negative_hp_counts_as_zero():
    clamped = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=0, max_hp=100)]))
    below = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=-30, max_hp=100)]))
    context = ctx()
    assert evaluate(clamped, context).total == evaluate(below, context).total


# --- Ultra Ball: a dead fetch waits, a live fetch fires ---

def test_ultra_ball_with_nothing_to_fetch_is_negative():
    """No Pokemon left in the deck: the Ball and two discards buy nothing, so it waits."""
    decklist = [FIRE_E] * 21
    before = board(me=player(active=body(DRAGAPULT, 1),
                             hand=[ULTRA_BALL, FIRE_E, FIRE_E], deck_count=21),
                   decklist=[ULTRA_BALL, FIRE_E, FIRE_E] + decklist)
    after = board(me=player(active=body(DRAGAPULT, 1), hand=[],
                            discard=[ULTRA_BALL, FIRE_E, FIRE_E], deck_count=21),
                  decklist=[ULTRA_BALL, FIRE_E, FIRE_E] + decklist)
    assert swing(before, after) < 0


def test_ultra_ball_reads_dead_when_its_only_target_is_undemanded():
    """A fetchable target that is itself dead (an evolution with no base anywhere) must not
    mark the fetch live — the multiplier is compared, never truthiness-read."""
    context = ctx()
    me = player(active=body(MAKUHITA, 1), hand=[ULTRA_BALL], deck_count=21)
    dead_target = board(me=me, decklist=[ULTRA_BALL, DRAKLOAK] + [FIRE_E] * 20)
    live_target = board(me=me, decklist=[ULTRA_BALL, DREEPY] + [FIRE_E] * 20)
    assert (evaluate(live_target, context).part("me.hand")
            > evaluate(dead_target, context).part("me.hand"))


def test_ultra_ball_fetching_the_live_evolution_is_positive():
    """Dreepy is in play, Drakloak comes out of the deck: demand-live fetch beats the spend."""
    decklist = [DRAKLOAK] + [FIRE_E] * 20
    before = board(me=player(active=body(DREEPY, 1),
                             hand=[ULTRA_BALL, FIRE_E, FIRE_E], deck_count=21),
                   decklist=[ULTRA_BALL, FIRE_E, FIRE_E] + decklist)
    after = board(me=player(active=body(DREEPY, 1), hand=[DRAKLOAK],
                            discard=[ULTRA_BALL, FIRE_E, FIRE_E], deck_count=20),
                  decklist=[ULTRA_BALL, FIRE_E, FIRE_E] + decklist)
    assert swing(before, after) > 0


# --- bench slots are scarce goods ---

def test_benching_the_wincon_basic_is_positive_even_on_the_last_slot():
    filler = [body(MAKUHITA, 10 + i) for i in range(4)]
    before = board(me=player(active=body(DRAGAPULT, 1), bench=filler, hand=[DREEPY]))
    after = board(me=player(active=body(DRAGAPULT, 1),
                            bench=filler + [body(DREEPY, 20)], hand=[]))
    assert swing(before, after) > 0


def test_benching_a_duplicate_of_a_fielded_body_on_the_last_slot_is_negative():
    """Every basic in the store carries a Role, so 'redundant' means DUPLICATED: three
    Makuhita already field the backup-attacker job; a fourth on the last slot is refused."""
    filler = [body(MAKUHITA, 10 + i) for i in range(3)] + [body(LUNATONE, 14)]
    before = board(me=player(active=body(DRAGAPULT, 1), bench=filler, hand=[MAKUHITA]))
    after = board(me=player(active=body(DRAGAPULT, 1),
                            bench=filler + [body(MAKUHITA, 20)], hand=[]))
    assert swing(before, after) < 0


def test_benching_a_filler_on_an_empty_bench_is_positive():
    """Early development is real: with every slot free the same filler is worth deploying."""
    before = board(me=player(active=body(DRAGAPULT, 1), hand=[LUNATONE]))
    after = board(me=player(active=body(DRAGAPULT, 1), bench=[body(LUNATONE, 20)], hand=[]))
    assert swing(before, after) > 0


# --- evolution demand: a live target prices the card up ---

def test_evolution_in_hand_prices_higher_with_its_base_in_play():
    """Compared on the HAND part alone, so the two boards' different actives (the thing that
    makes the base present or absent) cannot decide the inequality for the demand term."""
    context = ctx()
    live = board(me=player(active=body(DREEPY, 1), hand=[DRAKLOAK]))
    dead = board(me=player(active=body(MAKUHITA, 1), hand=[DRAKLOAK]))
    assert (evaluate(live, context).part("me.hand")
            > evaluate(dead, context).part("me.hand") + 0.02)


def test_the_pair_in_hand_outprices_either_alone():
    """Drakloak's marginal worth is higher when Dreepy shares the hand — the nonlinearity the
    sampled-hand chance model feeds on (plan §1). The margin is the point: without the pair
    term the two marginals are equal to within float noise, and a bare `>` would pass on one
    ULP (the ADR-0128 lesson)."""
    context = ctx()

    def value(hand):
        return evaluate(board(me=player(active=body(MAKUHITA, 1), hand=hand)), context).total

    marginal_beside_base = value([DREEPY, DRAKLOAK]) - value([DREEPY])
    marginal_alone = value([DRAKLOAK]) - value([])
    assert marginal_beside_base > marginal_alone + 0.02


# --- the boundary and coverage honesty ---

def test_unknown_card_scores_the_floor_and_logs_a_gap():
    context = ctx()
    valuation = evaluate(board(me=player(active=body(DRAGAPULT, 1), hand=[UNKNOWN])), context)
    assert any(str(UNKNOWN) in gap for gap in valuation.gaps)


def test_opponent_hand_is_priced_by_count_alone():
    context = ctx()
    small = board(them=player(own=False, hand_count=2))
    large = board(them=player(own=False, hand_count=8))
    assert evaluate(small, context).total > evaluate(large, context).total


def test_prize_race_prefers_fewer_own_prizes_remaining():
    context = ctx()
    ahead = board(me=player(prizes=2), them=player(own=False, prizes=6))
    behind = board(me=player(prizes=6), them=player(own=False, prizes=2))
    assert evaluate(ahead, context).total > evaluate(behind, context).total


def test_won_result_dominates_everything():
    context = ctx()
    printed = printout(me=player())
    printed["current"]["result"] = 0
    won = BoardState.root(printed)
    assert evaluate(won, context).total > 50.0


def test_valuation_is_deterministic():
    """Two builds of the same printout price identically — the replay guarantee."""
    context = ctx()
    mine = player(active=body(DREEPY, 1), hand=[FIRE_E], prizes=6)
    theirs = player(own=False, active=body(DREEPY, 2), hand_count=1, prizes=6)
    first = evaluate(board(me=mine, them=theirs), context).total
    second = evaluate(board(me=mine, them=theirs), context).total
    assert first == second


# --- terminal results: win, loss, and the draw between them ---

def test_lost_result_dominates_everything():
    context = ctx()
    printed = printout(me=player())
    printed["current"]["result"] = 1            # seat 1 won; the viewer is seat 0
    assert evaluate(BoardState.root(printed), context).total < -50.0


def test_a_draw_prices_between_the_win_and_the_loss():
    """cgpy's simultaneous outcome (result=2) is a DRAW: a line that draws must still beat a
    line that loses, so it scores zero, never the loss."""
    context = ctx()
    drawn = printout(me=player())
    drawn["current"]["result"] = 2
    lost = printout(me=player())
    lost["current"]["result"] = 1
    draw_value = evaluate(BoardState.root(drawn), context)
    assert draw_value.part("result") == 0.0
    assert draw_value.total > evaluate(BoardState.root(lost), context).total


# --- per-body terms: statuses, tools, the stack underneath, prize liability ---

def test_a_status_condition_prices_the_side_down():
    well = board(me=player(active=body(DREEPY, 1)))
    sick = board(me=player(active=body(DREEPY, 1), poisoned=True))
    context = ctx()
    assert evaluate(sick, context).total < evaluate(well, context).total
    assert evaluate(sick, context).part("me.status") < 0


def test_an_attached_tool_adds_its_worth_through_the_body():
    bare = board(me=player(active=body(MEGA_STARMIE, 1)))
    equipped = board(me=player(active=body(MEGA_STARMIE, 1, tools=(AIR_BALLOON,))))
    context = ctx()
    assert evaluate(equipped, context).total > evaluate(bare, context).total + 0.05


def test_the_evolutions_underlying_cards_keep_worth():
    fresh = board(me=player(active=body(MEGA_STARMIE, 1)))
    stacked = board(me=player(active=body(MEGA_STARMIE, 1, under=(STARYU,))))
    context = ctx()
    assert evaluate(stacked, context).total > evaluate(fresh, context).total + 0.005


def test_rule_box_bodies_carry_prize_liability():
    context = ctx()
    heavy = evaluate(board(me=player(active=body(MEGA_STARMIE, 1))), context)
    light = evaluate(board(me=player(active=body(MAKUHITA, 1))), context)
    assert heavy.part("me.liability") < light.part("me.liability") == 0.0


def test_the_active_premium_pays_more_when_the_active_can_attack():
    """Dreepy's Bite costs one Psychic: attached, the same body earns the full premium."""
    context = ctx()
    unready = evaluate(board(me=player(active=body(DREEPY, 1))), context)
    ready = evaluate(board(me=player(active=body(DREEPY, 1, energies=(PSYCHIC,)))), context)
    assert 0.0 < unready.part("me.active") < ready.part("me.active")


def test_energy_units_without_card_detail_still_price():
    """A printout carrying unit counts but no per-card energy listing falls back to the flat
    energy worth instead of pricing the attachment at zero."""
    with_units = body(DREEPY, 1, energies=(PSYCHIC,))
    with_units["energyCards"] = []
    context = ctx()
    assert (evaluate(board(me=player(active=with_units)), context).total
            > evaluate(board(me=player(active=body(DREEPY, 1))), context).total)


def test_a_zero_max_hp_body_prices_as_intact():
    context = ctx()
    zeroed = board(me=player(active=body(DREEPY, 1, hp=0, max_hp=0)))
    intact = board(me=player(active=body(DREEPY, 1, hp=100, max_hp=100)))
    assert evaluate(zeroed, context).total == evaluate(intact, context).total


# --- demand branches: colorless-only, bench-full basics, surplus, fetch vocabulary ---

def test_colorless_only_energy_prices_between_dead_and_typed():
    """The same dark energy in hand: nothing on a line-gone Dreepy, a colorless slot on Mega
    Starmie's Nebula Beam, and a typed slot is worth the most of the three. The dead leg pins
    its decklist so the reach gate is truly closed, not merely unknown."""
    context = ctx()
    no_line = [DARK_E] * 10
    dead = evaluate(board(me=player(active=body(DREEPY, 1), hand=[DARK_E]),
                          decklist=no_line), context)
    colorless = evaluate(board(me=player(active=body(MEGA_STARMIE, 1), hand=[DARK_E])),
                         context)
    typed = evaluate(board(me=player(active=body(DREEPY, 1), hand=[FIRE_E])), context)
    assert dead.part("me.hand") + 0.01 < colorless.part("me.hand")
    assert colorless.part("me.hand") + 0.01 < typed.part("me.hand")


def test_a_basic_in_hand_reads_dead_when_the_bench_is_full():
    context = ctx()
    filler = [body(LUNATONE, 10 + i) for i in range(5)]
    room = evaluate(board(me=player(active=body(DREEPY, 1), bench=filler[:4],
                                    hand=[MAKUHITA])), context)
    full = evaluate(board(me=player(active=body(DREEPY, 1), bench=filler,
                                    hand=[MAKUHITA])), context)
    assert full.part("me.hand") + 0.02 < room.part("me.hand")


def test_hand_copies_beyond_consumable_capacity_saturate():
    """One free bench slot consumes one Makuhita; the second and third copies decay, so three
    in hand are worth strictly less than three times one."""
    context = ctx()
    filler = [body(LUNATONE, 10 + i) for i in range(4)]

    def hand_part(hand):
        return evaluate(board(me=player(active=body(DREEPY, 1), bench=filler, hand=hand)),
                        context).part("me.hand")

    assert hand_part([MAKUHITA] * 3) + 0.02 < 3 * hand_part([MAKUHITA])


def test_fetch_liveness_respects_the_target_vocabulary():
    """Ultra Ball fetches Pokemon: a deck of nothing but energy leaves it dead even though
    every card in that deck is itself perfectly live."""
    context = ctx()
    me = player(active=body(DREEPY, 1), hand=[ULTRA_BALL], deck_count=20)
    energy_only = board(me=me, decklist=[ULTRA_BALL] + [PSYCHIC_E] * 20)
    with_pokemon = board(me=me, decklist=[ULTRA_BALL, MAKUHITA] + [PSYCHIC_E] * 19)
    assert (energy_only_part := evaluate(energy_only, context).part("me.hand")) + 0.01 \
        < evaluate(with_pokemon, context).part("me.hand")
    assert energy_only_part > 0


# --- forward credit: colorless slots on a REACHABLE evolution (the Staryu question) ---

def test_charging_staryu_for_nebula_beam_is_the_ruled_play_unless_staryu_is_doomed():
    """The owner's ruling, verbatim: the second (and third) water goes on Staryu even with
    Mega Starmie merely in the DECK — Nebula Beam's three colorless slots are what the deck is
    building toward — unless Staryu is doomed. In hand is stronger still; provably gone means
    the prep is waste again; and a badly damaged carrier refuses by the damage blend alone,
    which is where the doomed half of the ruling comes from."""
    context = ctx()

    def attach_swing(attached_before, decklist, extra_hand=(), hp=30):
        def make(attached, hand):
            active = body(STARYU, 1, energies=(WATER,) * attached, hp=hp, max_hp=30)
            return board(me=player(active=active, hand=hand), decklist=decklist)
        before = make(attached_before, [WATER_E, *extra_hand])
        after = make(attached_before + 1, list(extra_hand))
        return swing(before, after, context)

    in_deck = [MEGA_STARMIE] + [WATER_E] * 10
    gone = [WATER_E] * 10                        # no Mega Starmie left anywhere
    assert attach_swing(1, in_deck) > 0          # the ruling: deck-reachable is enough
    assert attach_swing(2, in_deck) > 0
    assert attach_swing(1, gone, extra_hand=[MEGA_STARMIE]) > attach_swing(1, in_deck)
    assert attach_swing(1, gone) < 0
    assert attach_swing(1, in_deck, hp=10) < 0   # doomed carrier: the cargo dies with it


# --- Ignition: the multi-unit provision clause read at the demand seam ---

def test_ignition_reads_fully_live_beside_a_multi_slot_evolution():
    """Mega Starmie's Nebula Beam has three colorless slots and Ignition provides three units
    on an evolution: one card doing three basics' work is fully live, not colorless-discounted.
    Dragapult ex is the control — also an evolution with a colorless slot, but only ONE, so
    the multi-provision read must not fire there. The special-energy worth is pinned here so
    the MECHANISM stays testable while the tuning rounds move the general default — the
    asserted margins scale with that worth."""
    context = ctx(overrides={"kind.special_energy": 0.10})
    beside_mega = evaluate(board(me=player(active=body(MEGA_STARMIE, 1), hand=[IGNITION])),
                           context)
    beside_dragapult = evaluate(board(me=player(active=body(DRAGAPULT, 1), hand=[IGNITION])),
                                context)
    beside_makuhita = evaluate(board(me=player(active=body(MAKUHITA, 1), hand=[IGNITION])),
                               context)
    assert beside_mega.part("me.hand") > beside_dragapult.part("me.hand") + 0.015
    assert beside_dragapult.part("me.hand") > beside_makuhita.part("me.hand") + 0.015


def test_concentration_prefers_finishing_the_started_twin():
    """ADR-0150: with the lever armed, 2-and-0 across twin attackers out-values 1-and-1 —
    the second energy toward Nebula Beam's three slots beats the first on a fresh body.
    At the 0.0 default the term is off and the splits price identically."""
    def split(started_units, bare_units):
        return board(me=player(
            active=body(STARYU, 9),
            bench=[body(MEGA_STARMIE, 1, energies=(WATER,) * started_units),
                   body(MEGA_STARMIE, 2, energies=(WATER,) * bare_units)]))

    armed = ctx(overrides={"concentration": 0.1})
    assert evaluate(split(2, 0), armed).total > evaluate(split(1, 1), armed).total
    flat = ctx()
    assert evaluate(split(2, 0), flat).total == pytest.approx(
        evaluate(split(1, 1), flat).total)


def test_rental_energy_on_the_bench_prices_zero():
    """ADR-0150: an end-of-turn-discarding Energy on a BENCHED body evaporates before the
    body can attack — worth zero there, priced normally on the Active."""
    def ignition_body(serial):
        shell = body(MEGA_STARMIE, serial)
        shell["energies"] = [0]
        shell["energyCards"] = [{"id": IGNITION, "serial": 701}]
        return shell

    context = ctx()
    bare_bench = evaluate(board(me=player(active=body(STARYU, 9),
                                          bench=[body(MEGA_STARMIE, 1)])), context)
    rental_bench = evaluate(board(me=player(active=body(STARYU, 9),
                                            bench=[ignition_body(1)])), context)
    assert rental_bench.part("me.bodies") == pytest.approx(bare_bench.part("me.bodies"))

    bare_active = evaluate(board(me=player(active=body(MEGA_STARMIE, 1))), context)
    rental_active = evaluate(board(me=player(active=ignition_body(1))), context)
    assert rental_active.part("me.bodies") > bare_active.part("me.bodies")
