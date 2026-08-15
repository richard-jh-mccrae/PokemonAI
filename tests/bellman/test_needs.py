from __future__ import annotations

from types import SimpleNamespace

import pytest

from common import ActionIdentity
from common.effects import CardEffects
from common.needs import (
    AccessEdge, CapabilityIndex, CoverageEdge, Need, NeedBeam, NeedBeamBuilder, NeedModel,
    NeedPath, NeedRoot, PathFeatures, PokemonRole, access_probability, best_assignment, infer_pokemon_roles,
    opponent_threat_roots,
)
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.options import LegalAction
from common.value import CardFacts, Potential, ValueRegistry
from train.needs_lab import gate_failures


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
        roles={LINE_TOP: ("win_condition",)},
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
    return NeedModel(registry, _potential, effects=CardEffects({}), stats=stats)


def test_assignment_never_uses_one_card_or_need_twice():
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


def test_visible_board_needs_do_not_require_a_visible_hand():
    observation = _observation([], appeared=False)
    observation["current"]["players"][0]["hand"] = None
    observation["current"]["players"][0]["handCount"] = 3

    needs = _model().immediate(observation, 0)

    assert any(need.key.startswith("evolve:") for need in needs)


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
    needs = (
        Need("setup:one", ((LINE_BASE, 0.5),)),
        Need("setup:two", ((LINE_BASE, 0.5),)),
    )
    effects = CardEffects({SUPPORTER: [{
        "kind": "fetch", "target": "pokemon", "zone": "deck", "amount": 2,
    }]})
    model = NeedModel(model.registry, _potential, effects=effects, stats=model.stats)

    tokens = model.coverage_slots(
        SUPPORTER, needs, supporter_available=True, discard_capacity=0,
        available_targets={LINE_BASE: 2})
    assignment = best_assignment(tokens, len(needs), target_counts={LINE_BASE: 2})

    assert len(tokens) == 2
    assert assignment.value == pytest.approx(1.0)


def test_fetch_without_a_remaining_target_is_not_an_out():
    model = _model()
    need = Need("develop", ((LINE_TOP, 1.0),))
    effects = CardEffects({SUPPORTER: [{
        "kind": "fetch", "target": "pokemon", "zone": "deck",
    }]})
    model = NeedModel(model.registry, _potential, effects=effects, stats=model.stats)

    assert model.coverage_slots(
        SUPPORTER, (need,), supporter_available=True, discard_capacity=0,
        available_targets={LINE_TOP: 0}) == ()


def test_available_held_supporter_removes_the_need_it_can_guarantee():
    base = _model()
    effects = CardEffects({SUPPORTER: [{
        "kind": "fetch", "target": "pokemon", "zone": "deck",
    }]})
    model = NeedModel(base.registry, _potential, effects=effects, stats=base.stats)
    need = Need("evolve", ((LINE_TOP, 1.0),))

    assert model.uncovered_by_hand(
        (need,), (SUPPORTER,), supporter_available=True, discard_capacity=0,
        available_targets={LINE_TOP: 1}) == ()
    assert model.uncovered_by_hand(
        (need,), (SUPPORTER,), supporter_available=False, discard_capacity=0,
        available_targets={LINE_TOP: 1}) == (need,)


def test_attack_needs_name_the_recipient_attack_typed_slot_and_matching_energy():
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

    model = NeedModel(registry, energy_potential, effects=CardEffects({}), stats=stats)
    observation = _observation([])
    observation["current"]["energyAttached"] = False
    observation["current"]["players"][0]["bench"] = []
    observation["current"]["players"][0]["active"] = [{
        "id": LINE_TOP, "serial": 77, "hp": 100, "maxHp": 100,
        "preEvolution": [{"id": LINE_BASE}], "energies": [3],
        "energyCards": [{"id": ENERGY}], "tools": [],
    }]

    needs = model.immediate(observation, 0)
    funding = tuple(need for need in needs if need.capability == "fund_attack")

    assert [need.key for need in funding] == [f"fund_attack:77:{ATTACK}:1:2"]
    assert funding[0].recipient == "77"
    assert funding[0].slot == "1:2"
    assert dict(funding[0].direct) == {FIRE_ENERGY: pytest.approx(1.0)}


def test_multi_unit_energy_covers_multiple_slots_for_only_its_chosen_recipient():
    registry = ValueRegistry(
        functions={ENERGY: ("provides:3",)}, facts={ENERGY: CardFacts()})
    stats = DictCardStatProvider({ENERGY: CardStat(ENERGY, cardType=6, energyType=0)})
    model = NeedModel(registry, _potential, effects=CardEffects({}), stats=stats)
    needs = tuple(
        Need(f"fund_attack:77:1:{slot}:0", ((ENERGY, 0.5),),
             recipient="77", capability="fund_attack", slot=f"{slot}:0")
        for slot in range(3)
    ) + (Need(
        "fund_attack:88:1:0:0", ((ENERGY, 1.0),),
        recipient="88", capability="fund_attack", slot="0:0"),)

    tokens = model.coverage_slots(
        ENERGY, needs, supporter_available=True, discard_capacity=0,
        recipient="77", provision_units=3)
    assignment = best_assignment(tokens, len(needs))

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

    model = NeedModel(registry, energy_potential, effects=CardEffects({}), stats=stats)
    observation = _observation([])
    observation["current"]["energyAttached"] = False
    observation["current"]["players"][0]["bench"] = []
    observation["current"]["players"][0]["active"] = [{
        "id": LINE_TOP, "serial": 77, "hp": 100, "maxHp": 100,
        "preEvolution": [], "energies": [], "energyCards": [], "tools": [],
    }]

    needs = tuple(need for need in model.immediate(observation, 0)
                  if need.capability == "fund_attack")
    signatures = model.coverage_slots(
        ENERGY, needs, supporter_available=True, discard_capacity=0,
        recipient="77", provision_units=3)
    assignment = best_assignment(signatures, len(needs))

    assert len(needs) == 3
    assert assignment.value == pytest.approx(3.0)


def test_multi_unit_energy_never_combines_alternative_attacks_on_one_recipient():
    registry = ValueRegistry(
        functions={ENERGY: ("provides:3",)}, facts={ENERGY: CardFacts()})
    stats = DictCardStatProvider({ENERGY: CardStat(ENERGY, cardType=6, energyType=0)})
    model = NeedModel(registry, _potential, effects=CardEffects({}), stats=stats)
    needs = (
        Need("fund_attack:77:10:0:0", ((ENERGY, 0.8),), recipient="77",
             capability="fund_attack", slot="0:0", alternative="10"),
        Need("fund_attack:77:10:1:0", ((ENERGY, 0.8),), recipient="77",
             capability="fund_attack", slot="1:0", alternative="10"),
        Need("fund_attack:77:20:0:0", ((ENERGY, 1.0),), recipient="77",
             capability="fund_attack", slot="0:0", alternative="20"),
    )

    tokens = model.coverage_slots(
        ENERGY, needs, supporter_available=True, discard_capacity=0,
        recipient="77", provision_units=2)
    assignment = best_assignment(tokens, len(needs))

    assert assignment.value == pytest.approx(1.6)
    assert assignment.covered_mask == 0b011


def test_one_multi_unit_energy_cannot_split_its_units_across_recipients():
    registry = ValueRegistry(
        functions={ENERGY: ("provides_evo:3",)}, facts={ENERGY: CardFacts()})
    stats = DictCardStatProvider({ENERGY: CardStat(ENERGY, cardType=6, energyType=0)})
    model = NeedModel(registry, _potential, effects=CardEffects({}), stats=stats)
    needs = tuple(
        Need(f"fund_attack:77:1:{slot}:0", ((ENERGY, 1.0),), recipient="77",
             capability="fund_attack", slot=f"{slot}:0", alternative="1")
        for slot in range(3)
    ) + (Need(
        "fund_attack:88:2:0:0", ((ENERGY, 2.0),), recipient="88",
        capability="fund_attack", slot="0:0", alternative="2"),)

    tokens = model.coverage_slots(
        ENERGY, needs, supporter_available=True, discard_capacity=0,
        recipient_units={"77": 3, "88": 1}, resource_group="held:0")
    assignment = best_assignment(tokens, len(needs))

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
    model = NeedModel(registry, _potential, effects=CardEffects({}), stats=stats)
    needs = (
        Need("a", ((wildcard, 0.9),), recipient="77", capability="fund_attack",
             slot="0", alternative="attack-a"),
        Need("b0", ((wildcard, 0.8), (b_one, 0.8)), recipient="77",
             capability="fund_attack", slot="0", alternative="attack-b"),
        Need("b1", ((wildcard, 0.8), (b_two, 0.8)), recipient="77",
             capability="fund_attack", slot="1", alternative="attack-b"),
        Need("b2", ((wildcard, 0.8), (b_one, 0.8), (b_two, 0.8)), recipient="77",
             capability="fund_attack", slot="2", alternative="attack-b"),
    )
    signatures = tuple(
        token
        for card_id in (wildcard, b_one, b_two)
        for token in model.coverage_slots(
            card_id, needs, supporter_available=True, discard_capacity=0,
            recipient="77")
    )

    assignment = best_assignment(signatures, len(needs))

    assert assignment.value == pytest.approx(2.4)
    assert assignment.covered_mask == 0b1110


def test_removing_a_recipient_removes_all_of_its_need_roots():
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

    model = NeedModel(registry, energy_potential, effects=CardEffects({}), stats=stats)
    observation = _observation([])
    observation["current"]["energyAttached"] = False
    observation["current"]["players"][0]["active"] = [{
        "id": LINE_TOP, "serial": 77, "hp": 100, "maxHp": 100,
        "energies": [], "energyCards": [], "tools": [], "preEvolution": [],
    }]

    assert any(need.recipient == "77" for need in model.immediate(observation, 0))
    observation["current"]["players"][0]["active"] = []
    assert all(need.recipient != "77" for need in model.immediate(observation, 0))


@pytest.mark.parametrize("observation", (
    _observation([LINE_TOP], appeared=False),
    _observation([LINE_TOP], body=False),
))
def test_next_turn_evolution_option_disappears_when_the_enabling_clock_or_body_is_absent(observation):
    resolved = _model().next_turn_retained(observation, 0, [LINE_TOP])

    assert resolved.value == 0.0
    assert resolved.options == ()


def test_capability_index_uses_mechanics_effects_and_tags_without_hiding_unknown_cards():
    model = _model()
    effects = CardEffects({SUPPORTER: [
        {"kind": "fetch", "target": "pokemon", "zone": "deck", "dig": 3},
    ]})
    functions = {UNRELATED: ("energy_denial",)}

    index = CapabilityIndex.compile(
        (LINE_BASE, LINE_TOP, SUPPORTER, UNRELATED, 999),
        stats=model.stats, effects=effects, functions=functions,
    )

    assert index.kinds(LINE_BASE) == ("deploy",)
    assert index.kinds(LINE_TOP) == ("evolve",)
    assert index.kinds(SUPPORTER) == ("dig", "fetch")
    assert index.kinds(UNRELATED) == ("energy_denial",)
    assert index.kinds(999) == ()
    assert index.unknown == (999,)


def test_need_contracts_are_immutable_serializable_and_semantically_stable():
    root = NeedRoot("fund", "attack_ready:active", 1, "establish_attacker", 1.0, "generic")
    edge = AccessEdge(3, "attach", (root.semantic_id,), 0, True, 1.0, 1.0)
    path = NeedPath((root.semantic_id,), (edge,), (), (), 0, 1.0, 1.0, "safe")
    features = PathFeatures("establish_attacker", 1, 0, 1, 1.0, 1.0, 1, 0, 0)
    beam = NeedBeam((), (), (), (path,), (features,), 0.2, False)

    assert root.semantic_id == NeedRoot(
        "fund", "attack_ready:active", 1, "establish_attacker", 1.0, "generic").semantic_id
    assert edge.semantic_id == edge.semantic_id
    assert beam.paths == (path,)
    with pytest.raises(Exception):
        root.deadline = 2


def test_access_probability_reuses_exact_hypergeometric_classes():
    assert access_probability((1, 1, 2, 3), 2, (1,)) == pytest.approx(5 / 6)
    assert access_probability((1, 1, 2, 3), 0, (1,)) == 0.0


def test_need_path_score_prefers_equal_access_without_irreversible_discards():
    root = NeedRoot("deploy", "deploy", 0, "establish_attacker", 1.0, "generic")
    edge = AccessEdge(GEAR, "fetch", (root.semantic_id,), 0, True, 1.0, 1.0)
    free = NeedPath((root.semantic_id,), (edge,), (), (), 0, 1.0, 1.0, "safe")
    costly = NeedPath(
        (root.semantic_id,), (edge,), ("discard:0", "discard:1"), (),
        0, 1.0, 1.0, "safe")

    assert NeedBeamBuilder._path_score(free, (root,)) > NeedBeamBuilder._path_score(
        costly, (root,))


def test_need_path_score_prioritizes_the_larger_recipient_ceiling():
    low = NeedRoot(
        "fund", "fund", 0, "take_prize", 1.0, "generic", ceiling=0.2)
    high = NeedRoot(
        "heal", "heal", 0, "prevent_prize", 1.0, "generic", ceiling=1.3)
    low_path = NeedPath(
        (low.semantic_id,), (), (), (), 0, 1.0, 1.0, "safe")
    high_path = NeedPath(
        (high.semantic_id,), (), (), (), 0, 1.0, 1.0, "safe")

    assert NeedBeamBuilder._path_score(high_path, (low, high)) > \
        NeedBeamBuilder._path_score(low_path, (low, high))


def test_known_top_path_is_emitted_once_independent_of_available_sources():
    model = _model()
    builder = NeedBeamBuilder(
        model, CapabilityIndex(((SUPPORTER, ("fetch",)), (GEAR, ("dig",))), ()))
    need = Need("evolve:active:0", ((LINE_TOP, 1.0),))
    root = builder._root(need)
    state = SimpleNamespace(
        deck_counts=((LINE_TOP, 1),),
        obs={"known_top": ((41, LINE_TOP),),
             "current": {"supporterPlayed": False, "players": [{"hand": []}, {}]}},
        root_seat=0,
    )

    paths = tuple(builder._access_paths(state, (root,), (need,)))

    assert sum(path.edges[0].capability == "known_top_draw" for path in paths) == 1


def test_access_budget_visits_current_legal_sources_before_future_deck_sources(monkeypatch):
    base = _model()
    effects = CardEffects({GEAR: [
        {"kind": "fetch", "target": "pokemon", "zone": "deck", "dig": 3},
    ]})
    model = NeedModel(base.registry, _potential, effects=effects, stats=base.stats)
    builder = NeedBeamBuilder(
        model, CapabilityIndex(((SUPPORTER, ("fetch",)), (GEAR, ("dig",))), ()))
    need = Need("evolve:active:0", ((LINE_TOP, 1.0),))
    root = builder._root(need)
    state = SimpleNamespace(
        deck_counts=((LINE_TOP, 1),), obs={"known_top": (), "current": {
            "supporterPlayed": False, "players": [{"hand": []}, {}]}}, root_seat=0)
    clock = iter((0.0, 0.0, 2.0, 2.0))
    monkeypatch.setattr("common.needs.perf_counter", lambda: next(clock))

    paths = tuple(builder._access_paths(
        state, (root,), (need,), deadline=1.0, source_ids=(GEAR,)))

    assert paths[0].edges[0].source_card_id == GEAR


def test_discard_recovery_is_a_current_need_path():
    base = _model()
    effects = CardEffects({SUPPORTER: [
        {"kind": "fetch", "target": "pokemon", "zone": "discard"},
    ]})
    model = NeedModel(base.registry, _potential, effects=effects, stats=base.stats)
    builder = NeedBeamBuilder(
        model, CapabilityIndex(((SUPPORTER, ("fetch",)),), ()))
    need = Need("deploy:line:0", ((LINE_BASE, 1.0),))
    root = builder._root(need)
    state = SimpleNamespace(
        deck_counts=(), root_seat=0,
        obs={"current": {"supporterPlayed": False, "players": [
            {"hand": [{"id": SUPPORTER}], "discard": [{"id": LINE_BASE}]}, {},
        ]}},
    )

    paths = tuple(builder._access_paths(
        state, (root,), (need,), source_ids=(SUPPORTER,)))

    assert len(paths) == 1
    assert paths[0].edges[0].capability == "recover"
    assert paths[0].edges[0].source_card_id == SUPPORTER


def test_generic_roles_fall_back_but_brief_roles_propagate_down_the_line():
    model = _model()
    roles = {row.card_id: row for row in infer_pokemon_roles(
        (LINE_BASE, LINE_TOP), model.registry, model.stats)}

    assert roles[LINE_TOP].role == "primary_attacker"
    assert roles[LINE_TOP].provenance == "brief"
    assert roles[LINE_BASE].role == "primary_attacker"


def test_visible_energy_creates_active_and_future_denial_needs():
    observation = _observation([])
    opponent = observation["current"]["players"][1]
    opponent["active"] = [{"id": 10, "energies": [3], "energyCards": [{"id": 3}]}]
    opponent["bench"] = [{"id": 11, "energies": [6], "energyCards": [{"id": 6}]}]

    roots = opponent_threat_roots(observation)

    assert [(root.predicate, root.deadline, root.outcome) for root in roots] == [
        ("deny:active:0:10:threat", 0, "prevent_prize"),
        ("deny:bench:0:11:threat", 1, "prevent_prize"),
    ]


def test_energy_denial_identifies_exact_retreat_and_energy_fuelled_ability_locks():
    observation = _observation([])
    opponent = observation["current"]["players"][1]
    opponent["active"] = [{"id": 10, "energies": [5], "energyCards": [{"id": 3}]}]
    stats = DictCardStatProvider({
        10: CardStat(10, hp=100, retreatCost=1, hasAbility=True, abilityEnergyTypes=(5,)),
    })

    roots = opponent_threat_roots(observation, stats)

    assert {root.outcome for root in roots} == {
        "prevent_prize", "prevent_retreat", "prevent_ability"}


def test_supporter_dig_builds_a_two_hop_path_only_while_supporter_is_available():
    base = _model()
    effects = CardEffects({
        GEAR: [{"kind": "fetch", "target": "supporter", "zone": "deck", "dig": 2}],
        SUPPORTER: [{"kind": "fetch", "target": "basic_energy", "zone": "deck"}],
    })
    stats = DictCardStatProvider({
        GEAR: CardStat(GEAR, cardType=1),
        SUPPORTER: CardStat(SUPPORTER, cardType=3),
        ENERGY: CardStat(ENERGY, cardType=5),
    })
    model = NeedModel(base.registry, _potential, effects=effects, stats=stats)
    builder = NeedBeamBuilder(model, CapabilityIndex.compile(
            (GEAR, SUPPORTER, SUPPORTER, ENERGY, ENERGY),
            stats=stats, effects=effects, functions={}))
    root = NeedRoot("fund", "attack_ready", 0, "take_prize", 1.0, "generic")
    need = Need("fund", ((ENERGY, 1.0),))

    def paths(supporter_played, *, hand=(), deck_counts=None):
        state = SimpleNamespace(
            root_seat=0,
            deck_counts=(deck_counts if deck_counts is not None else
                         ((GEAR, 1), (SUPPORTER, 2), (ENERGY, 2))),
            obs={"current": {"supporterPlayed": supporter_played,
                             "players": [{"hand": [{"id": card_id} for card_id in hand]}, {}]}},
        )
        return tuple(builder._access_paths(state, (root,), (need,)))

    two_hop = [path for path in paths(False) if len(path.edges) == 2]
    assert len(two_hop) == 1
    assert [edge.source_card_id for edge in two_hop[0].edges] == [GEAR, SUPPORTER]
    assert two_hop[0].probability == pytest.approx(0.7)
    direct_supporter = next(path for path in paths(False)
                            if path.edges[0].source_card_id == SUPPORTER)
    assert builder._path_score(two_hop[0], (root,)) > builder._path_score(
        direct_supporter, (root,))
    assert not [path for path in paths(True) if len(path.edges) == 2]
    assert not [path for path in paths(False, hand=(SUPPORTER,)) if len(path.edges) == 2]
    assert not paths(False, deck_counts=((GEAR, 1), (SUPPORTER, 2)))


def test_need_roots_consume_inferred_role_provenance():
    builder = NeedBeamBuilder(
        _model(), CapabilityIndex((), ()),
        roles=(PokemonRole(LINE_TOP, "primary_attacker", 0.9, "brief"),))

    root = builder._root(Need("evolve:active:0", ((LINE_TOP, 1.0),)))

    assert root.outcome == "establish_primary_attacker"
    assert root.confidence == 0.9
    assert root.provenance == "brief"


def test_absent_primary_attacker_deployment_is_a_current_need():
    builder = NeedBeamBuilder(
        _model(), CapabilityIndex((), ()),
        roles=(PokemonRole(LINE_BASE, "primary_attacker", 0.9, "brief"),))

    root = builder._root(Need("deploy:line:0", ((LINE_BASE, 1.0),)))

    assert root.outcome == "establish_primary_attacker"
    assert root.deadline == 0


def test_replay_gate_fails_closed_on_changes_unknowns_and_errors():
    result = {
        "shadow": {"unknown_actions": 1, "errors": 0},
        "focused": {"unknown_actions": 0, "errors": 1},
        "reuse_decision_changes": [{"frame": 1}],
        "decision_changes": [{"frame": 2}],
    }

    assert gate_failures(
        result, zero_focus=True, zero_reuse=True, zero_unknown=True, no_errors=True) == (
            "focused decision changes", "plan-reuse decision changes",
            "unknown actions", "mirror errors")


def test_energy_acceleration_and_ability_source_are_connected_generically():
    capabilities = CapabilityIndex(((ACCELERATOR, ("accel",)),), ())
    builder = NeedBeamBuilder(_model(), capabilities)
    root = NeedRoot("fund_attack", "fund_attack", 1, "take_prize", 1.0, "generic")
    paths = tuple(builder._acceleration_paths((root,)))
    state = SimpleNamespace(root_seat=0, obs={
        "current": {"players": [{"active": [{"id": ACCELERATOR}], "bench": []}, {}]},
        "select": {"option": [
            {"area": 2, "index": 7, "inPlayArea": 4, "inPlayIndex": 0}]},
    })
    action = LegalAction(ActionIdentity("ability"), (0,), ((0,),), ())

    assert paths[0].edges[0].source_card_id == ACCELERATOR
    assert builder._source_card_id(state, action) == ACCELERATOR

    state.obs["current"]["stadium"] = [{"id": ACCELERATOR}]
    state.obs["select"]["option"] = [{"area": 7, "index": 0}]
    assert builder._source_card_id(state, action) == ACCELERATOR


def test_named_stadium_fetch_forms_a_need_path_for_matching_deck_card():
    registry = ValueRegistry(facts={MARNIE_TARGET: CardFacts(pokemon=True, stage="basic")})
    stats = DictCardStatProvider({
        MARNIE_TARGET: CardStat(
            MARNIE_TARGET, name="Marnie's Scraggy", hp=70, stage="basic"),
    })
    effects = CardEffects({
        1259: [{"kind": "fetch", "target": "pokemon", "zone": "deck",
                "amount": 1, "name_family": "Marnie's"}],
    })
    model = NeedModel(registry, _potential, effects=effects, stats=stats)
    builder = NeedBeamBuilder(model, CapabilityIndex((), ()))
    need = Need("deploy:bench", ((MARNIE_TARGET, 1.0),))
    root = builder._root(need)
    state = SimpleNamespace(
        deck_counts=((MARNIE_TARGET, 1),), obs={"current": {"supporterPlayed": False}})

    paths = tuple(builder._access_paths(
        state, (root,), (need,), source_ids=(1259,)))

    assert len(paths) == 1
    assert paths[0].edges[0].source_card_id == 1259
