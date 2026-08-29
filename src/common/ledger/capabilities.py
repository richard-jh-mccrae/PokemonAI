from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from common.cards import card_clauses
from common.cards.card_facts import (
    BASIC_ENERGY, COLORLESS, DARKNESS, DRAGON, FIGHTING, GRASS, METAL, PSYCHIC,
    SUPPORTER, WILDCARD, Clause, EnergyCard, PokemonCard, TrainerCard,
)
from common.cards.functions.damage import bench_reach
from common.cards.functions.draw import draw_branches
from common.cards.functions.energy import provision_units
from common.cards.functions.fetch import DEADNESS, fetch_target_matches

WEAKNESS_MULTIPLIER = 2
RESISTANCE_REDUCTION = 30
COMPLETION_EXPONENT = 2
DEFAULT_PRIZE_COUNT = 6
COMEBACK_PRIZE_THRESHOLD = 3
DAMAGE_UNIT_HP = 100
DAMAGE_COUNTER_HP = 10
DAMAGE_RANGE_BOUND_COUNT = 2
FUTURE_TURN_DISCOUNT = 0.8
DISCARD_AREA = 3
ACTIVE_AREA = 4
IN_PLAY_AREAS = frozenset((4, 5))
KNOCKOUT_EVENT_KINDS = frozenset((6, 7))
MIN_SELF_DAMAGE_COUNTERS = 2
COIN_HEADS_PROBABILITY = 0.5
TERMINAL_LOSS_UNITS = 100.0
BOUNCE_ENERGY_HAND_UNIT = 0.5
ATTACHED_ENERGY_MATERIAL_UNIT = 0.25
ATTACK_EVENT_KIND = 15
SWITCH_EVENT_KIND = 8
DAMAGE_PROTECTION_THRESHOLD_HP = 200
ENERGY_COUNT_THRESHOLD = 3
LOW_REMAINING_HP_THRESHOLD = 30
HEAL_TARGET_HP = 30
TEAM_ROCKET_ENERGY_CARD_ID = 15
ANCIENT_POKEMON_IDS = frozenset({56, 62, 63, 171, 226, 986})
CLAUSE_COST_UNITS = {
    "bottom_2": 2.0,
    "discard_1": 1.0,
    "discard_2": 2.0,
    "discard_3": 3.0,
    "discard_hand": "hand",
    "shuffle_3_energy_into_deck": 3.0,
}
RIDER_COST_UNITS = {
    "discard_basic_f_energy": 1.0,
    "discard_eot": 1.0,
    "discard_own_energy": 1.0,
    "discard_remainder": 1.0,
    "other_to_bottom": 1.0,
    "recoil": 1.0,
    "self_ko": 1.0,
    "shuffle_counted_into_deck": 1.0,
    "shuffle_own_hand_in": "hand",
    "shuffle_self_in": 1.0,
}
RIDER_BENEFIT_UNITS = frozenset({
    "attached_cards_too", "both_hands_to_bottom", "bounce_energy_to_hand",
    "confuse_target", "cure_existing", "damage_new_active", "draw_1",
    "heal_30_target", "poison_new_active", "self_switch", "shuffle_before_place",
    "shuffle_both_hands", "skip_stage1",
})

CLAUSE_PARAMETER_VALUE_UNITS = {
    "allowance": {"body": 0.75, "card": 1.0},
    "dest": {
        "bench": 1.1, "deck_top": 0.7, "hand": 1.0, "in_play": 1.2,
        "new_benched": 1.1, "opp_any": 1.0,
    },
    "dig_from": {"bottom": 0.9},
    "duration": {
        "next_turn": FUTURE_TURN_DISCOUNT,
        "opp_next_turn": FUTURE_TURN_DISCOUNT,
    },
    "rider": {
        "attached_cards_too": 0.5, "both_hands_to_bottom": 0.5,
        "bounce_energy_to_hand": -0.5, "confuse_target": 1.0,
        "cure_existing": 1.0, "damage_new_active": 1.0,
        "discard_basic_f_energy": -1.0, "discard_eot": -1.0,
        "discard_own_energy": -1.0, "discard_remainder": -0.5,
        "draw_1": 1.0, "heal_30_target": 0.3, "other_to_bottom": -0.5,
        "poison_new_active": 1.0, "recoil": -1.0, "self_ko": -1.0,
        "self_switch": 1.0, "shuffle_before_place": 0.25,
        "shuffle_both_hands": 0.5, "shuffle_counted_into_deck": -0.5,
        "shuffle_own_hand_in": -0.5, "shuffle_self_in": -1.0,
        "skip_stage1": 1.0,
    },
    "scope": {
        "damage_and_effects": 1.0, "resistance": 0.8, "weakness": 1.0,
    },
    "source": {
        "attack_damage": 0.8, "deck": 0.75, "discard": 0.65, "hand": 0.9,
        "milled_pokemon": 0.5, "opponent_attack": 0.8,
        "opponent_effects_and_abilities": 0.8, "own_bench": 0.75, "self": 1.0,
    },
    "target": {
        "any": 1.25, "any_pokemon": 1.25, "basic": 0.8,
        "basic_energy": 0.8, "basic_pokemon": 0.8, "bench_only": 0.75,
        "benched": 0.75, "both_actives": 1.5, "defending": 1.0,
        "energy": 0.9, "evolution": 0.75, "future": 0.6, "item": 0.75,
        "mega": 0.6, "opp_active": 1.0, "opp_any": 1.25,
        "opp_bench": 0.75,
        "opp_dragon_pokemon": 0.4, "opponent_active": 1.0,
        "opponent": 1.0, "own_bench": 0.75, "own_line": 0.6,
        "own_type": 0.6, "pokemon": 1.0, "pokemon_or_basic_energy": 1.0,
        "pokemon_ex": 0.6, "self": 0.5, "stadium": 0.5, "stage1": 0.65,
        "stage2": 0.5, "supporter": 0.75, "tera": 0.4, "tool": 0.75,
        "trainer": 0.9,
    },
    "timing": {
        "after_weakness_resistance": 0.9,
        "before_weakness_resistance": 1.0,
    },
    "trigger": {
        "on_attach": 0.9, "on_bench_play": 0.9,
        "on_evolve": FUTURE_TURN_DISCOUNT,
        "on_fetch_success": FUTURE_TURN_DISCOUNT, "setup": 0.7,
    },
    "zone": {
        "deck": 0.75, "discard": 0.65, "hand": 0.9,
        "opp_any": 1.0, "own_any": 1.0,
    },
}


def _quantity(value, default=0.0) -> float:
    try:
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return float(default)


def _all_own_pokemon_team_rocket(side, ctx) -> bool:
    bodies = tuple(side.bodies)
    return bool(bodies) and all(
        getattr(ctx.facts(body.card.card_id), "name", "").casefold().startswith(
            "team rocket")
        for body in bodies)


def _draw_branches(clause, side, opponent, ctx, *, cards_leaving_hand=0):
    return draw_branches(
        clause, side.prize_count, opponent.prize_count,
        my_hand_size=side.hand_count,
        all_own_pokemon_team_rocket=_all_own_pokemon_team_rocket(side, ctx),
        cards_leaving_hand=cards_leaving_hand)


def expected_draw_counts(clause, side, opponent, ctx, *, cards_leaving_hand=0):
    branches = _draw_branches(
        clause, side, opponent, ctx, cards_leaving_hand=cards_leaving_hand)
    if not branches:
        return _quantity(clause.amount), _quantity(clause.opponent_amount)
    divisor = len(branches)
    return (sum(mine for mine, _theirs in branches) / divisor,
            sum(theirs for _mine, theirs in branches) / divisor)


@dataclass(frozen=True, slots=True)
class Capability:
    attack_now: float = 0.0
    attack_progress: float = 0.0
    attack_future: float = 0.0
    attack_potential: float = 0.0
    line_potential: float = 0.0
    bench_reach: float = 0.0
    draw_cards: float = 0.0
    search_cards: float = 0.0
    damage_move: float = 0.0
    healing: float = 0.0
    acceleration: float = 0.0
    denial: float = 0.0
    resource_cost: float = 0.0
    self_cost: float = 0.0
    ability_future: float = 0.0
    retreat_progress: float = 0.0
    gaps: tuple[str, ...] = ()

    def option_units(self) -> float:
        benefits = (
            self.attack_now, self.attack_progress, self.attack_future,
            self.attack_potential, self.line_potential, self.bench_reach,
            self.draw_cards, self.search_cards, self.damage_move, self.healing,
            self.acceleration, self.denial, self.ability_future, self.retreat_progress,
        )
        return sum(benefits) - self.resource_cost - self.self_cost


@dataclass(frozen=True, slots=True)
class OptionUnits:
    hp: float = 0.0
    attack: float = 0.0
    draw: float = 0.0
    search: float = 0.0
    acceleration: float = 0.0
    denial: float = 0.0
    healing: float = 0.0
    mobility: float = 0.0
    energy: float = 0.0
    cost: float = 0.0

    @property
    def total(self) -> float:
        return (self.hp + self.attack + self.draw + self.search + self.acceleration
                + self.denial + self.healing + self.mobility + self.energy - self.cost)

    def activations(self):
        return (
            ("option.hp", self.hp),
            ("option.attack", self.attack),
            ("option.draw", self.draw),
            ("option.search", self.search),
            ("option.acceleration", self.acceleration),
            ("option.denial", self.denial),
            ("option.healing", self.healing),
            ("option.mobility", self.mobility),
            ("option.energy", self.energy),
            ("option.cost", self.cost),
        )


def unmet_cost_slots(provisions, requirements) -> tuple[int, ...]:
    remaining = [int(unit) for unit in provisions]
    unpaid = []
    colorless = []
    for slot, required in enumerate(requirements):
        if int(required) == COLORLESS:
            colorless.append(slot)
            continue
        found = next((index for index, supplied in enumerate(remaining)
                      if supplied in {int(required), WILDCARD}), None)
        if found is None:
            unpaid.append(slot)
        else:
            remaining.pop(found)
    paid_colorless = min(len(colorless), len(remaining))
    return tuple((*unpaid, *colorless[paid_colorless:]))


def payment_fraction(provisions, requirements) -> float:
    requirements = tuple(requirements)
    if not requirements:
        return 1.0
    return (len(requirements) - len(unmet_cost_slots(provisions, requirements))) \
        / len(requirements)


def _side_names(side, ctx, *, bench_only=False) -> tuple[str, ...]:
    bodies = side.bench if bench_only else side.bodies
    return tuple(facts.name for body in bodies
                 if isinstance((facts := ctx.facts(body.card.card_id)), PokemonCard))


def _condition_probability(condition, body, side, board, ctx, *, clause=None) -> float | None:
    if not condition:
        return 1.0
    condition = str(condition)
    opponent_side = board.them if side is board.me else board.me
    side_seat = board.seat if side is board.me else 1 - board.seat
    if condition == "festival_grounds_in_play":
        return float(any(getattr(ctx.facts(card.card_id), "name", "") == "Festival Grounds"
                         for card in getattr(board, "stadium", ())))
    if condition == "active_has_festival_lead":
        active = side.active
        facts = None if active is None else ctx.facts(active.card.card_id)
        return float(any(ability.name == "Festival Lead"
                         for ability in getattr(facts, "abilities", ())))
    if condition == "damage_200_plus":
        return float(side.active is not None and opponent_side.active is not None
                     and best_current_damage(
                         opponent_side.active, opponent_side, side, board, ctx)
                     >= DAMAGE_PROTECTION_THRESHOLD_HP)
    subject = body if body is not None else side.active
    if condition == "energy_3_plus":
        return float(subject is not None
                     and len(subject.energies) >= ENERGY_COUNT_THRESHOLD)
    if condition == "first_turn":
        return float(board.turn.number <= 1)
    if condition == "going_second_first_turn":
        return float(board.turn.number <= 1 and board.turn.first_player != side_seat)
    if condition == "opp_active_damaged":
        active = opponent_side.active
        return float(active is not None and active.hp < active.max_hp)
    if condition == "own_bench_damaged":
        return float(any(other.hp < other.max_hp for other in side.bench))
    if condition == "self_damage_counters_2_plus":
        return float(body is not None and
                     body.max_hp - body.hp >= MIN_SELF_DAMAGE_COUNTERS * DAMAGE_COUNTER_HP)
    if condition == "full_hp":
        return float(body is not None and body.hp >= body.max_hp)
    if condition == "went_first":
        return float(board.turn.first_player == side_seat)
    if condition == "bench_has_named":
        wanted = str(getattr(clause, "named", "")).casefold()
        return float(any(name.casefold() == wanted
                         for name in _side_names(side, ctx, bench_only=True)))
    if condition == "more_prizes_remaining_than_opp":
        return float(side.prize_count > opponent_side.prize_count)
    if condition == "moved_to_active_this_turn":
        if body is None or body is not side.active:
            return 0.0
        serial = getattr(getattr(body, "card", None), "serial", None)
        moved = any(
            event.recognized
            and (fields := dict(event.public_fields)).get("playerIndex") == side_seat
            and ((fields.get("toArea") == ACTIVE_AREA
                  and (serial is None or fields.get("serial") == serial))
                 or (event.kind == SWITCH_EVENT_KIND
                     and (serial is None or fields.get("serialBench") == serial)))
            for event in board.events)
        retreated = side is board.me and board.turn.retreated
        return float(moved or retreated)
    if condition == "name_in_opp_discard":
        wanted = str(getattr(clause, "name_family", "") or "").casefold()
        return float(any(wanted and wanted in getattr(
            ctx.facts(card.card_id), "name", "").casefold()
                         for card in opponent_side.discard))
    if condition == "not_first_turn":
        return float(board.turn.number > 1)
    if condition == "once_per_turn_ability":
        return 1.0
    if condition.endswith("_in_play"):
        wanted = condition.removesuffix("_in_play").replace("_", " ").casefold()
        return float(any(name.casefold() == wanted for name in _side_names(side, ctx)))
    if condition.endswith("_on_bench"):
        wanted = condition.removesuffix("_on_bench").replace("_", " ").casefold()
        return float(any(name.casefold() == wanted
                         for name in _side_names(side, ctx, bench_only=True)))
    if condition in {"dark_energy_attached", "energy_type_attached"}:
        energy_type = getattr(clause, "condition_energy_type", None)
        return float(subject is not None and energy_type is not None
                     and int(energy_type) in subject.energies)
    if condition == "damaged":
        return float(body is not None and body.hp < body.max_hp)
    if condition == "opp_active_ex":
        facts = (None if opponent_side.active is None else
                 ctx.facts(opponent_side.active.card.card_id))
        return float(bool(getattr(facts, "is_rule_box", False)))
    if condition == "other_ancient_attacked_last_turn":
        own_id = getattr(getattr(body, "card", None), "card_id", None)
        return float(any(
            event.kind == ATTACK_EVENT_KIND
            and (fields := dict(event.public_fields)).get("playerIndex") == side_seat
            and fields.get("cardId") in ANCIENT_POKEMON_IDS
            and fields.get("cardId") != own_id
            for event in board.events if event.recognized))
    if condition == "played_supporter_this_turn":
        return float(board.turn.supporter_played)
    if condition == "remaining_hp_30_or_less":
        return float(any(0 < target.hp <= LOW_REMAINING_HP_THRESHOLD
                         for target in side.bodies))
    if condition == "self_active":
        return float(body is not None and body is side.active)
    if condition == "self_special_condition":
        return float(body is not None and body is side.active and any(
            bool(getattr(side, status)) for status in
            ("asleep", "paralyzed", "confused", "poisoned", "burned")))
    if condition == "solrock_in_play":
        return float(any(name.casefold() == "solrock" for name in _side_names(side, ctx)))
    if condition == "team_rocket_energy_attached":
        return float(subject is not None and any(
            card.card_id == TEAM_ROCKET_ENERGY_CARD_ID
            or getattr(ctx.facts(card.card_id), "name", "").casefold()
            == "team rocket's energy"
            for card in subject.energy_cards))
    if condition == "stadium_in_play":
        return float(bool(board.stadium))
    if condition == "pokemon_ko_last_turn":
        return 1.0 if _knockout_visible(board) else 0.0
    if condition == "exactly_6_prizes_remaining":
        return float(side.prize_count == DEFAULT_PRIZE_COUNT)
    if condition == "opp_3_or_fewer_prizes":
        return float(opponent_side.prize_count <= COMEBACK_PRIZE_THRESHOLD)
    return None


_DAMAGE_CLAUSES = frozenset({
    "attack_debuff", "bench_snipe", "bench_spread", "damage_boost",
    "damage_protection", "damage_reduction", "heal", "hp_bonus", "move_damage",
    "recoil",
})
_ENERGY_CLAUSES = frozenset({
    "accel", "attack_cost_reduction", "cost_reduction", "discard_opp_energy",
    "energy_bounce", "energy_double", "energy_provide", "energy_recur", "move_energy",
    "retreat_reduction", "self_discard_energy",
})


def _basic_energy_count(cards, ctx) -> int:
    return sum(
        isinstance(ctx.facts(card.card_id), EnergyCard)
        and ctx.facts(card.card_id).kind == BASIC_ENERGY for card in cards)


def _basic_energy_in_hand(side, ctx, energy_type=None):
    return sum(
        isinstance((facts := ctx.facts(card.card_id)), EnergyCard)
        and facts.kind == BASIC_ENERGY
        and (energy_type is None or facts.provides == int(energy_type))
        for card in tuple(side.hand))


def _discardable_basic_energy(side, ctx) -> int:
    known = sum(_basic_energy_count(body.energy_cards, ctx) for body in side.bodies)
    represented = sum(len(body.energy_cards) for body in side.bodies)
    anonymous = max(0, sum(len(body.energies) for body in side.bodies) - represented)
    return known + anonymous


def _expected_milled_basic(clause, side, board, ctx) -> float:
    sample = max(1.0, _quantity(clause.amount, 1))
    remaining = max(1, side.deck_count)
    known = sum(
        count for card_id, count in dict(board.deck_counts).items()
        if isinstance(ctx.facts(card_id), EnergyCard)
        and ctx.facts(card_id).kind == BASIC_ENERGY
        and (clause.energy_type is None
             or ctx.facts(card_id).provides == clause.energy_type))
    return sample * known / remaining


def _per_units(clause, body, side, opponent, board, ctx) -> float:
    per = str(clause.per or clause.amount_per or "")
    if not per:
        return 1.0
    values = {
        "energy_on_opp_active": 0 if opponent.active is None else len(opponent.active.energies),
        "damage_counter_on_self": (0 if body is None else
                                   max(0, body.max_hp - body.hp) // DAMAGE_COUNTER_HP),
        "damage_counter_self": (0 if body is None else
                                max(0, body.max_hp - body.hp) // DAMAGE_COUNTER_HP),
        "damage_counter_own_bench": sum(
            max(0, target.max_hp - target.hp) // DAMAGE_COUNTER_HP for target in side.bench),
        "card_in_own_hand": side.hand_count,
        "own_bench": len(side.bench),
        "their_bench": len(opponent.bench),
        "opp_bench": len(opponent.bench),
        "all_bench": len(side.bench) + len(opponent.bench),
        "card_in_opp_hand": opponent.hand_count,
        "energy_on_both_actives": ((0 if body is None else len(body.energies))
                                    + (0 if opponent.active is None
                                       else len(opponent.active.energies))),
        "energy_on_own_all": sum(len(target.energies) for target in side.bodies),
        "my_ancient": sum(target.card.card_id in ANCIENT_POKEMON_IDS
                          for target in side.bodies),
        "energy_discarded_this_way": _discardable_basic_energy(side, ctx),
        "basic_energy_discarded_this_way": _expected_milled_basic(
            clause, side, board, ctx),
        "heads": 1.0,
        "attached_fighting_energy": (0 if body is None else
                                     sum(energy == FIGHTING for energy in body.energies)),
        "basic_energy_own_discard": sum(
            isinstance(ctx.facts(card.card_id), EnergyCard)
            and ctx.facts(card.card_id).kind == BASIC_ENERGY for card in side.discard),
        "basic_energy_in_opp_discard": sum(
            isinstance(ctx.facts(card.card_id), EnergyCard)
            and ctx.facts(card.card_id).kind == BASIC_ENERGY for card in opponent.discard),
        "opp_prizes_taken": max(0, DEFAULT_PRIZE_COUNT - opponent.prize_count),
        "ethans_adventure_in_own_discard": sum(
            "ethan's adventure" in getattr(ctx.facts(card.card_id), "name", "").casefold()
            for card in side.discard),
    }
    try:
        return float(values[per])
    except KeyError:
        raise KeyError(f"unpriced clause per unit {per!r}") from None


def clause_cost_units(clause, side) -> float:
    cost = getattr(clause, "cost", None)
    if not cost:
        return 0.0
    try:
        units = CLAUSE_COST_UNITS[str(cost)]
    except KeyError:
        raise KeyError(f"unpriced clause cost {cost!r}") from None
    return float(side.hand_count if units == "hand" else units)


def clause_rider_cost_units(clause, side) -> float:
    rider = getattr(clause, "rider", None)
    if not rider or rider in RIDER_BENEFIT_UNITS:
        return 0.0
    try:
        units = RIDER_COST_UNITS[str(rider)]
    except KeyError:
        raise KeyError(f"unpriced clause rider {rider!r}") from None
    return float(side.hand_count if units == "hand" else units)


def _facts_on_side(side, ctx):
    return tuple(ctx.facts(body.card.card_id) for body in side.bodies)


def _named_units(value, side, board, ctx, *, family=False):
    wanted = str(value).casefold()
    visible = (*_facts_on_side(side, ctx),
               *(ctx.facts(card.card_id) for card in tuple(side.hand)),
               *(ctx.facts(card.card_id) for card in side.discard))
    known_deck = (0 if side is not board.me else sum(
        count for card_id, count in (board.deck_counts or ())
        if wanted in getattr(ctx.facts(card_id), "name", "").casefold()
        if family or getattr(ctx.facts(card_id), "name", "").casefold() == wanted))
    return float(known_deck + sum(
        wanted in getattr(candidate, "name", "").casefold()
        if family else getattr(candidate, "name", "").casefold() == wanted
        for candidate in visible if candidate is not None))


def _energy_eligibility_units(value, clause, side, opponent, board, ctx):
    wanted_basic = str(value) == "basic"
    if clause.kind == "discard_opp_energy":
        rows = tuple(
            ctx.facts(card.card_id)
            for target in opponent.bodies for card in target.energy_cards)
        return float(sum(
            isinstance(candidate, EnergyCard)
            and (candidate.kind == BASIC_ENERGY) == wanted_basic
            for candidate in rows))
    source = clause.source or clause.zone
    if source in {"deck", "discard", "hand"}:
        rows = _zone_fact_counts(source, side, board, ctx)
        available = sum(
            count for candidate, count in rows
            if isinstance(candidate, EnergyCard)
            and (candidate.kind == BASIC_ENERGY) == wanted_basic)
        return _amount_capacity(clause, available)
    explicit = tuple(
        ctx.facts(card.card_id)
        for target in side.bodies for card in target.energy_cards)
    available = sum(
        isinstance(candidate, EnergyCard)
        and (candidate.kind == BASIC_ENERGY) == wanted_basic
        for candidate in explicit)
    if wanted_basic:
        available = max(available, sum(len(target.energies) for target in side.bodies))
    return _amount_capacity(clause, available)


def _typed_eligibility_units(value, clause, side, opponent, board, ctx):
    wanted = int(value)
    if clause.rider == "discard_basic_f_energy":
        return _amount_capacity(
            clause, _basic_energy_in_hand(side, ctx, wanted))
    source = clause.source or clause.zone
    if source in {"deck", "discard", "hand"}:
        rows = _zone_fact_counts(source, side, board, ctx)
        pokemon_target = (clause.kind == "fetch"
                          and clause.target not in {"basic_energy", "energy"})
        available = sum(
            count for candidate, count in rows
            if ((isinstance(candidate, PokemonCard)
                 and candidate.energy_type == wanted) if pokemon_target else
                (isinstance(candidate, EnergyCard)
                 and candidate.provides == wanted))
            and (clause.kind != "fetch"
                 or fetch_target_matches(clause, candidate, reading=DEADNESS)))
        return _amount_capacity(clause, available)
    candidates = _clause_candidate_rows(
        clause, side, opponent, board, ctx, None)
    pokemon_available = sum(
        count for candidate, count in candidates
        if isinstance(candidate, PokemonCard) and candidate.energy_type == wanted)
    attached = sum(
        energy == wanted for target in side.bodies for energy in target.energies)
    return _amount_capacity(clause, max(pokemon_available, attached))


def _target_type_units(value, clause, side, opponent, board, ctx, body):
    wanted = int(value)
    if clause.kind == "fetch" and clause.zone in {"deck", "discard", "hand"}:
        rows = _zone_fact_counts(clause.zone, side, board, ctx)
    else:
        rows = _clause_candidate_rows(
            clause, side, opponent, board, ctx, body)
    available = sum(
        count for candidate, count in rows
        if isinstance(candidate, PokemonCard) and candidate.energy_type == wanted)
    return _amount_capacity(clause, available)


def _amount_capacity(clause, available):
    if clause is None or clause.amount is None:
        return min(float(available), 1.0)
    if clause.amount in {"all", "any"}:
        return float(available)
    return min(float(available), max(1.0, _quantity(clause.amount, 1)))


def _zone_fact_counts(value, side, board, ctx):
    value = str(value)
    if value == "deck" and side is board.me:
        return tuple((ctx.facts(card_id), count)
                     for card_id, count in (board.deck_counts or ()))
    if value == "discard":
        return tuple((ctx.facts(card.card_id), 1) for card in side.discard)
    if value == "hand":
        return tuple((ctx.facts(card.card_id), 1) for card in tuple(side.hand))
    return ()


def _eligible_zone_units(clause, side, board, ctx):
    rows = _zone_fact_counts(clause.zone, side, board, ctx)
    available = sum(
        count for facts, count in rows
        if fetch_target_matches(clause, facts, reading=DEADNESS))
    if not rows and clause.zone == "deck":
        available = side.deck_count
    return _amount_capacity(clause, available)


def _clause_candidate_rows(clause, side, opponent, board, ctx, body):
    if clause.kind == "fetch" and clause.zone in {"deck", "discard", "hand"}:
        return _zone_fact_counts(clause.zone, side, board, ctx)
    if clause.source == "milled_pokemon":
        return tuple((ctx.facts(card.card_id), 1) for card in side.discard)
    if clause.applies_to == "attached_body" and body is None:
        return tuple((candidate, 1) for candidate in _facts_on_side(side, ctx))
    if clause.applies_to in {"self", "attached_body"}:
        target = body or side.active
        return (() if target is None else ((ctx.facts(target.card.card_id), 1),))
    if clause.applies_to in {"own_bench", "benched"}:
        return tuple((ctx.facts(target.card.card_id), 1) for target in side.bench)
    if clause.target in {"opp_active", "opponent_active", "defending"}:
        return (() if opponent.active is None else
                ((ctx.facts(opponent.active.card.card_id), 1),))
    if clause.target in {"own_bench", "bench_only", "benched"}:
        return tuple((ctx.facts(target.card.card_id), 1) for target in side.bench)
    return tuple((candidate, 1) for candidate in _facts_on_side(side, ctx))


def _zone_units(value, side, opponent, board, ctx, *, clause=None):
    value = str(value)
    if clause is not None and clause.kind == "fetch" \
            and value in {"deck", "discard", "hand"}:
        return _eligible_zone_units(clause, side, board, ctx)
    if value == "deck":
        return _amount_capacity(clause, side.deck_count)
    if value == "discard":
        return _amount_capacity(clause, len(side.discard))
    if value == "hand":
        return _amount_capacity(clause, side.hand_count)
    if value == "own_any":
        return _amount_capacity(
            clause, len(side.bodies) + side.hand_count + len(side.discard))
    if value == "opp_any":
        return _amount_capacity(
            clause, len(opponent.bodies) + opponent.hand_count + len(opponent.discard))
    raise KeyError(f"unpriced clause zone {value!r}")


def _target_units(value, clause, facts, side, opponent, board, ctx, body):
    value = str(value)
    if clause.kind == "fetch":
        return (_eligible_zone_units(clause, side, board, ctx)
                if clause.zone in {"deck", "discard", "hand"} else 0.0)
    if value in {"self"}:
        return float(body is not None or isinstance(facts, PokemonCard))
    if value in {"own_bench", "bench_only", "benched", "future", "own_line",
                 "own_type"}:
        return float(len(side.bench))
    if value in {"opp_active", "opponent_active", "defending"}:
        return float(opponent.active is not None)
    if value in {"opp_bench"}:
        return float(len(opponent.bench))
    if value in {"opp_any", "any", "any_pokemon", "pokemon"}:
        return float(len(side.bodies) + len(opponent.bodies))
    if value == "both_actives":
        return float((side.active is not None) + (opponent.active is not None))
    if value == "opponent":
        return float(bool(opponent.bodies))
    if value == "opp_dragon_pokemon":
        return float(sum(getattr(candidate, "energy_type", None) == DRAGON
                         for candidate in _facts_on_side(opponent, ctx)))
    if value in {"basic", "basic_pokemon", "evolution", "mega", "pokemon_ex",
                 "stage1", "stage2", "tera"}:
        predicates = {
            "basic": lambda candidate: getattr(candidate, "evolves_from", None) is None,
            "basic_pokemon": lambda candidate: getattr(
                candidate, "evolves_from", None) is None,
            "evolution": lambda candidate: getattr(candidate, "evolves_from", None) is not None,
            "mega": lambda candidate: "mega" in getattr(candidate, "name", "").casefold(),
            "pokemon_ex": lambda candidate: getattr(candidate, "is_rule_box", False),
            "stage1": lambda candidate: getattr(candidate, "stage", None) == "stage1",
            "stage2": lambda candidate: getattr(candidate, "stage", None) == "stage2",
            "tera": lambda candidate: getattr(candidate, "tera", False),
        }
        return float(sum(predicates[value](candidate)
                         for candidate in (*_facts_on_side(side, ctx),
                                           *_facts_on_side(opponent, ctx))))
    if value in {"basic_energy", "energy"}:
        return float(sum(len(target.energies) for target in side.bodies)
                     + _basic_energy_count(tuple(side.hand), ctx)
                     + _basic_energy_count(side.discard, ctx))
    if value in {"item", "stadium", "supporter", "tool", "trainer"}:
        visible = sum(fetch_target_matches(
            Clause("fetch", target=value), ctx.facts(card.card_id), reading=DEADNESS)
            for card in (*tuple(side.hand), *tuple(side.discard)))
        known_deck = sum(
            count for card_id, count in board.deck_counts
            if fetch_target_matches(Clause("fetch", target=value),
                                    ctx.facts(card_id), reading=DEADNESS))
        return float(visible + known_deck)
    raise KeyError(f"unpriced clause target {value!r}")


def _applies_to_units(value, clause, side, ctx):
    value = str(value)
    candidates = tuple(side.bodies)
    if value in {"self", "attached_body"}:
        return float(bool(candidates))
    if value in {"own_bench", "benched"}:
        return float(len(side.bench))
    if value == "own_pokemon":
        return float(len(candidates))
    count = 0
    for body in candidates:
        facts = ctx.facts(body.card.card_id)
        name = getattr(facts, "name", "").casefold()
        stage = getattr(facts, "stage", None)
        energy_type = getattr(facts, "energy_type", None)
        count += bool(
            (value in {"basic", "own_basic"} and getattr(facts, "evolves_from", None) is None)
            or (value == "basic_non_dark" and getattr(facts, "evolves_from", None) is None
                and energy_type != DARKNESS)
            or (value == "grass" and energy_type == GRASS)
            or (value == "fighting" and energy_type == FIGHTING)
            or (value == "metal" and energy_type == METAL)
            or (value == "has_ability" and bool(getattr(facts, "abilities", ())))
            or (value == "has_energy_attached" and bool(body.energies))
            or (value == "name_family"
                and bool(family := str(clause.name_family or "").casefold())
                and family in name)
            or (value == "no_rule_box" and not getattr(facts, "is_rule_box", False))
            or (value == "own_evolved" and getattr(facts, "evolves_from", None) is not None)
            or (value == "own_evolution_r_pokemon" and stage in {"stage1", "stage2"})
            or (value == "self_ko_abilities" and bool(getattr(facts, "abilities", ())))
            or (value == "stage2" and stage == "stage2"))
    return float(count)


def _effect_units(value, clause, facts, side, opponent, board, ctx, body):
    value = str(value)
    applies = max(1.0, _applies_to_units(
        clause.applies_to or "self", clause, side, ctx))
    opposing_facts = (None if opponent.active is None else
                      ctx.facts(opponent.active.card.card_id))
    incoming_now = (0.0 if opponent.active is None else best_current_damage(
        opponent.active, opponent, side, board, ctx) / DAMAGE_UNIT_HP)
    incoming_later = FUTURE_TURN_DISCOUNT * max((
        attack.damage or attack.damage_fix or attack.damage_max or 0
        for attack in getattr(opposing_facts, "attacks", ())), default=0) / DAMAGE_UNIT_HP
    incoming = max(incoming_now, incoming_later)
    amount = _quantity(clause.amount, 1)
    if value == "attack_fails_on_tails":
        printed = max((attack.damage or attack.damage_fix or attack.damage_max or 0
                       for attack in getattr(facts, "attacks", ())), default=0)
        return -COIN_HEADS_PROBABILITY * printed / DAMAGE_UNIT_HP
    if value == "damage_boost":
        return amount * applies / DAMAGE_UNIT_HP
    if value == "damage_counters":
        return -amount * DAMAGE_COUNTER_HP * applies / DAMAGE_UNIT_HP
    if value == "damage_protection":
        return incoming
    if value == "damage_reduction":
        return min(incoming, amount / DAMAGE_UNIT_HP) * applies
    if value == "discard_opp_energy":
        return float(sum(len(target.energies) for target in opponent.bodies))
    if value == "evolve_early":
        return FUTURE_TURN_DISCOUNT * applies
    if value == "gust":
        return float(len(opponent.bench))
    if value == "hp_delta":
        return amount * applies / DAMAGE_UNIT_HP
    if value == "prevent_damage":
        return incoming * applies
    if value == "prevent_damage_counters":
        return float(len(side.bench))
    if value == "shuffle_into_deck":
        return float(min(len(opponent.bench), int(amount)))
    if value == "special_condition_immunity":
        return float(sum(bool(getattr(side, status)) for status in
                         ("asleep", "paralyzed", "confused", "poisoned", "burned")))
    raise KeyError(f"unpriced clause effect {value!r}")


def _clause_effect_polarity(clause):
    if clause.effect == "hp_delta":
        return 1.0 if _quantity(clause.amount) > 0 else -1.0
    if clause.effect in {"attack_fails_on_tails", "damage_counters"}:
        return -1.0
    if clause.kind == "ability_suppression":
        return -1.0
    return 1.0


def _symmetric_units(clause, facts, side, opponent, board, ctx):
    if clause.effect is not None:
        return -_effect_units(
            clause.effect, clause, facts, opponent, side, board, ctx,
            opponent.active)
    if clause.kind == "ability_suppression":
        return _applies_to_units(clause.applies_to, clause, opponent, ctx)
    if clause.kind == "deck_top":
        return -_amount_capacity(clause, opponent.hand_count)
    if clause.kind in {"checkup_trigger", "stadium_static", "stadium_trigger"}:
        return 0.0
    raise KeyError(f"unpriced symmetric clause {clause.kind!r}")


def _restriction_units(value, facts, side, opponent, board, ctx):
    value = str(value)
    candidates = tuple(side.bodies)
    predicates = {
        "active_dragon_only": lambda candidate: getattr(
            candidate, "energy_type", None) == DRAGON,
        "active_non_arvens_pokemon": lambda candidate: "arven" not in getattr(
            candidate, "name", "").casefold(),
        "arvens_pokemon": lambda candidate: "arven" in getattr(
            candidate, "name", "").casefold(),
        "mega_only": lambda candidate: "mega" in getattr(
            candidate, "name", "").casefold(),
        "psychic_only": lambda candidate: getattr(
            candidate, "energy_type", None) == PSYCHIC,
    }
    if value in {"active_dragon_only", "active_non_arvens_pokemon"}:
        active_facts = None if side.active is None else ctx.facts(side.active.card.card_id)
        return -float(max(1, int(active_facts is None
                                 or not predicates[value](active_facts))))
    if value in predicates:
        return -float(max(1, sum(
            not predicates[value](ctx.facts(target.card.card_id))
            for target in candidates)))
    if value in {"active_only", "self"}:
        return -float(max(1, len(candidates) - 1))
    if value == "evolves_from_self":
        rows = _zone_fact_counts("deck", side, board, ctx)
        return -float(max(1, sum(
            count for candidate, count in rows
            if isinstance(candidate, PokemonCard)
            and candidate.evolves_from != getattr(facts, "name", None))))
    if value == "ex_or_v_only":
        return -float(max(1, sum(
            not getattr(ctx.facts(target.card.card_id), "is_rule_box", False)
            for target in opponent.bench)))
    raise KeyError(f"unpriced clause restriction {value!r}")


def _restriction_satisfied(value, facts, side, opponent, board, ctx):
    if value is None:
        return True
    value = str(value)
    active = side.active
    active_facts = None if active is None else ctx.facts(active.card.card_id)
    gates = {
        "active_dragon_only": bool(active_facts and active_facts.energy_type == DRAGON),
        "active_non_arvens_pokemon": bool(
            active_facts and "arven" not in active_facts.name.casefold()),
        "active_only": active is not None,
        "arvens_pokemon": bool(
            active_facts and "arven" in active_facts.name.casefold()),
        "evolves_from_self": any(
            getattr(ctx.facts(card_id), "evolves_from", None)
            == getattr(facts, "name", None)
            for card_id, _count in (board.deck_counts or ())),
        "ex_or_v_only": any(
            getattr(ctx.facts(target.card.card_id), "is_rule_box", False)
            for target in opponent.bench),
        "mega_only": any(
            "mega" in getattr(ctx.facts(target.card.card_id), "name", "").casefold()
            for target in side.bodies),
        "psychic_only": any(
            getattr(ctx.facts(target.card.card_id), "energy_type", None) == PSYCHIC
            for target in side.bodies),
        "self": active is not None,
    }
    try:
        return gates[value]
    except KeyError:
        raise KeyError(f"unpriced clause restriction {value!r}") from None


def _restriction_targets(value, facts, side, ctx, *, body=None):
    if value is None:
        return tuple(side.bodies)
    value = str(value)
    if value == "self":
        target = body or side.active
        return () if target is None else (target,)
    if value in {"active_dragon_only", "active_non_arvens_pokemon",
                 "active_only", "arvens_pokemon"}:
        return () if side.active is None else (side.active,)
    predicates = {
        "mega_only": lambda candidate: "mega" in candidate.name.casefold(),
        "psychic_only": lambda candidate: candidate.energy_type == PSYCHIC,
    }
    if value in predicates:
        return tuple(
            target for target in side.bodies
            if predicates[value](ctx.facts(target.card.card_id)))
    return tuple(side.bodies)


def _heal_targets(clause, facts, side, board, ctx, *, body=None):
    targets = _restriction_targets(
        clause.restriction, facts, side, ctx, body=body)
    if clause.condition == "remaining_hp_30_or_less":
        targets = tuple(
            target for target in targets
            if 0 < target.hp <= LOW_REMAINING_HP_THRESHOLD)
    elif clause.condition == "energy_3_plus":
        targets = tuple(
            target for target in targets
            if len(target.energies) >= ENERGY_COUNT_THRESHOLD)
    if clause.rider == "discard_own_energy":
        required = max(1, int(clause.rider_amount or 1))
        targets = tuple(
            target for target in targets if len(target.energies) >= required)
    return tuple(target for target in targets if target.hp < target.max_hp)


def _healed_hp(clause, target):
    damage = max(0, target.max_hp - target.hp)
    return damage if clause.amount == "all" else min(damage, _quantity(clause.amount))


def _heal_rider_cost(clause, target):
    if clause.rider == "bounce_energy_to_hand":
        return BOUNCE_ENERGY_HAND_UNIT * len(target.energies)
    if clause.rider == "discard_own_energy":
        return float(min(len(target.energies), max(1, int(clause.rider_amount or 1))))
    return 0.0


def _heal_selection(clause, facts, side, board, ctx, *, body=None):
    targets = _heal_targets(clause, facts, side, board, ctx, body=body)
    if clause.each_of:
        healed = sum(_healed_hp(clause, target) for target in targets)
        rider_cost = sum(_heal_rider_cost(clause, target) for target in targets)
        return None, healed, rider_cost
    def net_value(selection):
        _target, healed, rider_cost = selection
        return healed / DAMAGE_UNIT_HP - rider_cost
    return max((
        (target, _healed_hp(clause, target), _heal_rider_cost(clause, target))
        for target in targets),
        key=net_value,
        default=(None, 0.0, 0.0))


def _rider_feasible(clause, facts, side, board, ctx, *, body=None):
    if clause.rider == "discard_basic_f_energy":
        return (_basic_energy_in_hand(
                    side, ctx, clause.rider_energy_type or FIGHTING)
                >= max(1, int(clause.rider_amount or 1)))
    if clause.kind == "heal" and clause.rider == "discard_own_energy":
        required = max(1, int(clause.rider_amount or 1))
        return any(len(target.energies) >= required for target in _heal_targets(
            clause, facts, side, board, ctx, body=body))
    return True


def _clause_gate(clause, body, facts, side, opponent, board, ctx):
    condition = _condition_probability(
        clause.condition, body, side, board, ctx, clause=clause)
    if condition is None:
        return None
    return (float(condition)
            * float(_restriction_satisfied(
                clause.restriction, facts, side, opponent, board, ctx))
            * float(_rider_feasible(
                clause, facts, side, board, ctx, body=body)))


def _rider_units(value, clause, facts, side, opponent, board, ctx, *, body=None):
    value = str(value)
    if clause.kind == "heal" and value in {
            "bounce_energy_to_hand", "discard_own_energy"}:
        _target, _healed, cost = _heal_selection(
            clause, facts, side, board, ctx, body=body)
        opportunity = (cost / BOUNCE_ENERGY_HAND_UNIT
                       if value == "bounce_energy_to_hand" else cost)
        return opportunity * CLAUSE_PARAMETER_VALUE_UNITS["rider"][value]
    opportunities = {
        "attached_cards_too": sum(len(body.tools) + len(body.energy_cards)
                                   for body in opponent.bodies),
        "both_hands_to_bottom": side.hand_count + opponent.hand_count,
        "bounce_energy_to_hand": sum(len(body.energies) for body in side.bodies),
        "confuse_target": int(opponent.active is not None and not opponent.confused),
        "cure_existing": sum(bool(getattr(side, status)) for status in
                             ("asleep", "paralyzed", "confused", "poisoned", "burned")),
        "damage_new_active": int(bool(opponent.bench)),
        "discard_basic_f_energy": _basic_energy_in_hand(
            side, ctx, FIGHTING),
        "discard_eot": sum(len(body.energies) for body in side.bodies),
        "discard_own_energy": sum(len(body.energies) for body in side.bodies),
        "discard_remainder": side.deck_count,
        "draw_1": side.deck_count,
        "heal_30_target": sum(max(0, body.max_hp - body.hp) for body in side.bodies)
                          / DAMAGE_UNIT_HP,
        "other_to_bottom": side.hand_count,
        "poison_new_active": int(bool(side.bench)),
        "recoil": int(bool(side.active)),
        "self_ko": int(bool(side.active)),
        "self_switch": int(bool(side.bench)),
        "shuffle_before_place": side.deck_count,
        "shuffle_both_hands": side.hand_count + opponent.hand_count,
        "shuffle_counted_into_deck": side.deck_count,
        "shuffle_own_hand_in": side.hand_count,
        "shuffle_self_in": int(bool(side.active)),
        "skip_stage1": int(bool(side.bench)),
    }
    try:
        return float(opportunities[value]) * CLAUSE_PARAMETER_VALUE_UNITS["rider"][value]
    except KeyError:
        raise KeyError(f"unpriced clause rider {value!r}") from None


def clause_parameter_units(parameter, value, clause, facts, side, opponent,
                           board, ctx, *, body=None) -> float:
    parameter = str(parameter)
    if value is None:
        return 0.0
    if parameter == "allowance":
        return float(len(side.bodies) if value == "body" else side.hand_count)
    if parameter == "applies_to":
        return (_clause_effect_polarity(clause)
                * _applies_to_units(value, clause, side, ctx))
    if parameter == "attack":
        return -float(any(attack.name == value for attack in getattr(facts, "attacks", ())))
    if parameter == "choice":
        return float(bool(value)) * _target_units(
            clause.target or "any", clause, facts, side, opponent, board, ctx, body)
    if parameter == "chooser":
        return -float(len(opponent.bodies))
    if parameter == "cost":
        return -clause_cost_units(clause, side)
    if parameter == "cost_required":
        return -float(bool(value))
    if parameter == "cost_units":
        return -float(len(value))
    if parameter == "dest":
        capacity = {
            "bench": side.bench_max - len(side.bench), "new_benched": side.bench_max - len(side.bench),
            "in_play": len(side.bodies), "hand": side.hand_count,
            "deck_top": side.deck_count, "opp_any": len(opponent.bodies),
        }
        return (CLAUSE_PARAMETER_VALUE_UNITS["dest"][str(value)]
                * _amount_capacity(clause, capacity[str(value)]))
    if parameter == "dig":
        return _quantity(value) / max(1, side.deck_count)
    if parameter == "dig_from":
        return CLAUSE_PARAMETER_VALUE_UNITS["dig_from"][str(value)] * side.deck_count
    if parameter == "distinct_types":
        source = clause.zone or clause.source or "deck"
        rows = _zone_fact_counts(source, side, board, ctx)
        types = {
            candidate.provides for candidate, _count in rows
            if isinstance(candidate, EnergyCard) and candidate.kind == BASIC_ENERGY
        }
        required = (_quantity(clause.amount, 1) + _quantity(clause.to_hand)
                    if clause.kind == "accel" else _quantity(clause.amount, 1))
        return float(min(len(types), required) if clause.amount != "all" else len(types))
    if parameter == "duration":
        return CLAUSE_PARAMETER_VALUE_UNITS["duration"][str(value)] * float(
            opponent.active is not None)
    if parameter == "each_of":
        return _clause_effect_polarity(clause) * float(bool(value)) * _target_units(
            clause.target or "any", clause, facts, side, opponent, board, ctx, body)
    if parameter == "effect":
        return _effect_units(value, clause, facts, side, opponent, board, ctx, body)
    if parameter == "energy":
        return _energy_eligibility_units(
            value, clause, side, opponent, board, ctx)
    if parameter in {"energy_type", "rider_energy_type"}:
        return _typed_eligibility_units(
            value, clause, side, opponent, board, ctx)
    if parameter == "evolves_into_type":
        return float(sum(
            getattr(candidate, "energy_type", None) == int(value)
            for candidate in _facts_on_side(side, ctx)))
    if parameter == "target_type":
        return _target_type_units(
            value, clause, side, opponent, board, ctx, body)
    if parameter == "exclude_name":
        excluded = sum(
            count for candidate, count in _clause_candidate_rows(
                clause, side, opponent, board, ctx, body)
            if getattr(candidate, "name", None) == value)
        harmful = clause.kind == "checkup_trigger" \
            and clause.effect == "damage_counters"
        return float(excluded if harmful else -excluded)
    if parameter == "granted_action":
        return float(bool(value)) * len(board.legal_actions)
    if parameter == "hp_max":
        rows = (_zone_fact_counts(clause.zone, side, board, ctx)
                if clause.zone in {"deck", "discard", "hand"} else
                tuple((candidate, 1) for candidate in _facts_on_side(side, ctx)))
        available = sum(
            count for candidate, count in rows
            if isinstance(candidate, PokemonCard) and candidate.hp <= int(value)
            and fetch_target_matches(clause, candidate, reading=DEADNESS))
        return _amount_capacity(clause, available)
    if parameter == "includes_effects":
        return float(bool(value) and opponent.active is not None)
    if parameter == "name":
        return _named_units(value, side, board, ctx)
    if parameter == "name_family":
        return _named_units(value, side, board, ctx, family=True)
    if parameter == "named":
        return _named_units(value, side, board, ctx)
    if parameter == "new_weakness":
        return float(opponent.active is not None and int(value) >= 0)
    if parameter == "no_ability":
        available = sum(
            count for candidate, count in _clause_candidate_rows(
                clause, side, opponent, board, ctx, body)
            if isinstance(candidate, PokemonCard) and not candidate.abilities)
        return (_amount_capacity(clause, available)
                if clause.kind == "fetch" else float(available))
    if parameter == "no_rule_box":
        available = sum(
            count for candidate, count in _clause_candidate_rows(
                clause, side, opponent, board, ctx, body)
            if isinstance(candidate, PokemonCard) and not candidate.is_rule_box)
        return (_amount_capacity(clause, available)
                if clause.kind == "fetch" else float(available))
    if parameter == "no_stack":
        return -float(sum(other.card.card_id == getattr(facts, "card_id", None)
                          for other in side.bodies))
    if parameter == "on":
        return (_clause_effect_polarity(clause)
                * float(side.bench_max - len(side.bench)))
    if parameter == "optional":
        return float(bool(value)) / (1.0 + clause_cost_units(clause, side)
                                     + clause_rider_cost_units(clause, side))
    if parameter == "random":
        return -COIN_HEADS_PROBABILITY * float(bool(value)) * opponent.hand_count
    if parameter == "restriction":
        return _restriction_units(value, facts, side, opponent, board, ctx)
    if parameter == "rider":
        return _rider_units(
            value, clause, facts, side, opponent, board, ctx, body=body)
    if parameter == "rider_amount":
        if clause.rider is None:
            return 0.0
        rider = CLAUSE_PARAMETER_VALUE_UNITS["rider"][str(clause.rider)]
        return ((1.0 if rider > 0 else -1.0)
                * _quantity(value) / DAMAGE_UNIT_HP)
    if parameter == "scope":
        return float(opponent.active is not None) \
            * CLAUSE_PARAMETER_VALUE_UNITS["scope"][str(value)]
    if parameter == "source":
        source = str(value)
        availability = (_zone_units(
                            source, side, opponent, board, ctx, clause=clause)
                        if source in {"deck", "discard", "hand"}
                        else len(side.bench) if source == "own_bench"
                        else len(side.discard) if source == "milled_pokemon"
                        else int(opponent.active is not None))
        return CLAUSE_PARAMETER_VALUE_UNITS["source"][source] * availability
    if parameter == "source_class":
        source_class = str(value)
        matches = {
            "basic": lambda candidate: getattr(candidate, "evolves_from", None) is None,
            "ex": lambda candidate: getattr(candidate, "is_rule_box", False),
            "ex_or_v": lambda candidate: getattr(candidate, "is_rule_box", False),
            "has_ability": lambda candidate: bool(getattr(candidate, "abilities", ())),
        }
        return float(sum(matches[source_class](candidate)
                         for candidate in _facts_on_side(opponent, ctx)))
    if parameter == "symmetric":
        return float(bool(value)) * _symmetric_units(
            clause, facts, side, opponent, board, ctx)
    if parameter == "target":
        target = str(value)
        harmful = (clause.kind, target) in {
            ("bench_spread", "own_bench"),
            ("confuse", "self"),
            ("energy_bounce", "self"),
            ("ko", "both_actives"),
            ("mill", "self"),
        }
        return ((-1.0 if harmful else 1.0)
                * CLAUSE_PARAMETER_VALUE_UNITS["target"][target]
                * _target_units(
                    target, clause, facts, side, opponent, board, ctx, body))
    if parameter == "target_class":
        if str(value) != "ex":
            raise KeyError(f"unpriced clause target class {value!r}")
        return float(sum(getattr(candidate, "is_rule_box", False)
                         for candidate in _facts_on_side(opponent, ctx)))
    if parameter == "target_condition":
        return float(sum(not target.appeared_this_turn for target in side.bodies))
    if parameter == "timing":
        return CLAUSE_PARAMETER_VALUE_UNITS["timing"][str(value)] * float(
            opponent.active is not None)
    if parameter == "trigger":
        trigger = str(value)
        gates = {
            "on_attach": sum(len(target.energies) for target in side.bodies),
            "on_bench_play": side.bench_max - len(side.bench),
            "on_evolve": sum(bool(target.pre_evolution) for target in side.bodies),
            "on_fetch_success": side.deck_count,
            "setup": int(board.turn.number <= 1),
        }
        return CLAUSE_PARAMETER_VALUE_UNITS["trigger"][trigger] * gates[trigger]
    if parameter == "type":
        provided = {
            "colorless": COLORLESS, "fighting": FIGHTING, "psychic": PSYCHIC,
        }[str(value)]
        if getattr(facts, "provides", None) != provided:
            return 0.0
        return float(any(
            payment_fraction((provided,), attack.cost) > 0.0
            for candidate in _facts_on_side(side, ctx)
            for attack in getattr(candidate, "attacks", ())))
    if parameter == "window":
        return FUTURE_TURN_DISCOUNT ** _quantity(value) * side.deck_count
    if parameter == "zone":
        zone = str(value)
        return CLAUSE_PARAMETER_VALUE_UNITS["zone"][zone] * _zone_units(
            zone, side, opponent, board, ctx, clause=clause)
    raise KeyError(f"unpriced clause parameter {parameter!r}")


def _clause_amount(clause, body, side) -> float:
    amount = getattr(clause, "amount", None)
    if amount not in {"all", "any"}:
        return abs(_quantity(amount, 1))
    if clause.kind == "fetch":
        return float(max(1, side.deck_count))
    if clause.kind in {"cost_reduction", "retreat_reduction"}:
        return float(max(1, 0 if body is None else len(body.energies)))
    if clause.kind == "self_discard_energy":
        return float(sum(len(target.energies) for target in side.bodies))
    if clause.kind == "move_damage":
        return float(sum(max(0, target.max_hp - target.hp) for target in side.bodies))
    raise KeyError(f"unpriced symbolic amount {amount!r} for {clause.kind!r}")


def clause_value_units(clause, facts, side, opponent, board, ctx, *, body=None) -> float:
    gate = _clause_gate(clause, body, facts, side, opponent, board, ctx)
    if gate is None:
        return 0.0
    if clause.kind == "heal":
        _target, healed, _rider_cost = _heal_selection(
            clause, facts, side, board, ctx, body=body)
        amount = healed / DAMAGE_UNIT_HP
    else:
        amount = _clause_amount(clause, body, side)
    if clause.kind == "draw":
        own_draw, _opponent_draw = expected_draw_counts(
            clause, side, opponent, ctx,
            cards_leaving_hand=int(isinstance(facts, TrainerCard)))
        amount = own_draw
    elif clause.kind == "damage_counters":
        amount *= DAMAGE_COUNTER_HP / DAMAGE_UNIT_HP
    elif clause.kind in _DAMAGE_CLAUSES and clause.kind != "heal":
        amount /= DAMAGE_UNIT_HP
    elif clause.kind == "coin":
        flips = (1.0 if clause.count == "until_tails" else _quantity(clause.count, 1))
        unit = (amount / DAMAGE_UNIT_HP if clause.effect == "damage_boost"
                else amount)
        amount = unit * flips * COIN_HEADS_PROBABILITY
    amount *= _per_units(clause, body, side, opponent, board, ctx)
    value = float(gate) * amount
    return max(0.0, value)


def _damage_boost(clause, body, attacker, defender, ctx, board) -> float:
    facts = ctx.facts(body.card.card_id)
    gate = _clause_gate(
        clause, body, facts, attacker, defender, board, ctx)
    if gate is None:
        gate = 0.0
    units = _per_units(clause, body, attacker, defender, board, ctx)
    return gate * _quantity(clause.amount) * units


def _knockout_visible(board) -> bool:
    for event in board.events:
        fields = dict(event.public_fields)
        if event.recognized and event.kind in KNOCKOUT_EVENT_KINDS \
                and fields.get("fromArea") in IN_PLAY_AREAS \
                and fields.get("toArea") == DISCARD_AREA:
            return True
    return False


def _scale_value(name, attacker, defender, attacker_body, defender_body, ctx) -> int | None:
    values = {
        "atk_hand": attacker.hand_count,
        "def_hand": defender.hand_count,
        "atk_active_energy": len(attacker_body.energies),
        "def_active_energy": 0 if defender_body is None else len(defender_body.energies),
        "atk_bench": len(attacker.bench),
        "def_bench": len(defender.bench),
        "both_bench": len(attacker.bench) + len(defender.bench),
        "both_active_energy": (len(attacker_body.energies)
                               + (0 if defender_body is None else len(defender_body.energies))),
        "atk_self_counters": max(
            0, attacker_body.max_hp - attacker_body.hp) // DAMAGE_COUNTER_HP,
        "def_counters": (0 if defender_body is None else
                         max(0, defender_body.max_hp - defender_body.hp)
                         // DAMAGE_COUNTER_HP),
        "atk_prizes_taken": max(0, DEFAULT_PRIZE_COUNT - attacker.prize_count),
        "def_prizes_taken": max(0, DEFAULT_PRIZE_COUNT - defender.prize_count),
        "atk_bench_stage2": sum(
            getattr(ctx.facts(body.card.card_id), "stage", None) == "stage2"
            for body in attacker.bench),
        "def_counters_all": sum(max(0, body.max_hp - body.hp) // DAMAGE_COUNTER_HP
                                for body in defender.bodies),
        "def_ex_in_play": sum(bool(getattr(ctx.facts(body.card.card_id), "ex", False)
                                   or getattr(ctx.facts(body.card.card_id), "mega_ex", False))
                              for body in defender.bodies),
    }
    return values.get(str(name))


def attack_damage(attack, attacker_facts, defender_facts, attacker_body,
                  attacker, defender, ctx, board=None) -> float:
    partner = attack.clause("requires_bench")
    if partner is not None and partner.name not in _side_names(attacker, ctx, bench_only=True):
        return 0.0
    bench_gate = attack.clause("requires_bench_count")
    if bench_gate is not None and len(attacker.bench) < int(bench_gate.amount or 0):
        return 0.0
    if attack.clause("requires_stadium") is not None and not getattr(board, "stadium", ()):
        return 0.0
    damage = float(attack.damage_fix if attack.damage_fix is not None else attack.damage or 0)
    copy = attack.clause("copy_attack")
    if copy is not None:
        family = str(copy.name_family or "").casefold()
        damage = max((
            float(candidate.damage or candidate.damage_fix or candidate.damage_max or 0)
            for other in attacker.bench
            for source in (ctx.facts(other.card.card_id),)
            if isinstance(source, PokemonCard)
            and (not family or family in source.name.casefold())
            for candidate in source.attacks), default=damage)
    if not damage and attack.damage_min is not None and attack.damage_max is not None:
        damage = (float(attack.damage_min) + float(attack.damage_max)) \
            / DAMAGE_RANGE_BOUND_COUNT
    if attack.scale_var and attack.scale_per_unit:
        units = _scale_value(attack.scale_var, attacker, defender, attacker_body,
                             defender.active, ctx)
        if units is not None:
            damage += float(attack.scale_per_unit) * units
    for clause in attack.clauses:
        if clause.kind == "damage_boost":
            damage += _damage_boost(clause, attacker_body, attacker, defender, ctx, board)
        elif clause.kind == "coin":
            probability = COIN_HEADS_PROBABILITY
            if clause.effect == "attack_fails_on_tails":
                damage *= probability
            elif clause.effect == "damage_boost":
                flips = (1.0 if clause.count == "until_tails"
                         else _quantity(clause.count, 1) * probability)
                damage += _quantity(clause.amount) * flips
    twice = attack.clause("attack_twice")
    if twice is not None:
        gate = _condition_probability(
            twice.condition, attacker_body, attacker, board, ctx, clause=twice)
        damage *= 1.0 + max(0.0, float(gate or 0.0))
    if attack.clause("ko") is not None and defender.active is not None:
        damage = max(damage, float(defender.active.hp))
    if not damage or attack.clause("ignores_wr") is not None or defender_facts is None:
        return max(0.0, damage)
    attacker_type = getattr(attacker_facts, "energy_type", None)
    if getattr(defender_facts, "weakness", None) == attacker_type:
        damage *= WEAKNESS_MULTIPLIER
    if getattr(defender_facts, "resistance", None) == attacker_type:
        damage = max(0.0, damage - RESISTANCE_REDUCTION)
    if attack.clause("ignores_effects") is None:
        for clause in card_clauses(defender_facts):
            if clause.kind == "damage_reduction" and clause.amount:
                damage = max(0.0, damage - float(clause.amount))
            if clause.kind == "prevent_damage" and clause.condition in {None, "always"}:
                return 0.0
    return max(0.0, damage)


def _target_impact(damage: float, target, ctx) -> float:
    if target is None or damage <= 0:
        return max(0.0, damage) / DAMAGE_UNIT_HP
    live_hp = max(1, target.hp)
    progress = min(damage, live_hp) / DAMAGE_UNIT_HP
    if damage >= live_hp:
        progress += float(getattr(ctx.facts(target.card.card_id), "prize_value", 1))
    return progress


def self_ko_liability_units(body, side, opponent, ctx):
    if body is None:
        return 0.0
    prize_value = float(getattr(ctx.facts(body.card.card_id), "prize_value", 1) or 1)
    material = (body.hp / DAMAGE_UNIT_HP + prize_value
                + ATTACHED_ENERGY_MATERIAL_UNIT * len(body.energies))
    terminal = TERMINAL_LOSS_UNITS if opponent.prize_count <= prize_value else 0.0
    return material + terminal


def _attack_impact(attack, facts, body, side, opponent, ctx, board) -> tuple[float, float]:
    defender_facts = (None if opponent.active is None else
                      ctx.facts(opponent.active.card.card_id))
    active = _target_impact(
        attack_damage(attack, facts, defender_facts, body, side, opponent, ctx, board),
        opponent.active, ctx)
    reach = float(bench_reach(attack))
    any_target = attack.clause("bench_snipe")
    bench_targets = tuple(opponent.bench)
    if any_target is not None and any_target.restriction == "ex_or_v_only":
        bench_targets = tuple(
            target for target in bench_targets
            if getattr(ctx.facts(target.card.card_id), "is_rule_box", False))
    bench = max((_target_impact(reach, target, ctx) for target in bench_targets),
                default=0.0)
    if any_target is not None and any_target.target == "opp_any":
        count = max(1, int(any_target.count or 1))
        targets = ((opponent.active, False), *((target, True) for target in bench_targets))
        chosen = sorted(((_target_impact(reach, target, ctx), is_bench)
                         for target, is_bench in targets if target is not None), reverse=True)
        selected = chosen[:count]
        total = sum(value for value, _is_bench in selected)
        selected_bench = sum(value for value, is_bench in selected if is_bench)
        return max(active, total), selected_bench
    return active + bench, bench


def _ability_capability(body, facts, side, opponent, board, ctx) -> Capability:
    values = {name: 0.0 for name in (
        "draw_cards", "search_cards", "damage_move", "healing", "acceleration",
        "denial", "resource_cost", "self_cost", "ability_future")}
    gaps = []
    for ability in facts.abilities:
        for clause in ability.clauses:
            gate = _clause_gate(
                clause, body, facts, side, opponent, board, ctx)
            if gate is None:
                gaps.append(f"unsupported condition {clause.condition!r} on {facts.card_id}")
                continue
            if gate <= 0:
                continue
            values["resource_cost"] += gate * (
                clause_cost_units(clause, side)
                + (0.0 if clause.kind == "heal"
                   else clause_rider_cost_units(clause, side)))
            if clause.rider == "draw_1":
                values["draw_cards"] += gate
            elif clause.rider == "heal_30_target":
                damaged = sum(max(0, other.max_hp - other.hp) for other in side.bodies)
                values["healing"] += gate * min(HEAL_TARGET_HP, damaged) / DAMAGE_UNIT_HP
            if clause.kind == "draw":
                mine, theirs = expected_draw_counts(clause, side, opponent, ctx)
                values["draw_cards"] += gate * mine
                values["resource_cost"] += gate * theirs
            elif clause.kind == "fetch" and clause.trigger != "on_bench_play":
                values["search_cards"] += gate * _quantity(clause.amount, 1)
            elif clause.kind == "move_damage":
                amount = _quantity(clause.amount)
                movable = min(amount,
                              sum(max(0, other.max_hp - other.hp) for other in side.bodies))
                room = max((target.hp for target in opponent.bodies), default=0)
                immediate = min(movable, room) / DAMAGE_UNIT_HP
                potential = min(amount, room) / DAMAGE_UNIT_HP
                values["damage_move"] += gate * immediate
                values["ability_future"] += gate * max(0.0, potential - immediate)
            elif clause.kind == "heal":
                _target, healed, rider_cost = _heal_selection(
                    clause, facts, side, board, ctx, body=body)
                values["healing"] += gate * healed / DAMAGE_UNIT_HP
                values["resource_cost"] += gate * rider_cost
            elif clause.kind in {"accel", "energy_recur", "move_energy"}:
                available = len(side.discard) if clause.zone == "discard" else 1
                values["acceleration"] += gate * min(_quantity(clause.amount, 1), available)
            elif clause.kind in {"ability_suppression", "attack_lock", "item_lock",
                                 "no_retreat", "retreat_lock"}:
                values["denial"] += gate
    for clause in card_clauses(facts):
        if clause.kind == "checkup_trigger":
            amount = _quantity(clause.amount) * DAMAGE_COUNTER_HP / DAMAGE_UNIT_HP
            opposing = sum(1 for target in opponent.bodies
                            if getattr(ctx.facts(target.card.card_id), "abilities", ()))
            friendly = sum(1 for target in side.bodies if target is not body
                           and getattr(ctx.facts(target.card.card_id), "abilities", ()))
            values["damage_move"] += amount * opposing
            values["self_cost"] += amount * friendly
        elif clause.kind == "grant_prevo_attacks":
            values["ability_future"] += max((
                float(attack.damage or attack.damage_fix or attack.damage_max or 0)
                / DAMAGE_UNIT_HP
                for target in side.bodies for card in target.pre_evolution
                for previous in (ctx.facts(card.card_id),)
                if isinstance(previous, PokemonCard) for attack in previous.attacks), default=0.0)
        elif clause.kind == "setup_active" and board.turn.number <= 0:
            values["ability_future"] += 1.0
        elif clause.kind == "no_weakness" and facts.weakness is not None:
            values["denial"] += max(0.0, best_current_damage(
                opponent.active, opponent, side, board, ctx) / DAMAGE_UNIT_HP
                if opponent.active is not None else 0.0)
        elif clause.kind == "survive_ko" and body.hp >= body.max_hp:
            gate = _clause_gate(
                clause, body, facts, side, opponent, board, ctx)
            values["denial"] += max(0.0, float(gate or 0.0)) * max(
                0.0, _quantity(clause.remaining_hp, 1) / DAMAGE_UNIT_HP)
    return Capability(**values, gaps=tuple(gaps))


def _reachable_evolutions(facts, ctx, reach):
    from .worth import Reach, _forward_lines

    for card_id in _forward_lines().get(facts.name, ()):
        status = (reach or {}).get(card_id, Reach.ABSENT)
        scale = (1.0 if status in {Reach.HAND, Reach.FETCHABLE} else
                 1.0 if status is Reach.NEXT_TURN else
                 max(0.0, min(1.0, float(status))) if isinstance(status, (int, float)) else 0.0)
        target = ctx.facts(card_id)
        if scale > 0 and isinstance(target, PokemonCard):
            yield target, scale


def body_capability(body, side, opponent, board, ctx, *, reach=None) -> Capability:
    if body.max_hp > 0 and body.hp <= 0:
        return Capability()
    body = _without_bench_rentals(body, side, ctx)
    facts = ctx.facts(body.card.card_id)
    if not isinstance(facts, PokemonCard):
        return Capability(gaps=(f"body {body.card.card_id} has no Pokemon facts",))
    immediate = progress = bench = potential = chosen_attack_cost = 0.0
    immediate_net = float("-inf")
    for attack in facts.attacks:
        impact, attack_bench = _attack_impact(
            attack, facts, body, side, opponent, ctx, board)
        resource_cost = sum(
                            clause_cost_units(clause, side)
                            + clause_rider_cost_units(clause, side)
                            for clause in attack.clauses)
        if any(clause.kind == "ko" and clause.target == "both_actives"
               for clause in attack.clauses):
            resource_cost += self_ko_liability_units(
                body, side, opponent, ctx)
        if resource_cost and any(clause.optional and clause.cost
                                 for clause in attack.clauses):
            without_optional = impact - attack_bench
            if impact - resource_cost <= without_optional:
                impact, attack_bench, resource_cost = without_optional, 0.0, 0.0
        printed = max(float(attack.damage or attack.damage_fix or attack.damage_max or 0),
                      float(bench_reach(attack))) / DAMAGE_UNIT_HP
        potential = max(potential, max(impact, printed) / max(1, len(attack.cost)))
        fraction = payment_fraction(body.energies, attack.cost)
        permission = attack.clause("first_turn_attack_permission")
        permission_gate = (0.0 if permission is None else
                           float(_condition_probability(
                               permission.condition, body, side, board, ctx,
                               clause=permission) or 0.0))
        first_turn_blocked = (
            side is board.me and board.turn.number <= 1
            and board.turn.first_player == board.seat
            and permission_gate <= 0.0)
        if fraction >= 1.0 and not first_turn_blocked:
            net = impact - resource_cost
            if net > immediate_net:
                immediate_net = net
                immediate, bench, chosen_attack_cost = impact, attack_bench, resource_cost
        else:
            progress = max(progress, impact * fraction ** COMPLETION_EXPONENT)
    future = 0.0
    for evolved, scale in _reachable_evolutions(facts, ctx, reach):
        for attack in evolved.attacks:
            impact, _attack_bench = _attack_impact(
                attack, evolved, body, side, opponent, ctx, board)
            fraction = payment_fraction(body.energies, attack.cost)
            future = max(future, scale * impact * fraction ** COMPLETION_EXPONENT)
    from .worth import _forward_lines

    line = (facts, *(ctx.facts(card_id)
                     for card_id in _forward_lines().get(facts.name, ())))
    line_potential = max((
        (float(attack.damage or attack.damage_fix or attack.damage_max or 0)
         + float(bench_reach(attack))) / DAMAGE_UNIT_HP / max(1, len(attack.cost))
        for card in line if isinstance(card, PokemonCard) for attack in card.attacks),
        default=potential)
    ability = _ability_capability(body, facts, side, opponent, board, ctx)
    twice_gate = max((
        _condition_probability(clause.condition, body, side, board, ctx, clause=clause) or 0.0
        for clause in card_clauses(facts) if clause.kind == "attack_twice"), default=0.0)
    if twice_gate:
        immediate *= 1.0 + twice_gate
        progress *= 1.0 + twice_gate
        future *= 1.0 + twice_gate
        potential *= 1.0 + twice_gate
    first_turn_search = max((
        float(_condition_probability(
            permission.condition, body, side, board, ctx,
            clause=permission) or 0.0) * _quantity(clause.amount, 1)
        for attack in facts.attacks
        for permission in (attack.clause("first_turn_attack_permission"),)
        if permission is not None
        and payment_fraction(body.energies, attack.cost) >= 1.0
        for clause in attack.clauses if clause.kind == "fetch"), default=0.0)
    future_protection = max((
        body.max_hp / DAMAGE_UNIT_HP
        for attack in facts.attacks
        if attack.clause("no_weakness") is not None
        and payment_fraction(body.energies, attack.cost) >= 1.0), default=0.0)
    attack_lock_cost = max((
        1.0 for attack in facts.attacks
        if attack.clause("same_attack_lock") is not None
        and payment_fraction(body.energies, attack.cost) >= 1.0), default=0.0)
    weakness_override = max((
        1.0 for clause in card_clauses(facts)
        if clause.kind == "weakness_override" and opponent.active is not None), default=0.0)
    retreat = ((1.0 if facts.retreat_cost <= 0 else
                min(1.0, len(body.energies) / facts.retreat_cost))
               if body is side.active and side.bench else 0.0)
    result = replace(ability, attack_now=immediate, attack_progress=progress,
                   attack_future=future, attack_potential=potential,
                   line_potential=line_potential, bench_reach=bench,
                   resource_cost=(ability.resource_cost + attack_lock_cost
                                  + chosen_attack_cost),
                   search_cards=ability.search_cards + first_turn_search,
                   denial=ability.denial + weakness_override + future_protection,
                   retreat_progress=retreat)
    persistent_body = _without_end_turn_energy(body, ctx)
    if persistent_body is not body:
        persistent_side = replace(
            side,
            active=persistent_body if side.active is body else side.active,
            bench=tuple(persistent_body if item is body else item for item in side.bench),
        )
        persistent = body_capability(
            persistent_body, persistent_side, opponent, board, ctx, reach=reach)
        result = replace(
            result, attack_progress=persistent.attack_progress,
            attack_future=persistent.attack_future)
    return result


def _without_bench_rentals(body, side, ctx):
    if body is side.active:
        return body
    return _without_end_turn_energy(body, ctx)


def _without_end_turn_energy(body, ctx):
    if not body.energy_cards:
        return body
    provisions = list(body.energies)
    persistent_cards = []
    changed = False
    for card in body.energy_cards:
        facts = ctx.facts(card.card_id)
        if not any(clause.rider == "discard_eot" for clause in card_clauses(facts)):
            persistent_cards.append(card)
            continue
        supplied = getattr(facts, "provides", None)
        for _unit in range(provision_units(
                facts, evolved=bool(getattr(ctx.facts(body.card.card_id),
                                             "evolves_from", None)))):
            index = next((index for index, unit in enumerate(provisions)
                          if supplied is None or unit == supplied), None)
            if index is not None:
                provisions.pop(index)
                changed = True
    return (replace(body, energies=tuple(provisions), energy_cards=tuple(persistent_cards))
            if changed else body)


def best_current_damage(body, side, opponent, board, ctx) -> float:
    facts = ctx.facts(body.card.card_id)
    if not isinstance(facts, PokemonCard):
        return 0.0
    defender_facts = (None if opponent.active is None else
                      ctx.facts(opponent.active.card.card_id))
    return max((attack_damage(
        attack, facts, defender_facts, body, side, opponent, ctx, board)
        for attack in facts.attacks
        if payment_fraction(body.energies, attack.cost) >= 1.0), default=0.0)


def energy_marginal(body, energy_facts, side, opponent, board, ctx, *, reach=None) -> float:
    if not isinstance(energy_facts, EnergyCard):
        return 0.0
    if body is not side.active and any(
            clause.rider == "discard_eot" for clause in card_clauses(energy_facts)):
        return 0.0
    facts = ctx.facts(body.card.card_id)
    units = provision_units(energy_facts, evolved=bool(getattr(facts, "evolves_from", None)))
    supplied = int(energy_facts.provides)
    before = body_capability(body, side, opponent, board, ctx, reach=reach)
    after_body = replace(body, energies=(*body.energies, *((supplied,) * units)))
    after_side = replace(
        side,
        active=after_body if side.active is body else side.active,
        bench=tuple(after_body if item is body else item for item in side.bench),
    )
    after = body_capability(after_body, after_side, opponent, board, ctx, reach=reach)
    return after.option_units() - before.option_units()


def best_energy_marginal(energy_facts, side, opponent, board, ctx, reaches=None) -> float:
    reaches = reaches or {}
    return max((energy_marginal(
        body, energy_facts, side, opponent, board, ctx,
        reach=reaches.get(body.card.serial)) for body in side.bodies), default=0.0)


def recoverable_discard_ids(side, ctx) -> frozenset[int]:
    sources = tuple(side.hand or ()) + tuple(
        card for body in side.bodies for card in (body.card, *body.tools))
    discard = tuple(side.discard)
    recoverable = set()
    for source in sources:
        for clause in card_clauses(ctx.facts(source.card_id)):
            if clause.kind not in {"fetch", "energy_recur"} or clause.zone != "discard":
                continue
            for card in discard:
                facts = ctx.facts(card.card_id)
                if clause.kind == "energy_recur":
                    if isinstance(facts, EnergyCard) and (
                            clause.energy_type is None or facts.provides == clause.energy_type):
                        recoverable.add(card.card_id)
                elif fetch_target_matches(clause, facts, reading=DEADNESS):
                    recoverable.add(card.card_id)
    return frozenset(recoverable)


def card_option_units(facts, side, opponent, board, ctx, *, reaches=None,
                      _price_shuffle_loss=True) -> OptionUnits:
    if isinstance(facts, EnergyCard):
        hand = tuple(side.hand)
        copies = sum(
            isinstance(held, EnergyCard)
            and held.kind == facts.kind and held.provides == facts.provides
            for card in hand if (held := ctx.facts(card.card_id)) is not None)
        return OptionUnits(energy=max(0.0, best_energy_marginal(
            facts, side, opponent, board, ctx, reaches=reaches)) / max(1, copies))
    if isinstance(facts, PokemonCard):
        deployable = (facts.evolves_from is None and len(side.bench) < side.bench_max) \
            or any(getattr(ctx.facts(body.card.card_id), "name", None) == facts.evolves_from
                   for body in side.bodies)
        if not deployable:
            return OptionUnits()
        from .worth import _forward_lines

        line = (facts, *(ctx.facts(card_id)
                         for card_id in _forward_lines().get(facts.name, ())))
        line = tuple(card for card in line if isinstance(card, PokemonCard))
        attack = max(((float(item.damage or item.damage_fix or item.damage_max or 0)
                       + float(bench_reach(item)))
                      / DAMAGE_UNIT_HP / max(1, len(item.cost))
                      for card in line for item in card.attacks), default=0.0)
        clauses = tuple(clause for card in line for ability in card.abilities
                        for clause in ability.clauses)
        gate = lambda clause: (
            _prospective_condition(clause.condition, side, board, ctx)
            * float(_restriction_satisfied(
                clause.restriction, facts, side, opponent, board, ctx))
            * float(_rider_feasible(
                clause, facts, side, board, ctx)))

        def heal_units(clause):
            _target, healed, _rider_cost = _heal_selection(
                clause, facts, side, board, ctx)
            return gate(clause) * healed / DAMAGE_UNIT_HP

        def draw_units(clause):
            mine, theirs = expected_draw_counts(clause, side, opponent, ctx)
            return gate(clause) * mine, gate(clause) * theirs

        return OptionUnits(
            hp=facts.hp / DAMAGE_UNIT_HP,
            attack=attack,
            draw=max((draw_units(clause)[0]
                      for clause in clauses if clause.kind == "draw"), default=0.0),
            search=max((gate(clause) * _quantity(clause.amount, 1)
                        for clause in clauses if clause.kind == "fetch"), default=0.0),
            acceleration=max((gate(clause) * (
                _quantity(clause.amount, 1) + _quantity(clause.to_hand))
                for clause in clauses
                if clause.kind in {"accel", "energy_recur", "move_energy"}), default=0.0),
            denial=max((gate(clause) for clause in clauses if clause.kind in {
                "ability_suppression", "attack_lock", "item_lock", "no_retreat",
                "retreat_lock"}), default=0.0),
            healing=max((heal_units(clause)
                         for clause in clauses if clause.kind == "heal"), default=0.0),
            mobility=max((gate(clause) for clause in clauses
                          if clause.kind in {"self_switch", "switch_self"}), default=0.0),
            cost=(max((gate(clause) for clause in clauses
                      if clause.rider in {"shuffle_self_in", "self_shuffle_in"}), default=0.0)
                 + max((draw_units(clause)[1]
                        for clause in clauses if clause.kind == "draw"), default=0.0)),
        )
    if isinstance(facts, TrainerCard):
        availability = (FUTURE_TURN_DISCOUNT
                        if facts.kind == SUPPORTER and board.turn.supporter_played else 1.0)
        values = {name: 0.0 for name in OptionUnits.__dataclass_fields__}
        for clause in facts.clauses:
            gate = (_prospective_condition(clause.condition, side, board, ctx)
                    * float(_restriction_satisfied(
                        clause.restriction, facts, side, opponent, board, ctx))
                    * float(_rider_feasible(
                        clause, facts, side, board, ctx)))
            values["cost"] += gate * (
                clause_cost_units(clause, side)
                + (0.0 if clause.kind == "heal"
                   or (clause.kind == "draw"
                       and clause.rider == "shuffle_own_hand_in")
                   else clause_rider_cost_units(clause, side)))
            if clause.kind == "draw":
                mine, theirs = expected_draw_counts(
                    clause, side, opponent, ctx, cards_leaving_hand=1)
                target = mine
                values["cost"] += gate * theirs
                if clause.rider == "shuffle_own_hand_in":
                    target = max(0.0, target - max(0, side.hand_count - 1))
                values["draw"] += gate * target
                if clause.rider == "shuffle_own_hand_in" and _price_shuffle_loss:
                    skipped_played_copy = False
                    for card in tuple(side.hand):
                        held = ctx.facts(card.card_id)
                        if card.card_id == facts.card_id and not skipped_played_copy:
                            skipped_played_copy = True
                            continue
                        units = card_option_units(
                            held, side, opponent, board, ctx, reaches=reaches,
                            _price_shuffle_loss=False)
                        for field in OptionUnits.__dataclass_fields__:
                            if field != "cost":
                                values[field] -= gate * max(0.0, getattr(units, field))
            elif clause.kind == "fetch":
                values["search"] += gate * _quantity(clause.amount, 1)
            elif clause.kind in {"accel", "energy_recur", "move_energy"}:
                values["acceleration"] += gate * (
                    _quantity(clause.amount, 1) + _quantity(clause.to_hand))
            elif clause.kind == "heal":
                _target, healed, rider_cost = _heal_selection(
                    clause, facts, side, board, ctx)
                values["healing"] += gate * healed / DAMAGE_UNIT_HP
                values["cost"] += gate * rider_cost
            elif clause.kind in {"self_switch", "switch_self"}:
                values["mobility"] += gate * switch_target_units(side, board, ctx)
            elif clause.kind in {"gust", "push_out", "opp_hand_to_deck",
                                 "discard_opp_energy"}:
                values["denial"] += gate * _quantity(clause.amount, 1)
            elif clause.kind == "coin" and clause.effect in {
                    "discard_opp_energy", "energy_bounce"}:
                values["denial"] += (
                    gate * COIN_HEADS_PROBABILITY * _quantity(clause.amount, 1))
            elif clause.kind == "deck_top":
                values["search"] += gate * _quantity(clause.amount, 1)
        return OptionUnits(**{key: availability * value for key, value in values.items()})
    return OptionUnits()


def switch_target_units(side, board, ctx) -> float:
    if side.active is None or not side.bench:
        return 0.0
    blocked = any(bool(getattr(side, status)) for status in ("asleep", "paralyzed"))
    facts = ctx.facts(side.active.card.card_id)
    retreat_cost = int(getattr(facts, "retreat_cost", 0) or 0)
    reduction = sum(
        int(clause.amount or 0)
        for tool in side.active.tools
        for clause in card_clauses(ctx.facts(tool.card_id))
        if clause.kind == "retreat_reduction")
    payable = len(side.active.energies) >= max(0, retreat_cost - reduction)
    retreat_available = not board.turn.retreated and not blocked and payable
    return float(not retreat_available)


def card_option_value(facts, side, opponent, board, ctx, *, reaches=None) -> float:
    return card_option_units(
        facts, side, opponent, board, ctx, reaches=reaches).total


def hidden_zone_expectation(count, side, opponent_side, board, ctx, belief, *,
                            option_value=None) -> float:
    if belief is None or not belief.candidates:
        return float(count)
    expectation = float(belief.unknown_mass)
    represented = float(belief.unknown_mass)
    option_value = (lambda facts: card_option_value(
        facts, side, opponent_side, board, ctx)) if option_value is None else option_value
    for candidate in belief.candidates:
        resources = tuple((int(card_id), max(0.0, float(probability)))
                          for card_id, probability in candidate.resources.items()
                          if probability > 0)
        mass = sum(probability for _card_id, probability in resources)
        quality = (1.0 if not mass else sum(
            probability * (1.0 + max(0.0, option_value(ctx.facts(card_id))))
            for card_id, probability in resources) / mass)
        expectation += candidate.probability * quality
        represented += candidate.probability
    expectation += max(0.0, 1.0 - represented)
    return float(count) * expectation


def _prospective_condition(condition, side, board, ctx) -> float:
    if not condition:
        return 1.0
    condition = str(condition)
    if condition.endswith("_in_play"):
        wanted = condition.removesuffix("_in_play").replace("_", " ").casefold()
        return float(any(name.casefold() == wanted for name in _side_names(side, ctx)))
    if condition == "pokemon_ko_last_turn":
        return float(_knockout_visible(board))
    exact = _condition_probability(condition, None, side, board, ctx)
    return FUTURE_TURN_DISCOUNT if exact is None else exact


__all__ = (
    "Capability", "OptionUnits", "attack_damage", "best_current_damage",
    "best_energy_marginal", "body_capability", "card_option_units",
    "switch_target_units",
    "card_option_value", "energy_marginal", "hidden_zone_expectation", "payment_fraction",
    "recoverable_discard_ids", "unmet_cost_slots",
    "clause_cost_units", "clause_rider_cost_units", "clause_value_units",
    "expected_draw_counts",
)
