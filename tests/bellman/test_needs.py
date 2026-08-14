from __future__ import annotations

from types import SimpleNamespace

import pytest

from common import ActionIdentity
from common.effects import CardEffects
from common.needs import (
    AccessEdge, CapabilityIndex, Need, NeedBeam, NeedBeamBuilder, NeedModel, NeedPath, NeedRoot,
    PathFeatures, PokemonRole, access_probability, best_assignment, infer_pokemon_roles,
    opponent_threat_roots,
)
from common.scouting.provider import CardStat, DictCardStatProvider
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

    assert useful.value == pytest.approx(0.6)
    assert useful.options[0].description.startswith("evolve:")
    assert unrelated.value == 0.0


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
        ("deny_threat:active:0", 0, "prevent_prize"),
        ("deny_threat:bench:0", 1, "prevent_prize"),
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
