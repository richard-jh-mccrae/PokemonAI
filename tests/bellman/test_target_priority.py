from common import BoardPotential, CardFacts, ValueRegistry
from common.scouting.provider import AttackStat, CardStat


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


def _potential():
    registry = ValueRegistry(facts={card_id: CardFacts(pokemon=True)
                                    for card_id in (1, 2, 3, 9)})
    return BoardPotential(
        _Stats(), registry=registry, opponent_role_worth={1: 30.0, 2: 20.0}, root_seat=0)


def test_snipe_progress_values_the_primary_attacker_above_the_backup():
    primary_hit = _observation(_body(1, hp=50), _body(2))
    backup_hit = _observation(_body(1), _body(2, hp=50))

    assert _potential()(primary_hit).total > _potential()(backup_hit).total


def test_energy_denial_values_the_primary_attacker_above_the_backup():
    primary_denied = _observation(_body(1, energy=False), _body(2))
    backup_denied = _observation(_body(1), _body(2, energy=False))

    assert _potential()(primary_denied).total > _potential()(backup_denied).total
