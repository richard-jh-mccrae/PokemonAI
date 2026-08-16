from __future__ import annotations

import pytest

from common.effects import CardEffects
from common.demand import (
    CoverageEdge, DemandSlot, DemandModel, access_probability, best_assignment,
)
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.value import CardFacts, Potential, ValueRegistry


LINE_BASE = 901
LINE_TOP = 902
SUPPORTER = 903
UNRELATED = 904
GEAR = 905
ENERGY = 906
ACCELERATOR = 907
MARNIE_TARGET = 908
ATTACK = 909
FIRE_ENERGY = 910


def _potential(observation):
    mine = observation["current"]["players"][0]
    hand = 0.2 * len(mine.get("hand") or ())
    body = next((body for body in mine.get("bench") or () if body), None)
    board = 0.0
    if body and int(body.get("id", 0)) == LINE_TOP:
        board = 1.0
        if int(body.get("hp", 0)) == int(body.get("maxHp", 0)):
            board += 0.3
    families = (("board", board), ("hand", hand))
    return Potential(sum(value for _name, value in families), families)


def _observation(hand, *, appeared=True, body=True):
    bench = []
    if body:
        bench.append({
            "id": LINE_BASE, "hp": 30, "maxHp": 60, "appearThisTurn": appeared,
            "preEvolution": [], "energies": [], "energyCards": [], "tools": [],
        })
    return {
        "current": {
            "yourIndex": 0, "turn": 2, "supporterPlayed": True,
            "energyAttached": True, "retreated": False, "stadiumPlayed": False,
            "players": [
                {"hand": [{"id": card_id} for card_id in hand], "handCount": len(hand),
                 "active": [], "bench": bench, "discard": [], "prize": [None] * 6},
                {"hand": None, "handCount": 0, "active": [], "bench": [],
                 "discard": [], "prize": [None] * 6},
            ],
        },
    }


def _model():
    registry = ValueRegistry(
        roles={LINE_TOP: ("primary_attacker",)},
        facts={
            LINE_BASE: CardFacts(pokemon=True, stage="basic"),
            LINE_TOP: CardFacts(pokemon=True, stage="stage1"),
            SUPPORTER: CardFacts(),
            UNRELATED: CardFacts(),
        },
        lines=((LINE_BASE, LINE_TOP),), line_pairs=((LINE_BASE, LINE_TOP),),
    )
    stats = DictCardStatProvider({
        LINE_BASE: CardStat(LINE_BASE, hp=60, stage="basic"),
        LINE_TOP: CardStat(LINE_TOP, hp=330, stage="stage1", megaEx=True),
        SUPPORTER: CardStat(SUPPORTER, cardType=3),
        UNRELATED: CardStat(UNRELATED, cardType=1),
    })
    return DemandModel(registry, _potential, effects=CardEffects({}), stats=stats)


def test_assignment_never_uses_one_card_or_demand_twice():
    assignment = best_assignment((((0, 1.0), (1, 0.8)), ((0, 0.9),)), 2)

    assert assignment.value == pytest.approx(1.7)
    assert assignment.covered_mask == 0b11
    assert assignment.used_card_mask == 0b11


def test_next_turn_evolution_has_situational_value_beyond_equal_static_hand_worth():
    model = _model()

    useful = model.next_turn_retained(
        _observation([LINE_TOP, UNRELATED]), 0, [LINE_TOP, UNRELATED])
    unrelated = model.next_turn_retained(
        _observation([UNRELATED]), 0, [UNRELATED])

    assert useful.value == pytest.approx(0.8)
    assert useful.options[0].description.startswith("evolve:")
    assert unrelated.value == 0.0


def test_visible_board_demands_do_not_require_a_visible_hand():
    observation = _observation([], appeared=False)
    observation["current"]["players"][0]["hand"] = None
    observation["current"]["players"][0]["handCount"] = 3

    demands = _model().immediate(observation, 0)

    assert any(demand.key.startswith("evolve:") for demand in demands)


def test_heal_bounce_accepts_hidden_hand_without_mutating_observation():
    observation = _observation([], appeared=False)
    player = observation["current"]["players"][0]
    player["hand"] = None
    player["handCount"] = 3
    player["bench"] = [{
        "id": LINE_TOP, "hp": 200, "maxHp": 330, "appearThisTurn": False,
        "preEvolution": [{"id": LINE_BASE}], "energies": [3],
        "energyCards": [{"id": ENERGY}], "tools": [],
    }]
    model = _model()

    gain = model._heal_gain(
        observation, 0,
        {"kind": "heal", "amount": "all", "restriction": "mega_only",
         "rider": "bounce_energy_to_hand"},
        target=("bench", 0))

    assert gain > 0.0
    assert observation["current"]["players"][0]["hand"] is None
    assert observation["current"]["players"][0]["handCount"] == 3


def test_multi_target_fetch_provides_one_assignment_token_per_printed_target():
    model = _model()
    demands = (
        DemandSlot("setup:one", ((LINE_BASE, 0.5),)),
        DemandSlot("setup:two", ((LINE_BASE, 0.5),)),
    )
    effects = CardEffects({SUPPORTER: [{
        "kind": "fetch", "target": "pokemon", "zone": "deck", "amount": 2,
    }]})
    model = DemandModel(model.registry, _potential, effects=effects, stats=model.stats)

    tokens = model.coverage_slots(
        SUPPORTER, demands, supporter_available=True, discard_capacity=0,
        available_targets={LINE_BASE: 2})
    assignment = best_assignment(tokens, len(demands), target_counts={LINE_BASE: 2})

    assert len(tokens) == 2
    assert assignment.value == pytest.approx(1.0)


def test_fetch_without_a_remaining_target_is_not_an_out():
    model = _model()
    demand = DemandSlot("develop", ((LINE_TOP, 1.0),))
    effects = CardEffects({SUPPORTER: [{
        "kind": "fetch", "target": "pokemon", "zone": "deck",
    }]})
    model = DemandModel(model.registry, _potential, effects=effects, stats=model.stats)

    assert model.coverage_slots(
        SUPPORTER, (demand,), supporter_available=True, discard_capacity=0,
        available_targets={LINE_TOP: 0}) == ()


def test_available_held_supporter_removes_the_demand_it_can_guarantee():
    base = _model()
    effects = CardEffects({SUPPORTER: [{
        "kind": "fetch", "target": "pokemon", "zone": "deck",
    }]})
    model = DemandModel(base.registry, _potential, effects=effects, stats=base.stats)
    demand = DemandSlot("evolve", ((LINE_TOP, 1.0),))

    assert model.uncovered_by_hand(
        (demand,), (SUPPORTER,), supporter_available=True, discard_capacity=0,
        available_targets={LINE_TOP: 1}) == ()
    assert model.uncovered_by_hand(
        (demand,), (SUPPORTER,), supporter_available=False, discard_capacity=0,
        available_targets={LINE_TOP: 1}) == (demand,)


def test_attack_demands_name_the_recipient_attack_typed_slot_and_matching_energy():
    registry = ValueRegistry(
        facts={
            LINE_TOP: CardFacts(pokemon=True, stage="stage1"),
            ENERGY: CardFacts(), FIRE_ENERGY: CardFacts(),
        },
    )
    stats = DictCardStatProvider({
        LINE_TOP: CardStat(LINE_TOP, hp=100, stage="stage1", attacks=(ATTACK,)),
        ENERGY: CardStat(ENERGY, cardType=5, energyType=3),
        FIRE_ENERGY: CardStat(FIRE_ENERGY, cardType=5, energyType=2),
    }, attacks={ATTACK: AttackStat(ATTACK, cost=2, energyTypes=(3, 2))})

    def energy_potential(observation):
        active = observation["current"]["players"][0]["active"][0]
        value = float(len(active.get("energyCards") or ()))
        return Potential(value, (("energy_position", value),))

    model = DemandModel(registry, energy_potential, effects=CardEffects({}), stats=stats)
    observation = _observation([])
    observation["current"]["energyAttached"] = False
    observation["current"]["players"][0]["bench"] = []
    observation["current"]["players"][0]["active"] = [{
        "id": LINE_TOP, "serial": 77, "hp": 100, "maxHp": 100,
        "preEvolution": [{"id": LINE_BASE}], "energies": [3],
        "energyCards": [{"id": ENERGY}], "tools": [],
    }]

    demands = model.immediate(observation, 0)
    funding = tuple(demand for demand in demands if demand.capability == "fund_attack")

    assert [demand.key for demand in funding] == [f"fund_attack:77:{ATTACK}:1:2"]
    assert funding[0].recipient == "77"
    assert funding[0].slot == "1:2"
    assert dict(funding[0].direct) == {FIRE_ENERGY: pytest.approx(1.0)}


def test_multi_unit_energy_covers_multiple_slots_for_only_its_chosen_recipient():
    registry = ValueRegistry(
        functions={ENERGY: ("provides:3",)}, facts={ENERGY: CardFacts()})
    stats = DictCardStatProvider({ENERGY: CardStat(ENERGY, cardType=6, energyType=0)})
    model = DemandModel(registry, _potential, effects=CardEffects({}), stats=stats)
    demands = tuple(
        DemandSlot(f"fund_attack:77:1:{slot}:0", ((ENERGY, 0.5),),
             recipient="77", capability="fund_attack", slot=f"{slot}:0")
        for slot in range(3)
    ) + (DemandSlot(
        "fund_attack:88:1:0:0", ((ENERGY, 1.0),),
        recipient="88", capability="fund_attack", slot="0:0"),)

    tokens = model.coverage_slots(
        ENERGY, demands, supporter_available=True, discard_capacity=0,
        recipient="77", provision_units=3)
    assignment = best_assignment(tokens, len(demands))

    assert len(tokens) == 3
    assert assignment.value == pytest.approx(1.5)
    assert assignment.covered_mask == 0b0111


def test_multi_unit_energy_distributes_one_operation_gain_across_covered_slots():
    registry = ValueRegistry(
        functions={ENERGY: ("provides:3",)},
        facts={LINE_TOP: CardFacts(pokemon=True, stage="stage1"), ENERGY: CardFacts()},
    )
    stats = DictCardStatProvider({
        LINE_TOP: CardStat(LINE_TOP, hp=100, stage="stage1", attacks=(ATTACK,)),
        ENERGY: CardStat(ENERGY, cardType=6, energyType=0),
    }, attacks={ATTACK: AttackStat(ATTACK, cost=3, energyTypes=(0, 0, 0))})

    def energy_potential(observation):
        active = observation["current"]["players"][0]["active"][0]
        value = float(len(active.get("energies") or ()))
        return Potential(value, (("energy_position", value),))

    model = DemandModel(registry, energy_potential, effects=CardEffects({}), stats=stats)
    observation = _observation([])
    observation["current"]["energyAttached"] = False
    observation["current"]["players"][0]["bench"] = []
    observation["current"]["players"][0]["active"] = [{
        "id": LINE_TOP, "serial": 77, "hp": 100, "maxHp": 100,
        "preEvolution": [], "energies": [], "energyCards": [], "tools": [],
    }]

    demands = tuple(demand for demand in model.immediate(observation, 0)
                  if demand.capability == "fund_attack")
    signatures = model.coverage_slots(
        ENERGY, demands, supporter_available=True, discard_capacity=0,
        recipient="77", provision_units=3)
    assignment = best_assignment(signatures, len(demands))

    assert len(demands) == 3
    assert assignment.value == pytest.approx(3.0)


def test_multi_unit_energy_never_combines_alternative_attacks_on_one_recipient():
    registry = ValueRegistry(
        functions={ENERGY: ("provides:3",)}, facts={ENERGY: CardFacts()})
    stats = DictCardStatProvider({ENERGY: CardStat(ENERGY, cardType=6, energyType=0)})
    model = DemandModel(registry, _potential, effects=CardEffects({}), stats=stats)
    demands = (
        DemandSlot("fund_attack:77:10:0:0", ((ENERGY, 0.8),), recipient="77",
             capability="fund_attack", slot="0:0", alternative="10"),
        DemandSlot("fund_attack:77:10:1:0", ((ENERGY, 0.8),), recipient="77",
             capability="fund_attack", slot="1:0", alternative="10"),
        DemandSlot("fund_attack:77:20:0:0", ((ENERGY, 1.0),), recipient="77",
             capability="fund_attack", slot="0:0", alternative="20"),
    )

    tokens = model.coverage_slots(
        ENERGY, demands, supporter_available=True, discard_capacity=0,
        recipient="77", provision_units=2)
    assignment = best_assignment(tokens, len(demands))

    assert assignment.value == pytest.approx(1.6)
    assert assignment.covered_mask == 0b011


def test_one_multi_unit_energy_cannot_split_its_units_across_recipients():
    registry = ValueRegistry(
        functions={ENERGY: ("provides_evo:3",)}, facts={ENERGY: CardFacts()})
    stats = DictCardStatProvider({ENERGY: CardStat(ENERGY, cardType=6, energyType=0)})
    model = DemandModel(registry, _potential, effects=CardEffects({}), stats=stats)
    demands = tuple(
        DemandSlot(f"fund_attack:77:1:{slot}:0", ((ENERGY, 1.0),), recipient="77",
             capability="fund_attack", slot=f"{slot}:0", alternative="1")
        for slot in range(3)
    ) + (DemandSlot(
        "fund_attack:88:2:0:0", ((ENERGY, 2.0),), recipient="88",
        capability="fund_attack", slot="0:0", alternative="2"),)

    tokens = model.coverage_slots(
        ENERGY, demands, supporter_available=True, discard_capacity=0,
        recipient_units={"77": 3, "88": 1}, resource_group="held:0")
    assignment = best_assignment(tokens, len(demands))

    assert assignment.value == pytest.approx(3.0)
    assert assignment.covered_mask == 0b0111


def test_assignment_never_combines_alternative_attacks_across_fetch_tokens():
    signatures = (
        (CoverageEdge(0, 0.8, 10, "77:fund_attack", "attack-a"),
         CoverageEdge(1, 1.0, 20, "77:fund_attack", "attack-b")),
        (CoverageEdge(0, 0.8, 10, "77:fund_attack", "attack-a"),
         CoverageEdge(1, 1.0, 20, "77:fund_attack", "attack-b")),
    )

    assignment = best_assignment(signatures, 2, target_counts={10: 1, 20: 1})

    assert assignment.value == pytest.approx(1.0)
    assert assignment.covered_mask in {0b01, 0b10}


def test_global_assignment_preserves_cross_energy_attack_plan_complementarity():
    wildcard, b_one, b_two = 910, 911, 912
    registry = ValueRegistry(facts={
        wildcard: CardFacts(), b_one: CardFacts(), b_two: CardFacts()})
    stats = DictCardStatProvider({
        card_id: CardStat(card_id, cardType=5, energyType=0)
        for card_id in (wildcard, b_one, b_two)
    })
    model = DemandModel(registry, _potential, effects=CardEffects({}), stats=stats)
    demands = (
        DemandSlot("a", ((wildcard, 0.9),), recipient="77", capability="fund_attack",
             slot="0", alternative="attack-a"),
        DemandSlot("b0", ((wildcard, 0.8), (b_one, 0.8)), recipient="77",
             capability="fund_attack", slot="0", alternative="attack-b"),
        DemandSlot("b1", ((wildcard, 0.8), (b_two, 0.8)), recipient="77",
             capability="fund_attack", slot="1", alternative="attack-b"),
        DemandSlot("b2", ((wildcard, 0.8), (b_one, 0.8), (b_two, 0.8)), recipient="77",
             capability="fund_attack", slot="2", alternative="attack-b"),
    )
    signatures = tuple(
        token
        for card_id in (wildcard, b_one, b_two)
        for token in model.coverage_slots(
            card_id, demands, supporter_available=True, discard_capacity=0,
            recipient="77")
    )

    assignment = best_assignment(signatures, len(demands))

    assert assignment.value == pytest.approx(2.4)
    assert assignment.covered_mask == 0b1110


def test_removing_a_recipient_removes_all_of_its_demand_roots():
    registry = ValueRegistry(
        facts={LINE_TOP: CardFacts(pokemon=True, stage="stage1"), ENERGY: CardFacts()})
    stats = DictCardStatProvider({
        LINE_TOP: CardStat(LINE_TOP, hp=100, stage="stage1", attacks=(ATTACK,)),
        ENERGY: CardStat(ENERGY, cardType=5, energyType=0),
    }, attacks={ATTACK: AttackStat(ATTACK, cost=1, energyTypes=(0,))})
    def energy_potential(observation):
        active = observation["current"]["players"][0].get("active") or ()
        value = float(len(active[0].get("energyCards") or ())) if active else 0.0
        return Potential(value, (("energy_position", value),))

    model = DemandModel(registry, energy_potential, effects=CardEffects({}), stats=stats)
    observation = _observation([])
    observation["current"]["energyAttached"] = False
    observation["current"]["players"][0]["active"] = [{
        "id": LINE_TOP, "serial": 77, "hp": 100, "maxHp": 100,
        "energies": [], "energyCards": [], "tools": [], "preEvolution": [],
    }]

    assert any(demand.recipient == "77" for demand in model.immediate(observation, 0))
    observation["current"]["players"][0]["active"] = []
    assert all(demand.recipient != "77" for demand in model.immediate(observation, 0))


@pytest.mark.parametrize("observation", (
    _observation([LINE_TOP], appeared=False),
    _observation([LINE_TOP], body=False),
))
def test_next_turn_evolution_option_disappears_when_the_enabling_clock_or_body_is_absent(observation):
    resolved = _model().next_turn_retained(observation, 0, [LINE_TOP])

    assert resolved.value == 0.0
    assert resolved.options == ()



def test_undeclared_funding_reads_the_cost_off_the_card():
    """A fund_attack hint that names no Energy funds the recipient's own unmet printed cost, so
    an Energy that pays nothing it owes is not treated as funding."""
    from types import SimpleNamespace
    from common.demand import StrategyBeamBuilder
    from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
    from common.strategy.strategies import ActivatedStrategy, StrategySnapshot

    attacker, fire, psychic, darkness = 810, 2, 5, 7
    stats = DictCardStatProvider(
        {
            attacker: CardStat(attacker, hp=320, attacks=(11,)),
            fire: CardStat(fire, cardType=5, energyType=fire),
            psychic: CardStat(psychic, cardType=5, energyType=psychic),
            darkness: CardStat(darkness, cardType=5, energyType=darkness),
        },
        attacks={11: AttackStat(11, damage=200, energyTypes=(fire, psychic))},
    )
    hint = ActivatedStrategy(
        "deck.fund", "fund_attack", "own.active", attacker, 1, (), "immediate", "high", None, 0)
    builder = StrategyBeamBuilder(
        StrategySnapshot(1, 0, "hash", "snapshot", (), (), (hint,)), stats=stats)
    observation = {"current": {"yourIndex": 0, "turn": 1, "players": [
        {"active": [{"id": attacker, "serial": 1, "hp": 320, "maxHp": 320,
                     "energies": [fire]}], "bench": []},
        {"active": [], "bench": []},
    ]}, "select": {"context": 0, "option": []}}
    state = SimpleNamespace(
        obs=observation, root_seat=0,
        deck_counts=((fire, 3), (psychic, 3), (darkness, 2)))

    # One Fire is already attached, so only the Psychic slot is still owed.
    assert builder._funding_energy_ids(state, hint) == (psychic,)
    assert builder._funds_the_cost(state, hint, psychic)
    assert not builder._funds_the_cost(state, hint, darkness)


def test_a_colorless_slot_does_not_make_every_energy_funding():
    """A Colorless slot accepts anything, so a body owing one looked funded by every Energy in
    the deck -- including one another body needs by type. A printed TYPE owed anywhere wins."""
    from types import SimpleNamespace
    from common.demand import StrategyBeamBuilder
    from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
    from common.strategy.strategies import ActivatedStrategy, StrategySnapshot

    attacker, colorless_only, fire, psychic, darkness = 820, 821, 2, 5, 7
    stats = DictCardStatProvider(
        {
            # Two attacks, as Dragapult ex has: a one-Colorless poke and the real typed attack.
            attacker: CardStat(attacker, hp=320, attacks=(12, 13)),
            colorless_only: CardStat(colorless_only, hp=210, attacks=(12,)),
            fire: CardStat(fire, cardType=5, energyType=fire),
            psychic: CardStat(psychic, cardType=5, energyType=psychic),
            darkness: CardStat(darkness, cardType=5, energyType=darkness),
        },
        attacks={
            12: AttackStat(12, damage=70, energyTypes=(0,)),
            13: AttackStat(13, damage=200, energyTypes=(fire, psychic)),
        },
    )
    counts = ((fire, 3), (psychic, 3), (darkness, 2))

    def eligible(card_id):
        hint = ActivatedStrategy(
            "deck.fund", "fund_attack", "own.active", card_id, 1, (),
            "immediate", "high", None, 0)
        builder = StrategyBeamBuilder(
            StrategySnapshot(1, 0, "hash", "snapshot", (), (), (hint,)), stats=stats)
        observation = {"current": {"yourIndex": 0, "turn": 1, "players": [
            {"active": [{"id": card_id, "serial": 1, "hp": 320, "maxHp": 320,
                         "energies": []}], "bench": []},
            {"active": [], "bench": []},
        ]}, "select": {"context": 0, "option": []}}
        return builder._funding_energy_ids(
            SimpleNamespace(obs=observation, root_seat=0, deck_counts=counts), hint)

    # The Colorless slot is unpaid too, but a printed type is owed, so Darkness is not funding.
    assert eligible(attacker) == (fire, psychic)
    # Nothing typed is owed anywhere on this body, so every Energy genuinely does fund it.
    assert eligible(colorless_only) == (fire, psychic, darkness)


def test_funding_satisfies_only_once_the_body_owes_nothing():
    """A bundle holds every later waypoint until the earlier ones satisfy, so a fund_attack
    outcome that can never report satisfied strands the attack behind it for the whole turn."""
    from types import SimpleNamespace
    from common.demand import StrategyBeamBuilder
    from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
    from common.strategy.strategies import ActivatedStrategy, StrategySnapshot

    attacker, fire, psychic = 830, 2, 5
    stats = DictCardStatProvider(
        {
            attacker: CardStat(attacker, hp=320, attacks=(14,)),
            fire: CardStat(fire, cardType=5, energyType=fire),
            psychic: CardStat(psychic, cardType=5, energyType=psychic),
        },
        attacks={14: AttackStat(14, damage=200, energyTypes=(fire, psychic))},
    )
    funding = ActivatedStrategy(
        "deck.fund", "fund_attack", "own.active", attacker, 1, (),
        "immediate", "high", "deck.line", 0)
    swing = ActivatedStrategy(
        "deck.swing", "damage_setup", "opponent.bench.highest_role", attacker, 9, (),
        "immediate", "high", "deck.line", 1)
    builder = StrategyBeamBuilder(
        StrategySnapshot(1, 0, "hash", "snapshot", (), (), (funding, swing)), stats=stats)

    def _status(energies):
        observation = {"current": {"yourIndex": 0, "turn": 1, "players": [
            {"active": [{"id": attacker, "serial": 1, "hp": 320, "maxHp": 320,
                         "energies": list(energies)}], "bench": []},
            {"active": [], "bench": [{"id": attacker, "serial": 9, "hp": 60, "maxHp": 320}]},
        ]}, "select": {"context": 0, "option": []}}
        rows = builder.outcome_statuses(
            SimpleNamespace(obs=observation, root_seat=0, deck_counts=()))
        return {row["strategy_id"]: row["status"] for row in rows}

    # Half the cost down: funding is still live, so the swing behind it stays held.
    assert _status((fire,))["deck.fund"] != "satisfied"
    assert _status((fire,))["deck.swing"] == "held"
    # Cost fully paid: funding satisfies and the swing is released within the same turn.
    assert _status((fire, psychic))["deck.fund"] == "satisfied"
    assert _status((fire, psychic))["deck.swing"] != "held"


def test_an_unreadable_body_never_reports_its_funding_satisfied():
    """"No cost we can see" is not "no cost owed" -- calling it satisfied would release a
    bundle on missing information."""
    from types import SimpleNamespace
    from common.demand import StrategyBeamBuilder
    from common.scouting.provider import CardStat, DictCardStatProvider
    from common.strategy.strategies import ActivatedStrategy, StrategySnapshot

    mystery = 831
    stats = DictCardStatProvider({mystery: CardStat(mystery, hp=100)})
    hint = ActivatedStrategy(
        "deck.fund", "fund_attack", "own.active", mystery, 1, (),
        "immediate", "high", None, 0)
    builder = StrategyBeamBuilder(
        StrategySnapshot(1, 0, "hash", "snapshot", (), (), (hint,)), stats=stats)
    observation = {"current": {"yourIndex": 0, "turn": 1, "players": [
        {"active": [{"id": mystery, "serial": 1, "hp": 100, "maxHp": 100, "energies": []}],
         "bench": []},
        {"active": [], "bench": []},
    ]}, "select": {"context": 0, "option": []}}

    rows = builder.outcome_statuses(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()))

    assert rows[0]["status"] != "satisfied"
