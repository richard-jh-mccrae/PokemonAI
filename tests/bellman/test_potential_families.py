"""Phase-2 families: opponent hand pressure, special conditions, and stadium board worth."""
from __future__ import annotations

import pytest

from common import BoardPotential, CardFacts, ValueRegistry
from common.card_worth import KNOWN_CARD_FLOOR
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.value import worth_to_prizes


ATTACKER, DEFENDER, STADIUM = 700, 701, 1260


def _stats():
    return DictCardStatProvider(
        {
            ATTACKER: CardStat(ATTACKER, name="Attacker", hp=120, attacks=(1,)),
            DEFENDER: CardStat(DEFENDER, name="Defender", hp=120, attacks=(1,)),
            STADIUM: CardStat(STADIUM, name="Stadium"),
        },
        attacks={1: AttackStat(1, name="Hit", damage=60)},
    )


def _registry():
    return ValueRegistry(facts={
        ATTACKER: CardFacts(pokemon=True), DEFENDER: CardFacts(pokemon=True),
        STADIUM: CardFacts(),
    })


def _body(card_id, hp=120, max_hp=120, energies=()):
    return {"id": card_id, "serial": card_id, "hp": hp, "maxHp": max_hp,
            "energies": list(energies), "energyCards": [], "tools": [], "preEvolution": []}


def _observation(*, me_conditions=(), opp_conditions=(), opp_hand_count=4, stadium=()):
    me = {"active": [_body(ATTACKER)], "bench": [], "hand": [], "discard": [],
          "prize": [None] * 6, "handCount": 0}
    opponent = {"active": [_body(DEFENDER)], "bench": [], "hand": None,
                "handCount": opp_hand_count, "discard": [], "prize": [None] * 6}
    for name in ("poisoned", "burned", "asleep", "paralyzed", "confused"):
        me[name] = name in me_conditions
        opponent[name] = name in opp_conditions
    return {"current": {"yourIndex": 0, "turn": 2, "players": [me, opponent],
                        "stadium": list(stadium)}}


def _potential(**kwargs):
    return BoardPotential(_stats(), registry=_registry(), root_seat=0, **kwargs)


def test_opponent_hand_size_is_a_priced_liability_when_armed():
    small = _potential(opponent_hand_share=1.0)(_observation(opp_hand_count=2))
    large = _potential(opponent_hand_share=1.0)(_observation(opp_hand_count=8))

    families_small = dict(small.families)
    families_large = dict(large.families)
    assert families_small["opponent_hand"] > families_large["opponent_hand"]
    assert families_small["opponent_hand"] == -2 * worth_to_prizes(KNOWN_CARD_FLOOR)
    assert small.total - large.total == pytest.approx(6 * worth_to_prizes(KNOWN_CARD_FLOOR))


def test_opponent_hand_pricing_ships_dark_by_default():
    families = dict(_potential()(_observation(opp_hand_count=8)).families)

    assert "opponent_hand" in families                 # the family exists, at zero share
    assert families["opponent_hand"] == 0.0


def test_a_paralyzed_opponent_active_is_not_a_live_incoming_threat():
    threatened = _potential()(_observation())
    safe = _potential()(_observation(opp_conditions=("paralyzed",)))

    assert dict(safe.families)["readiness"] > dict(threatened.families)["readiness"]


def test_a_sleeping_opponent_active_is_a_discounted_incoming_threat():
    threatened = _potential()(_observation())
    drowsy = _potential()(_observation(opp_conditions=("asleep",)))
    safe = _potential()(_observation(opp_conditions=("paralyzed",)))

    readiness = lambda potential: dict(potential.families)["readiness"]
    assert readiness(threatened) < readiness(drowsy) < readiness(safe)


def test_our_own_sleeping_active_discounts_our_forecast_readiness():
    awake = _potential()(_observation())
    asleep = _potential()(_observation(me_conditions=("asleep",)))

    assert dict(asleep.families)["readiness"] < dict(awake.families)["readiness"]


def test_poison_on_the_opponent_active_is_pending_damage_progress():
    clean = _potential()(_observation())
    poisoned = _potential()(_observation(opp_conditions=("poisoned",)))

    assert dict(poisoned.families)["damage"] > dict(clean.families)["damage"]


def test_a_spread_attack_reaches_the_bench_in_forecasts():
    # benchSpread counters can all land on one benched target, so forecast reach is
    # max(benchSnipe, benchSpread) — not snipe-only with spread read as zero.
    stats = DictCardStatProvider(
        {ATTACKER: CardStat(ATTACKER, name="Spreader", hp=120, attacks=(2,)),
         DEFENDER: CardStat(DEFENDER, name="Bench", hp=60)},
        attacks={2: AttackStat(2, name="Spread", damage=0, benchSpread=60)},
    )
    potential = BoardPotential(stats, registry=_registry(), root_seat=0)
    attacker = _body(ATTACKER)
    bench_defender = _body(DEFENDER, hp=60, max_hp=60)

    value = potential._attack_value(
        attacker, [], bench_defender,
        potential._side_facts({"active": [attacker], "bench": [], "hand": [],
                               "discard": [], "prize": []}),
        potential._side_facts({"active": [bench_defender], "bench": [], "hand": None,
                               "discard": [], "prize": []}))

    assert value == 1.0                               # a full KO reach, not zero


def test_a_defenders_tool_reduction_caps_the_forecast_ko():
    tool = 1174
    stats = DictCardStatProvider(
        {ATTACKER: CardStat(ATTACKER, name="Attacker", hp=120, attacks=(1,)),
         DEFENDER: CardStat(DEFENDER, name="Defender", hp=60),
         tool: CardStat(tool, name="Guard", damageReduction=30)},
        attacks={1: AttackStat(1, name="Hit", damage=60)},
    )
    potential = BoardPotential(stats, registry=_registry(), root_seat=0)
    attacker = _body(ATTACKER)
    bare = _body(DEFENDER, hp=60, max_hp=60)
    guarded = _body(DEFENDER, hp=60, max_hp=60)
    guarded["tools"] = [{"id": tool, "serial": 9}]
    me = {"active": [attacker], "bench": [], "hand": [], "discard": [], "prize": []}

    def value(defender):
        side = {"active": [defender], "bench": [], "hand": None, "discard": [], "prize": []}
        return potential._attack_value(
            attacker, [], defender, potential._side_facts(me), potential._side_facts(side))

    assert value(bare) == 1.0                         # 60 into 60: a forecast KO
    assert value(guarded) == 0.5                      # the attached tool absorbs 30


def test_our_own_stadium_in_play_carries_its_board_worth():
    bare = _potential()(_observation())
    ours = _potential()(_observation(
        stadium=[{"id": STADIUM, "serial": 3, "playerIndex": 0}]))
    theirs = _potential()(_observation(
        stadium=[{"id": STADIUM, "serial": 3, "playerIndex": 1}]))

    board = lambda potential: dict(potential.families)["board"]
    assert board(ours) == board(bare) + worth_to_prizes(KNOWN_CARD_FLOOR)
    assert board(theirs) == board(bare)
