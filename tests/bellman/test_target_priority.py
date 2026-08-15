from common import BoardPotential, CardFacts, ValueRegistry
from common.scouting.provider import AttackStat, CardStat
from copy import deepcopy


class _Stats:
    def get(self, card_id):
        return CardStat(cardId=card_id, hp=100, attacks=(10,))

    def attack(self, attack_id):
        return AttackStat(attackId=attack_id, energyTypes=(3, 3), damage=100)

    def forward_card_ids(self, card_id):
        return frozenset()


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
    registry = ValueRegistry(
        facts={3: CardFacts(), 13: CardFacts()},
        functions={13: ("provides_evo:3",)},
    )
    potential = BoardPotential(_Stats(), registry=registry, root_seat=0)
    before = _observation(_body(9), _body(2))
    active = before["current"]["players"][0]["active"][0]
    active.update({
        "preEvolution": [{"id": 8}], "energies": [3, 3, 3],
        "energyCards": [{"id": 13}],
    })
    after = deepcopy(before)
    after_active = after["current"]["players"][0]["active"][0]
    after_active["energies"].append(3)
    after_active["energyCards"].append({"id": 3})

    before_energy = dict(potential(before).families)["energy_position"]
    after_energy = dict(potential(after).families)["energy_position"]

    assert after_energy < before_energy


def test_snipe_progress_values_the_primary_attacker_above_the_backup():
    primary_hit = _observation(_body(1, hp=50), _body(2))
    backup_hit = _observation(_body(1), _body(2, hp=50))

    assert _potential()(primary_hit).total > _potential()(backup_hit).total


def test_energy_denial_values_the_primary_attacker_above_the_backup():
    primary_denied = _observation(_body(1, energy=False), _body(2))
    backup_denied = _observation(_body(1), _body(2, energy=False))

    assert _potential()(primary_denied).total > _potential()(backup_denied).total
