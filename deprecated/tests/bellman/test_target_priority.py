from deprecated.bellman import BoardPotential, CardFacts, ValueRegistry
from common.cards.card_facts import (
    Attack, BASIC, BASIC_ENERGY, EnergyCard, PokemonCard, STAGE1,
)
from copy import deepcopy


class _Stats(dict):
    """Explicit rows win; any other id resolves to a 100 HP Basic with one (3, 3)-cost
    100-damage attack."""

    def get(self, card_id, default=None):
        found = super().get(int(card_id))
        if found is not None:
            return found
        return PokemonCard(int(card_id), f"Test Pokemon {card_id}", 100, 0, BASIC,
                           attacks=(Attack(10, "Hit", (3, 3), 100),))


def _body(card_id, *, hp=100, energy=True):
    cards = [{"id": 3}] if energy else []
    return {
        "id": card_id, "hp": hp, "maxHp": 100,
        "energies": [3] if energy else [], "energyCards": cards,
    }


def _observation(primary, backup):
    return {
        "current": {
            "yourIndex": 0, "result": -1,
            "players": [
                {"active": [_body(9)], "bench": [], "hand": [], "prize": [None] * 6},
                {"active": [], "bench": [primary, backup], "hand": None,
                 "handCount": 4, "prize": [None] * 6},
            ],
        },
        "select": {"context": 0},
    }


def _potential(*, isolated_selection=False):
    registry = ValueRegistry(facts={card_id: CardFacts(pokemon=True)
                                    for card_id in (1, 2, 3, 9)})
    return BoardPotential(
        _Stats(), registry=registry, opponent_role_worth={1: 30.0, 2: 20.0}, root_seat=0,
        isolated_selection=isolated_selection)


def test_energy_position_includes_basic_attackers_during_isolated_selections():
    observation = _observation(_body(1), _body(2))

    families = dict(_potential(isolated_selection=True)(observation).families)

    assert families["energy_position"] > 0.0


def test_full_health_active_is_funded_before_backup_energy_is_valued():
    before = _observation(_body(1), _body(2))
    before["current"]["players"][0]["bench"] = [_body(9, energy=False)]
    active_attach = deepcopy(before)
    active_attach["current"]["players"][0]["active"][0] = _body(9)
    active_attach["current"]["players"][0]["active"][0]["energies"].append(3)
    active_attach["current"]["players"][0]["active"][0]["energyCards"].append({"id": 3})
    bench_attach = deepcopy(before)
    bench_attach["current"]["players"][0]["bench"][0] = _body(9)

    potential = _potential()
    baseline = dict(potential(before).families)["energy_position"]
    active_value = dict(potential(active_attach).families)["energy_position"]
    bench_value = dict(potential(bench_attach).families)["energy_position"]

    assert active_value > baseline
    assert bench_value < baseline


def test_multi_unit_energy_saturates_attack_without_valuing_a_fourth_unit():
    # 17 = Ignition Energy, the real provides_evo:3 record; provision now reads the record.
    from common.cards import card_store
    registry = ValueRegistry(facts={3: CardFacts(), 17: CardFacts()})
    potential = BoardPotential(_Stats({17: card_store()[17]}), registry=registry, root_seat=0)
    before = _observation(_body(9), _body(2))
    active = before["current"]["players"][0]["active"][0]
    active.update({
        "preEvolution": [{"id": 8}], "energies": [3, 3, 3],
        "energyCards": [{"id": 17}],
    })
    after = deepcopy(before)
    after_active = after["current"]["players"][0]["active"][0]
    after_active["energies"].append(3)
    after_active["energyCards"].append({"id": 3})

    before_energy = dict(potential(before).families)["energy_position"]
    after_energy = dict(potential(after).families)["energy_position"]

    assert after_energy < before_energy


def test_hand_value_requires_a_recipient_for_evolution_but_retains_future_energy():
    base, top, energy = 20, 21, 22
    hit = Attack(10, "Hit", (3,), 100)
    stats = {
        base: PokemonCard(base, "Base", 60, 0, BASIC, attacks=(hit,)),
        top: PokemonCard(top, "Top", 120, 0, STAGE1, evolves_from="Base", attacks=(hit,)),
        energy: EnergyCard(energy, "Test Water", BASIC_ENERGY, provides=3),
    }
    registry = ValueRegistry(
        roles={base: ("primary_attacker",), top: ("primary_attacker",)},
        facts={base: CardFacts(pokemon=True, stage="basic"),
               top: CardFacts(pokemon=True, stage="stage1"),
               energy: CardFacts(typed_basic_energy=True)},
        lines=((base, top),), line_pairs=((base, top),))
    potential = BoardPotential(stats, registry=registry, root_seat=0)
    player = {"active": [_body(base)], "bench": [],
              "hand": [{"id": top}, {"id": energy}], "prize": [None] * 6}
    player["active"][0]["energies"] = [3]
    player["active"][0]["energyCards"] = [{"id": energy}]

    assert potential._held_card_usable(player, top) is True
    assert potential._held_card_usable(player, energy) is False
    isolated = BoardPotential(stats, registry=registry, root_seat=0, isolated_selection=True)
    assert isolated._held_card_usable(player, energy) is True
    player["active"] = [_body(9)]
    assert potential._held_card_usable(player, top) is False


def test_snipe_progress_values_the_primary_attacker_above_the_backup():
    primary_hit = _observation(_body(1, hp=50), _body(2))
    backup_hit = _observation(_body(1), _body(2, hp=50))

    assert _potential()(primary_hit).total > _potential()(backup_hit).total


def test_energy_denial_values_the_primary_attacker_above_the_backup():
    primary_denied = _observation(_body(1, energy=False), _body(2))
    backup_denied = _observation(_body(1), _body(2, energy=False))

    assert _potential()(primary_denied).total > _potential()(backup_denied).total
