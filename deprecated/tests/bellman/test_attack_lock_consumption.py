"""Every family that reads a printed attack must first ask whether that attack is barred.

`common/attack_locks.py` reconstructs the board state the observation omits: an attack whose text
reads "During your next turn this Pokemon can't use <attack>" is enforced by the engine, which
simply drops it from the menu, and publishes no marker anywhere else. A family that enumerates
`CardStat.attacks` directly therefore keeps pricing a spent one-shot as reachable — on OUR side it
buys a knockout the agent cannot make, on the OPPONENT's side it fears a hit they cannot land.
"""
from __future__ import annotations

from deprecated.bellman import BoardPotential, CardFacts, ValueRegistry
from common.cards.card_facts import Attack, BASIC, Clause, PokemonCard


ATTACKER, DEFENDER, SIDEKICK = 800, 801, 802
BIG, SMALL, OPPONENT_BIG = 1, 2, 3


def _stats():
    # One shot that knocks out the Active and snipes the Bench, then bars itself.
    big = Attack(BIG, "Overreach", (), 200,
                 clauses=(Clause("bench_snipe", amount=60), Clause("same_attack_lock")))
    small = Attack(SMALL, "Jab", (), 10)
    their_big = Attack(OPPONENT_BIG, "Their Overreach", (), 200,
                       clauses=(Clause("same_attack_lock"),))
    return {
        ATTACKER: PokemonCard(ATTACKER, "Attacker", 200, 0, BASIC, attacks=(big, small)),
        DEFENDER: PokemonCard(DEFENDER, "Defender", 120, 0, BASIC, attacks=(their_big,)),
        SIDEKICK: PokemonCard(SIDEKICK, "Sidekick", 60, 0, BASIC),
    }


def _registry():
    return ValueRegistry(facts={
        ATTACKER: CardFacts(pokemon=True), DEFENDER: CardFacts(pokemon=True),
        SIDEKICK: CardFacts(pokemon=True),
    })


def _body(card_id, hp):
    return {"id": card_id, "serial": card_id, "hp": hp, "maxHp": hp,
            "energies": [], "energyCards": [], "tools": [], "preEvolution": []}


def _observation(*, locks=None):
    me = {"active": [_body(ATTACKER, 200)], "bench": [], "hand": [], "discard": [],
          "prize": [None] * 6, "handCount": 0}
    opponent = {"active": [_body(DEFENDER, 120)], "bench": [_body(SIDEKICK, 60)],
                "hand": None, "handCount": 4, "discard": [], "prize": [None] * 6}
    observation = {"current": {"yourIndex": 0, "turn": 8, "players": [me, opponent],
                               "stadium": []}}
    if locks:
        observation["attack_locks"] = locks
    return observation


def _families(**kwargs):
    potential = BoardPotential(_stats(), registry=_registry(), root_seat=0)
    return dict(potential(_observation(**kwargs)).families)


def test_a_barred_attack_stops_buying_a_two_prize_line():
    """`_multi_target_ko_ready` prices a ready attack that knocks out Active and Bench together."""
    free = _families()
    barred = _families(locks={str(ATTACKER): {str(BIG): 9}})

    assert free["multi_target_ko"] > 0.0
    assert barred["multi_target_ko"] == 0.0


def test_a_barred_attack_still_leaves_the_body_its_other_attacks():
    barred_big = _families(locks={str(ATTACKER): {str(BIG): 9}})
    barred_both = _families(locks={str(ATTACKER): {str(BIG): 9, str(SMALL): 9}})

    assert barred_big["readiness"] > barred_both["readiness"]


def test_the_opponents_own_lock_lowers_the_threat_we_price():
    """`_lethal_exposure` reads THEIR printed attacks. A spent one-shot cannot hit us next turn."""
    feared = _families()
    spent = _families(locks={str(DEFENDER): {str(OPPONENT_BIG): 9}})

    assert spent["game"] > feared["game"]


def test_an_expired_lock_restores_every_family():
    """A lock stamped for a turn already behind us bars nothing."""
    free = _families()
    expired = _families(locks={str(ATTACKER): {str(BIG): 7},
                               str(DEFENDER): {str(OPPONENT_BIG): 7}})

    assert expired == free
