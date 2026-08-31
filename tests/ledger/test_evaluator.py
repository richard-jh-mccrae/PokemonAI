"""The Ledger's pinned consequences: every action pays full cost, only end-turn is free.

Each test builds two real boards and asserts the SIGN of the swing between them — the exact
judgments the plan names (docs/plans/PokemonAI_Ledger_Plan.md §1): a useless attachment is
negative, overkill counters add nothing, a dead fetch waits, bench slots are scarce goods."""
from __future__ import annotations

from dataclasses import replace

from ledger_helpers import (AIR_BALLOON, DARK_E, DARKNESS, DRAGAPULT, DRAKLOAK, DREEPY, FIRE,
                            FIRE_E, IGNITION, LILLIES, LUNATONE, MAKUHITA, MEGA_STARMIE, PSYCHIC,
                            PSYCHIC_E, STARYU, ULTRA_BALL, UNKNOWN, WATER, WATER_E, body,
                            player, printout)

import pytest

from common.observation import ObservationStateBuilder
from common.observation.state import AttackEvent
from common.ledger import DeckOverlay, EvaluationModel, evaluate
from common.ledger.capabilities import (
    ITEM_LOCK_BASE_UNITS, body_capability)
from common.ledger.evaluate import _slot_option


def board(**kwargs):
    decklist = kwargs.pop("decklist", None)
    return ObservationStateBuilder(decklist).root(printout(**kwargs))


def ctx(**kwargs):
    overrides = kwargs.pop("overrides", {})
    overlay = {key: value - EvaluationModel.build().configuration[key]
               for key, value in overrides.items()}
    return EvaluationModel.build(overlay=DeckOverlay(overlay), **kwargs)


def swing(before, after, context=None):
    context = context or ctx()
    return evaluate(after, context).total - evaluate(before, context).total


def test_evaluation_exposes_catalog_activations_and_contributions_that_sum_to_total():
    context = EvaluationModel.build()
    valuation = evaluate(board(
        me=player(prizes=5, poisoned=True),
        them=player(own=False, prizes=6),
    ), context)

    assert valuation.activations
    assert valuation.contributions
    for contribution in valuation.contributions:
        assert contribution.coefficient == context.configuration[contribution.feature]
        assert contribution.value == pytest.approx(
            contribution.activation * contribution.coefficient)
    assert sum(item.value for item in valuation.contributions) == pytest.approx(valuation.total)


def test_feature_extraction_is_independent_of_resolved_coefficients():
    state = board(me=player(active=body(DREEPY, 1), hand=[DARK_E, DRAGAPULT]))
    general = EvaluationModel.build()
    bent = EvaluationModel.build(overlay=DeckOverlay({
        "combat.realization": -0.25,
        "zone.in_hand": -1.2,
    }))

    assert evaluate(state, general).activations == evaluate(state, bent).activations


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
    """Close evolution reach so Dark Energy has no speculative colorless slot."""
    no_line = [DARK_E] * 10                      # a decklist holding no Drakloak or Dragapult
    before = board(me=player(active=body(DREEPY, 1), hand=[DARK_E]), decklist=no_line)
    after = board(me=player(active=body(DREEPY, 1, energies=(DARKNESS,)), hand=[]),
                  decklist=no_line)
    assert swing(before, after) < 0


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

def test_bench_slot_reserve_escalates_toward_the_last_open_slot():
    assert _slot_option(5) - _slot_option(4) < _slot_option(1) - _slot_option(0)

def test_benching_the_wincon_basic_is_positive_even_on_the_last_slot():
    filler = [body(MAKUHITA, 10 + i) for i in range(4)]
    before = board(me=player(active=body(DRAGAPULT, 1), bench=filler, hand=[DREEPY]))
    after = board(me=player(active=body(DRAGAPULT, 1),
                            bench=filler + [body(DREEPY, 20)], hand=[]))
    assert swing(before, after) > 0


def test_benching_a_duplicate_of_a_fielded_body_on_the_last_slot_is_negative():
    """Zero HP worth to isolate duplicate-role refusal on the last bench slot."""
    context = ctx(overrides={"body.hp_per_100": 0.0})
    filler = [body(MAKUHITA, 10 + i) for i in range(3)] + [body(LUNATONE, 14)]
    before = board(me=player(active=body(DRAGAPULT, 1), bench=filler, hand=[MAKUHITA]))
    after = board(me=player(active=body(DRAGAPULT, 1),
                            bench=filler + [body(MAKUHITA, 20)], hand=[]))
    assert swing(before, after, context) < 0


def test_benching_a_filler_on_an_empty_bench_is_positive():
    """Early development is real: with every slot free the same filler is worth deploying."""
    before = board(me=player(active=body(DRAGAPULT, 1), hand=[LUNATONE]))
    after = board(me=player(active=body(DRAGAPULT, 1), bench=[body(LUNATONE, 20)], hand=[]))
    assert swing(before, after) > 0


def test_full_bench_pressure_is_not_a_second_card_option_evaluator():
    full = [body(MAKUHITA, 10 + index) for index in range(5)]
    unknown = board(me=player(active=body(DRAGAPULT, 1), bench=full))
    known = board(
        me=player(active=body(DRAGAPULT, 1), bench=full, deck_count=1),
        decklist=[DREEPY])

    def pressure(state):
        return next(item.value for item in evaluate(state, ctx()).activations
                    if item.feature == "bench.full")

    assert pressure(known) == pressure(unknown)


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
    """Demand a margin because a bare comparison can pass on float noise; see ADR-0128."""
    context = ctx()

    def value(hand):
        return evaluate(board(me=player(active=body(MAKUHITA, 1), hand=hand)), context).total

    marginal_beside_base = value([DREEPY, DRAKLOAK]) - value([DREEPY])
    marginal_alone = value([DRAKLOAK]) - value([])
    assert marginal_beside_base > marginal_alone + 0.02


def test_visible_evolution_link_is_owned_by_its_feasible_parent():
    valuation = evaluate(board(me=player(
        active=body(MAKUHITA, 1), hand=[DREEPY, DRAKLOAK, DRAKLOAK])), ctx())

    links = [item for item in valuation.activations
             if item.feature == "development.basic_hand_link"]

    assert sum(item.value for item in links) == 1.0
    assert links[0].provenance == ("feasible_option_portfolio:serial:800",)


def test_one_middle_card_cannot_complete_two_hand_links():
    one_middle = evaluate(replace(board(me=player(
        active=body(MAKUHITA, 1), hand=[DREEPY, DRAKLOAK, DRAGAPULT])),
        deck_counts=((DREEPY, 2),)), ctx())
    two_middles = evaluate(replace(board(me=player(
        active=body(MAKUHITA, 1),
        hand=[DREEPY, DRAKLOAK, DRAKLOAK, DRAGAPULT])),
        deck_counts=((DREEPY, 2),)), ctx())

    def links(valuation):
        return sum(item.value for item in valuation.activations
                   if item.feature in {"development.basic_hand_link",
                                       "development.feasible_hand_link"})

    def reserves(valuation):
        return sum(item.value for item in valuation.activations
                   if item.feature == "development.reserve_hand_link")

    assert links(one_middle) == 1.0
    assert links(two_middles) == 2.0
    assert reserves(one_middle) == 0.0
    assert reserves(two_middles) == 0.0


def test_unused_duplicate_evolution_keeps_a_reserve_deck_link():
    valuation = evaluate(replace(board(me=player(
        active=body(MAKUHITA, 1), hand=[DRAKLOAK, DRAKLOAK, DRAGAPULT])),
        deck_counts=((DREEPY, 2),)), ctx())

    assert sum(item.value for item in valuation.activations
               if item.feature == "development.reserve_hand_link") == 1.0


def test_evolving_transfers_ready_and_energy_reach_into_completed_development():
    before = evaluate(board(me=player(
        active=body(DRAKLOAK, 1, energies=(FIRE, PSYCHIC), under=(DREEPY,)),
        hand=[DRAGAPULT])), ctx())
    after = evaluate(board(me=player(
        active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC),
                    under=(DREEPY, DRAKLOAK)))), ctx())

    def activation(valuation, feature):
        return next(item.value for item in valuation.activations
                    if item.feature == feature)

    assert activation(after, "development.ready_evolution") == activation(
        before, "development.ready_evolution")
    assert activation(after, "development.visible_reach") == activation(
        before, "development.visible_reach")
    assert after.total > before.total


def test_a_named_synergy_partner_in_play_makes_the_held_half_live():
    context = ctx()
    paired = evaluate(board(me=player(active=body(676, 1), hand=[LUNATONE])), context)
    alone = evaluate(board(me=player(active=body(MAKUHITA, 1), hand=[LUNATONE])), context)

    assert paired.part("me.hand") > alone.part("me.hand") + 0.35
    synergy = next(item for item in paired.activations
                   if item.feature == "interaction.synergy.in_hand")
    assert synergy.provenance == ("feasible_option_portfolio:serial:800",)


def test_duplicate_supporter_has_less_marginal_hand_value():
    context = ctx()

    def hand_value(cards):
        return evaluate(board(me=player(active=body(DREEPY, 1), hand=cards)), context).part(
            "me.hand")

    assert hand_value([LILLIES, LILLIES]) - hand_value([LILLIES]) \
        < hand_value([LILLIES]) - hand_value([])


def test_discard_recovery_is_dead_until_a_matching_target_exists():
    empty = evaluate(board(me=player(active=body(DREEPY, 1), hand=[1097])), ctx())
    live = evaluate(board(me=player(
        active=body(DREEPY, 1), hand=[1097], discard=[DRAKLOAK])), ctx())

    assert any(item.feature == "demand.dead" and item.value == 1.0
               for item in empty.activations)
    assert not any(item.feature == "demand.dead" and item.value > 0
                   for item in live.activations)


def test_the_active_with_lower_attack_pressure_is_the_better_gust_target():
    context = ctx()
    fez_active = board(them=player(own=False, active=body(140, 1), bench=[body(1071, 2)]))
    meowth_active = board(them=player(own=False, active=body(1071, 2), bench=[body(140, 1)]))

    assert evaluate(meowth_active, context).total > evaluate(fez_active, context).total


def test_retreat_readiness_only_has_value_when_a_bench_target_exists():
    context = ctx()
    stranded = board(me=player(active=body(DREEPY, 1, energies=(PSYCHIC,))))
    mobile = board(me=player(active=body(DREEPY, 1, energies=(PSYCHIC,)),
                             bench=[body(MAKUHITA, 2)]))

    stranded_features = {item.feature: item.value for item in evaluate(stranded, context).activations}
    mobile_features = {item.feature: item.value for item in evaluate(mobile, context).activations}
    assert stranded_features.get("mobility.retreat_progress", 0.0) == 0.0
    assert mobile_features["mobility.retreat_progress"] > 0.0


# --- the boundary and coverage honesty ---

def test_unknown_card_scores_the_floor_and_logs_a_gap():
    context = ctx()
    valuation = evaluate(board(me=player(active=body(DRAGAPULT, 1), hand=[UNKNOWN])), context)
    assert any(str(UNKNOWN) in gap for gap in valuation.gaps)


def test_non_pokemon_rendered_as_a_body_is_explicit_coverage_unknown():
    valuation = evaluate(board(me=player(active=body(ULTRA_BALL, 1), hand=[IGNITION])), ctx())

    assert any("non-Pokemon body" in gap for gap in valuation.gaps)
    assert any(item.feature == "coverage.unknown_card" and item.value > 0
               for item in valuation.activations)


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
    won = ObservationStateBuilder().root(printed)
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
    assert evaluate(ObservationStateBuilder().root(printed), context).total < -50.0


def test_a_draw_prices_between_the_win_and_the_loss():
    """cgpy's simultaneous outcome (result=2) is a DRAW: a line that draws must still beat a
    line that loses, so it scores zero, never the loss."""
    context = ctx()
    drawn = printout(me=player())
    drawn["current"]["result"] = 2
    lost = printout(me=player())
    lost["current"]["result"] = 1
    draw_value = evaluate(ObservationStateBuilder().root(drawn), context)
    assert draw_value.part("result") == 0.0
    assert draw_value.total > evaluate(ObservationStateBuilder().root(lost), context).total


# --- per-body terms: statuses, tools, the stack underneath, prize liability ---

def test_a_status_condition_prices_the_side_down():
    well = board(me=player(active=body(DREEPY, 1)))
    sick = board(me=player(active=body(DREEPY, 1), poisoned=True))
    context = ctx()
    assert evaluate(sick, context).total < evaluate(well, context).total
    assert evaluate(sick, context).part("me.status") < 0


def test_combat_realization_is_one_attack_envelope_not_a_sum_of_readings():
    state = board(me=player(active=body(MEGA_STARMIE, 1, energies=(WATER,))))
    context = ctx()

    capability = body_capability(
        state.me.active, state.me, state.them, state, context)

    assert capability.realization == pytest.approx(1.2)


def test_incomplete_stronger_attack_does_not_stack_on_a_ready_attack():
    one_energy = board(
        me=player(active=body(MEGA_STARMIE, 1, energies=(WATER,))),
        them=player(active=body(MEGA_STARMIE, 9), own=False))
    two_energy = board(
        me=player(active=body(MEGA_STARMIE, 1, energies=(WATER, WATER))),
        them=player(active=body(MEGA_STARMIE, 9), own=False))
    context = ctx()

    one = body_capability(
        one_energy.me.active, one_energy.me, one_energy.them, one_energy, context)
    two = body_capability(
        two_energy.me.active, two_energy.me, two_energy.them, two_energy, context)

    assert two.realization == one.realization


def test_held_typed_energy_advances_the_next_attachment_clock():
    without = board(me=player(active=body(MAKUHITA, 1), bench=[body(678, 2)]),
                    them=player(active=body(DRAKLOAK, 3), own=False))
    with_fighting = board(
        me=player(active=body(MAKUHITA, 1), bench=[body(678, 2)], hand=[6]),
        them=player(active=body(DRAKLOAK, 3), own=False))
    context = ctx()

    bare = body_capability(
        without.me.bench[0], without.me, without.them, without, context)
    funded = body_capability(
        with_fighting.me.bench[0], with_fighting.me, with_fighting.them,
        with_fighting, context)

    assert funded.attachment_clock > bare.attachment_clock


def test_spent_attachment_allowance_removes_held_energy_from_the_clock():
    state = board(
        me=player(active=body(MAKUHITA, 1), bench=[body(678, 2)], hand=[6]),
        them=player(active=body(DRAKLOAK, 3), own=False),
        turn=1,
        energy_attached=True)
    capability = body_capability(
        state.me.bench[0], state.me, state.them, state, ctx())

    assert capability.attachment_clock == pytest.approx(capability.realization)


def test_bench_value_already_includes_a_held_manual_attachment():
    held = board(
        me=player(active=body(MAKUHITA, 1), bench=[body(677, 2)], hand=[6]),
        them=player(active=body(DRAKLOAK, 3), own=False),
        turn=1)
    attached = board(
        me=player(
            active=body(MAKUHITA, 1), bench=[body(677, 2, energies=(6,))]),
        them=player(active=body(DRAKLOAK, 3), own=False),
        turn=1,
        energy_attached=True)

    held_combat = evaluate(held, ctx()).part("me.combat")
    attached_combat = evaluate(attached, ctx()).part("me.combat")

    assert attached_combat == pytest.approx(held_combat)


@pytest.mark.parametrize(("turn", "player"), ((1, 0), (2, 1), (3, 0), (4, 1)))
def test_turn_exposes_the_current_player(turn, player):
    assert board(turn=turn).turn.player == player


def test_promotion_values_active_realization_over_discounted_backup_realization():
    lucario = body(678, 2)
    makuhita = body(MAKUHITA, 3, energies=(6,))
    them = player(active=body(DRAKLOAK, 4), own=False)
    promoted_lucario = board(
        me=player(active=lucario, bench=[makuhita], hand=[6]), them=them,
        energy_attached=True)
    promoted_makuhita = board(
        me=player(active=makuhita, bench=[lucario], hand=[6]), them=them,
        energy_attached=True)

    assert evaluate(promoted_lucario, ctx()).total > evaluate(
        promoted_makuhita, ctx()).total


def test_payable_attack_effect_counts_in_active_realization():
    state = board(
        me=player(active=body(235, 1)),
        them=player(active=body(MAKUHITA, 2), own=False))
    context = ctx()
    budew = context.facts(235)
    stripped = replace(
        budew, attacks=tuple(replace(attack, clauses=()) for attack in budew.attacks))
    stripped_context = replace(context, store={**context.store, 235: stripped})

    valued = body_capability(
        state.me.active, state.me, state.them, state, context)
    damage_only = body_capability(
        state.me.active, state.me, state.them, state, stripped_context)

    assert valued.attack_now == damage_only.attack_now + ITEM_LOCK_BASE_UNITS


def test_retained_attack_modifiers_cross_the_knockout_threshold():
    one = board(
        me=player(active=body(MAKUHITA, 1, energies=(6, 6)), hand=[1141]),
        them=player(active=body(DRAKLOAK, 2, hp=90, max_hp=90), own=False))
    two = board(
        me=player(active=body(MAKUHITA, 1, energies=(6, 6)), hand=[1141, 1141]),
        them=player(active=body(DRAKLOAK, 2, hp=90, max_hp=90), own=False))
    context = ctx()

    one_attack = body_capability(
        one.me.active, one.me, one.them, one, context).attack_now
    two_attack = body_capability(
        two.me.active, two.me, two.them, two, context).attack_now

    assert two_attack > one_attack + 1.0


def test_held_attack_modifiers_do_not_inflate_every_benched_attacker():
    state = board(
        me=player(
            active=body(MAKUHITA, 1, energies=(6, 6)),
            bench=[body(MAKUHITA, 2, energies=(6, 6))],
            hand=[1141, 1141]),
        them=player(active=body(DRAKLOAK, 3, hp=90, max_hp=90), own=False))
    context = ctx()

    active = body_capability(
        state.me.active, state.me, state.them, state, context)
    benched = body_capability(
        state.me.bench[0], state.me, state.them, state, context)

    assert active.attack_now > benched.attack_now + 1.0


def test_played_attack_modifier_persists_for_the_turn():
    held = board(
        me=player(active=body(MAKUHITA, 1, energies=(6, 6)), hand=[1141]),
        them=player(active=body(DRAKLOAK, 2, hp=90, max_hp=90), own=False))
    printed = printout(
        me=player(active=body(MAKUHITA, 1, energies=(6, 6)), discard=[1141]),
        them=player(active=body(DRAKLOAK, 2, hp=90, max_hp=90), own=False))
    printed["logs"] = [{"type": 10, "cardId": 1141, "playerIndex": 0, "serial": 99}]
    played = ObservationStateBuilder().root(printed)
    context = ctx()

    held_attack = body_capability(
        held.me.active, held.me, held.them, held, context).attack_now
    played_attack = body_capability(
        played.me.active, played.me, played.them, played, context).attack_now

    assert played_attack == held_attack


def test_self_shuffling_draw_exposes_the_body_cost():
    valuation = evaluate(board(me=player(active=body(66, 1))), ctx())
    contribution = next(item for item in valuation.contributions
                        if item.feature == "function.self_cost.exposure")

    assert contribution.activation == 3.0
    assert contribution.coefficient == -0.04


def test_symmetric_stadium_fit_does_not_scale_with_current_body_count():
    printed = printout(
        me=player(active=body(DREEPY, 1), bench=[body(MAKUHITA, 2)]),
        them=player(active=body(DRAKLOAK, 3), own=False))
    printed["current"]["stadium"] = [
        {"id": 1260, "serial": 700, "playerIndex": 0}]
    state = ObservationStateBuilder().root(printed)

    assert sum(item.value for item in evaluate(state, ctx()).activations
               if item.feature == "function.stadium.board_fit") == 0.2


def test_confusion_reduces_expected_attack_and_retreat_cures_it():
    context = ctx()
    healthy = board(me=player(
        active=body(DREEPY, 1, energies=(PSYCHIC,)), bench=[body(MAKUHITA, 2)]))
    confused = board(me=player(
        active=body(DREEPY, 1, energies=(PSYCHIC,)), bench=[body(MAKUHITA, 2)],
        confused=True))
    after = board(me=player(
        active=body(MAKUHITA, 2), bench=[body(DREEPY, 1, energies=(PSYCHIC,))]))

    healthy_capability = body_capability(
        healthy.me.active, healthy.me, healthy.them, healthy, context)
    confused_capability = body_capability(
        confused.me.active, confused.me, confused.them, confused, context)

    assert confused_capability.attack_now < healthy_capability.attack_now
    assert swing(confused, after, context) > swing(healthy, after, context) + 0.1


@pytest.mark.parametrize("status", ("asleep", "paralyzed"))
def test_attack_blocking_conditions_zero_immediate_realization(status):
    state = board(me=player(
        active=body(DREEPY, 1, energies=(PSYCHIC,)), **{status: True}))
    capability = body_capability(
        state.me.active, state.me, state.them, state, ctx())

    assert capability.attack_now == 0.0


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
    unready = evaluate(board(me=player(active=body(DREEPY, 1)),
                             them=player(active=body(MAKUHITA, 2), own=False)), context)
    ready = evaluate(board(me=player(active=body(DREEPY, 1, energies=(PSYCHIC,))),
                           them=player(active=body(MAKUHITA, 2), own=False)), context)
    unready_features = {item.feature: item.value for item in unready.activations}
    ready_features = {item.feature: item.value for item in ready.activations}
    assert ready_features["combat.realization"] > unready_features.get(
        "combat.realization", 0.0)
    assert not set(ready_features).intersection({
        "combat.attack_now", "combat.attack_progress", "combat.attack_future",
        "combat.bench_reach", "combat.active_threat", "combat.line_potential",
        "combat.prize_phase_fit",
    })


def test_energy_units_without_card_detail_still_price():
    """A printout carrying unit counts but no per-card energy listing falls back to the flat
    energy worth instead of pricing the attachment at zero."""
    with_units = body(DREEPY, 1, energies=(PSYCHIC,))
    with_units["energyCards"] = []
    context = ctx()
    assert (evaluate(board(me=player(active=with_units)), context).total
            > evaluate(board(me=player(active=body(DREEPY, 1))), context).total)


def test_a_zero_max_hp_body_prices_as_intact():
    # Size-as-worth zeroed: the armed hp_value default legitimately prices printed bulk,
    # which a zero-max-hp record does not have; this pins the damage-blend fallback alone.
    context = ctx(overrides={"body.hp_per_100": 0.0})
    zeroed = board(me=player(active=body(DREEPY, 1, hp=0, max_hp=0)))
    intact = board(me=player(active=body(DREEPY, 1, hp=100, max_hp=100)))
    assert evaluate(zeroed, context).total == evaluate(intact, context).total


# --- demand branches: colorless-only, bench-full basics, surplus, fetch vocabulary ---

def test_colorless_only_energy_prices_between_dead_and_typed():
    """Pin the dead decklist so reach is closed rather than unknown."""
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


def test_in_play_line_copy_capacity_comes_from_remaining_terminal_evolutions():
    decklist = [MEGA_STARMIE] * 3 + [WATER_E] * 20
    three = board(me=player(
        active=body(DREEPY, 1),
        bench=[body(STARYU, 2), body(STARYU, 3), body(STARYU, 4)]),
        decklist=decklist)
    four = board(me=player(
        active=body(DREEPY, 1),
        bench=[body(STARYU, 2), body(STARYU, 3), body(STARYU, 4), body(STARYU, 5)]),
        decklist=decklist)

    def surplus(state):
        return sum(item.value for item in evaluate(state, ctx()).activations
                   if item.feature == "copy.surplus_in_play")

    assert surplus(three) == 0.0
    assert surplus(four) == 1.0


def test_terminal_copy_capacity_comes_from_observed_terminal_copies():
    state = board(me=player(
        active=body(DRAGAPULT, 1),
        bench=[body(DRAGAPULT, 2), body(DRAGAPULT, 3)]),
        decklist=[DRAGAPULT] * 3)

    surplus = sum(item.value for item in evaluate(state, ctx()).activations
                  if item.feature == "copy.surplus_in_play")

    assert surplus == 0.0


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

def test_charging_staryu_requires_a_legally_reachable_forward_evolution():
    """Deck presence alone is not a legal development action; a visible Mega Starmie is."""
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
    for decklist in (in_deck, gone):
        valuation = evaluate(board(me=player(
            active=body(STARYU, 1, energies=(WATER,)), hand=[WATER_E]),
            decklist=decklist), context)
        assert "development.visible_reach" not in {
            item.feature for item in valuation.activations}
    assert attach_swing(1, in_deck, extra_hand=[ULTRA_BALL, FIRE_E, FIRE_E]) > (
        attach_swing(1, in_deck))
    assert attach_swing(1, gone, extra_hand=[MEGA_STARMIE]) > attach_swing(1, in_deck)
    assert attach_swing(1, gone) < 0
    assert attach_swing(1, in_deck, hp=10) == pytest.approx(attach_swing(1, in_deck))


def test_stage_two_reach_requires_the_stage_one_or_typed_rare_candy():
    def visible(hand):
        valuation = evaluate(board(me=player(
            active=body(DREEPY, 1, energies=(FIRE,)), hand=hand)), ctx())
        return sum(item.value for item in valuation.activations
                   if item.feature == "development.visible_reach")

    assert visible([DRAGAPULT]) == 0.0
    assert visible([DRAKLOAK]) > 0.0
    assert visible([DRAGAPULT, 1079]) > 0.0


def test_body_played_this_turn_retains_evolution_hand_option_without_reach_bonus():
    active = body(DREEPY, 1, energies=(FIRE,))
    active["appearThisTurn"] = True
    valuation = evaluate(board(me=player(active=active, hand=[DRAKLOAK])), ctx())
    activations = {item.feature: item.value for item in valuation.activations}

    assert "development.visible_reach" not in activations
    assert activations["option.attack"] > 0


# --- Ignition: the multi-unit provision clause read at the demand seam ---

def test_ignition_reads_fully_live_beside_a_multi_slot_evolution():
    """Pin special-Energy worth to isolate multi-provision from a one-slot control."""
    context = ctx(overrides={"kind.special_energy": 0.10})
    beside_mega = evaluate(board(me=player(active=body(MEGA_STARMIE, 1), hand=[IGNITION])),
                           context)
    beside_dragapult = evaluate(board(me=player(active=body(DRAGAPULT, 1), hand=[IGNITION])),
                                context)
    beside_makuhita = evaluate(board(me=player(active=body(MAKUHITA, 1), hand=[IGNITION])),
                               context)
    assert beside_mega.part("me.hand") > beside_dragapult.part("me.hand") + 0.015
    assert beside_dragapult.part("me.hand") > beside_makuhita.part("me.hand") + 0.01


def test_ignition_stays_live_for_a_reachable_multi_slot_evolution():
    context = ctx(overrides={"kind.special_energy": 0.10})
    reachable = evaluate(board(me=player(
        active=body(STARYU, 1), hand=[MEGA_STARMIE, IGNITION])), context).part("me.hand")
    evolution = evaluate(board(me=player(
        active=body(STARYU, 1), hand=[MEGA_STARMIE])), context).part("me.hand")
    stranded = evaluate(board(me=player(
        active=body(STARYU, 1), hand=[IGNITION])), context).part("me.hand")
    empty = evaluate(board(me=player(
        active=body(STARYU, 1))), context).part("me.hand")

    assert reachable - evolution > stranded - empty + 0.01


def test_concentration_prefers_finishing_the_started_twin():
    """ADR-0150: armed concentration prefers 2–0; zeroed concentration ties 1–1."""
    def split(started_units, bare_units):
        return board(me=player(
            active=body(STARYU, 9),
            bench=[body(MEGA_STARMIE, 1, energies=(WATER,) * started_units),
                   body(MEGA_STARMIE, 2, energies=(WATER,) * bare_units)]))

    armed = ctx()
    assert armed.configuration["energy.concentration"] > 0
    assert evaluate(split(2, 0), armed).total > evaluate(split(1, 1), armed).total
    flat = ctx(overrides={"energy.concentration": 0.0,
                          "combat.realization": 0.0})
    assert evaluate(split(2, 0), flat).total == pytest.approx(
        evaluate(split(1, 1), flat).total)


def test_draw_engine_does_not_earn_attacker_concentration_bonus():
    dunsparce = 305
    state = board(me=player(active=body(
        dunsparce, 1, energies=(DARKNESS, DARKNESS))))

    concentration = sum(
        item.activation for item in evaluate(state, ctx()).contributions
        if item.feature == "energy.concentration")
    assert concentration == 0


def test_acceleration_open_slots_include_reachable_evolution_costs():
    def activation(first_units, second_units):
        first = body(STARYU, 1, energies=(WATER,) * first_units)
        second = body(STARYU, 2, energies=(WATER,) * second_units)
        first["appearThisTurn"] = True
        second["appearThisTurn"] = True
        state = board(me=player(
            active=body(666, 9, energies=(WATER,)),
            bench=[first, second],
            hand=[MEGA_STARMIE, WATER_E, IGNITION]))
        return sum(item.activation for item in evaluate(state, ctx()).contributions
                   if item.feature == "function.accel.open_energy_slot")

    assert activation(2, 1) >= activation(3, 0)


def test_rental_energy_on_the_bench_prices_zero():
    """ADR-0150: an end-of-turn-discarding Energy on a BENCHED body evaporates before the
    body can attack — worth zero there, priced normally on the Active."""
    def ignition_body(serial):
        shell = body(MEGA_STARMIE, serial)
        shell["energies"] = [0, 0, 0]
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
    assert rental_active.total > bare_active.total


def test_rental_subtraction_does_not_erase_persistent_attached_energy():
    shell = body(MEGA_STARMIE, 1)
    shell["energies"] = [WATER, 0, 0, 0]
    shell["energyCards"] = [
        {"id": WATER_E, "serial": 700},
        {"id": IGNITION, "serial": 701},
    ]
    valuation = evaluate(board(me=player(active=shell)), ctx())

    assert sum(item.value for item in valuation.activations
               if item.feature == "zone.attached_usable") == 1.0


def test_rental_penalty_excludes_provision_the_active_can_spend_now():
    shell = body(MEGA_STARMIE, 1)
    shell["energies"] = [0, 0, 0]
    shell["energyCards"] = [{"id": IGNITION, "serial": 701}]
    valuation = evaluate(board(me=player(active=shell)), ctx())

    assert not [item for item in valuation.activations
                if item.feature == "energy.end_of_turn_rental"]


def test_named_once_per_turn_ability_has_one_board_capacity():
    one = board(me=player(
        active=body(676, 1), bench=[body(LUNATONE, 2)], hand=[6]))
    two = board(me=player(
        active=body(676, 1), bench=[body(LUNATONE, 2), body(LUNATONE, 3)], hand=[6]))

    def draw_units(state):
        return sum(item.value for item in evaluate(state, ctx()).activations
                   if item.feature == "ability.draw_cards")

    assert draw_units(two) == pytest.approx(draw_units(one))


def test_hp_value_makes_the_evolve_pay_for_its_hand_card():
    """ADR-0151: compare armed HP pricing with a zeroed underpricing control."""
    before = board(me=player(active=body(DRAGAPULT, 9),
                             bench=[body(STARYU, 1, hp=70, max_hp=70)],
                             hand=[MEGA_STARMIE]))
    after = board(me=player(active=body(DRAGAPULT, 9),
                            bench=[body(MEGA_STARMIE, 1, hp=330, max_hp=330,
                                        under=(STARYU,))],
                            hand=[]))
    flat = ctx(overrides={"body.hp_per_100": 0.0})
    armed = ctx()
    assert armed.configuration["body.hp_per_100"] > 0
    assert swing(before, after, armed) > swing(before, after, flat)


def test_hp_value_prices_chip_damage_and_unknown_threats():
    """Size needs no store record: chipping 100 off a big body is a real gain, and a
    store-unknown 330 HP opponent body carries more threat weight than a 70 HP one."""
    context = ctx()
    fresh = board(them=player(own=False, active=body(MEGA_STARMIE, 9, hp=330, max_hp=330)))
    chipped = board(them=player(own=False, active=body(MEGA_STARMIE, 9, hp=230, max_hp=330)))
    assert swing(fresh, chipped, context) > 0

    big = board(them=player(own=False, active=body(UNKNOWN, 9, hp=330, max_hp=330)))
    small = board(them=player(own=False, active=body(UNKNOWN, 9, hp=70, max_hp=70)))
    assert evaluate(big, context).total < evaluate(small, context).total


def test_doomed_active_discount_prices_the_killable_active_as_spent():
    """ADR-0152: weakness makes Cinderace killable; zero disables doom discount."""
    def against(defender):
        # Our active sits at full 330 so the conservative incoming read (their side's
        # projected attach + evolution) never dooms US — this test isolates THEIR side.
        return board(me=player(active=body(MEGA_STARMIE, 1, energies=(WATER,),
                                           hp=330, max_hp=330)),
                     them=player(own=False, active=defender))

    killable = against(body(STARYU, 9, hp=70, max_hp=70))            # 120 >= 70
    weak_kill = against(body(666, 9, hp=160, max_hp=160))            # Cinderace: 120x2 >= 160
    safe = against(body(MEGA_STARMIE, 9, hp=330, max_hp=330))        # 120 < 330
    armed = ctx()
    assert armed.configuration["active.doomed"] > 0
    flat = ctx(overrides={"active.doomed": 0.0})
    for doomed_board in (killable, weak_kill):
        assert evaluate(doomed_board, armed).total > evaluate(doomed_board, flat).total
    assert evaluate(safe, armed).total == pytest.approx(evaluate(safe, flat).total)
    # Symmetric: OUR killable active reads as mostly spent too.
    ours = board(me=player(active=body(STARYU, 1, hp=70, max_hp=70)),
                 them=player(own=False, active=body(MEGA_STARMIE, 9, energies=(WATER,))))
    assert evaluate(ours, armed).total < evaluate(ours, flat).total


def test_our_doomed_read_uses_only_currently_payable_damage():
    def ours_vs(attacker):
        return board(me=player(active=body(MEGA_STARMIE, 1, hp=150, max_hp=330)),
                     them=player(own=False, active=attacker))

    armed = ctx()
    flat = ctx(overrides={"active.doomed": 0.0})
    doomed = ours_vs(body(DRAGAPULT, 9, energies=(FIRE, PSYCHIC)))
    assert evaluate(doomed, armed).total < evaluate(doomed, flat).total
    one_short = ours_vs(body(DRAGAPULT, 9, energies=(FIRE,)))
    assert evaluate(one_short, armed).total == pytest.approx(
        evaluate(one_short, flat).total)


def test_doomed_active_does_not_claim_next_turn_combat_realization():
    def combat(energies):
        state = board(
            me=player(active=body(
                MEGA_STARMIE, 1, hp=150, max_hp=330, energies=energies)),
            them=player(own=False, active=body(
                MEGA_STARMIE, 9, hp=330, max_hp=330,
                energies=(WATER, WATER, WATER))))
        return next((item.activation for item in evaluate(state, ctx()).contributions
                     if item.feature == "combat.realization"), 0.0)

    assert combat((WATER, WATER, WATER)) == pytest.approx(combat(()))


def test_terminal_ko_route_is_not_double_counted_as_combat_realization():
    def combat(energies):
        state = board(
            me=player(active=body(MEGA_STARMIE, 1, energies=energies)),
            them=player(own=False, active=body(
                DRAGAPULT, 9, hp=70, max_hp=320), prizes=2))
        return next((item.activation for item in evaluate(state, ctx()).contributions
                     if item.feature == "combat.realization"), 0.0)

    assert combat((WATER,)) == pytest.approx(combat((WATER, WATER, WATER)))


def test_combat_readiness_does_not_reprice_against_remaining_target_hp():
    def against(target_hp):
        return board(
            me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC))),
            them=player(own=False, active=body(
                MEGA_STARMIE, 9, hp=target_hp, max_hp=330)))

    healthy = body_capability(
        against(150).me.active, against(150).me, against(150).them,
        against(150), ctx())
    damaged = body_capability(
        against(20).me.active, against(20).me, against(20).them,
        against(20), ctx())

    assert healthy.realization == pytest.approx(damaged.realization)
    assert healthy.attack_now != damaged.attack_now


def test_whole_board_value_does_not_depend_on_attack_history():
    state = board(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC))),
        them=player(own=False, active=body(
            MEGA_STARMIE, 9, hp=150, max_hp=330)))
    attacked = replace(state, events=(AttackEvent(
        15, (("cardId", DRAGAPULT), ("playerIndex", state.seat)), True),))

    assert evaluate(attacked, ctx()).total == pytest.approx(evaluate(state, ctx()).total)


def test_usable_energy_on_our_doomed_active_is_ammunition_not_investment():
    """Ruling d98fc4c74107: usable Energy on a doomed active remains ammunition."""
    def ours(energies):
        return board(me=player(active=body(MEGA_STARMIE, 1, hp=150, max_hp=330,
                                           energies=energies)),
                     them=player(own=False, active=body(
                         DRAGAPULT, 9, energies=(FIRE, PSYCHIC))))

    # Concentration is zeroed both sides: progress credit is investment-shaped and stays
    # under the discount; only the direct usable-Energy worth is the ammunition here.
    armed = ctx(overrides={"energy.concentration": 0.0})
    assert armed.configuration["active.doomed"] > 0
    flat = ctx(overrides={"active.doomed": 0.0, "energy.concentration": 0.0})
    armed_swing = (evaluate(ours((WATER,)), armed).part("me.bodies")
                   - evaluate(ours(()), armed).part("me.bodies"))
    flat_swing = (evaluate(ours((WATER,)), flat).part("me.bodies")
                  - evaluate(ours(()), flat).part("me.bodies"))
    assert armed_swing == pytest.approx(flat_swing)
    assert (evaluate(ours(()), armed).part("me.bodies")
            < evaluate(ours(()), flat).part("me.bodies"))
