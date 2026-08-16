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


def test_opponent_hand_charge_shrinks_as_our_board_falls_behind():
    """ADR-0141 amendment: a player losing on board cannot afford to protect the leader's hand."""
    observation = _observation(opp_hand_count=4)
    even = _potential(opponent_hand_share=1.0)(observation)
    behind = _potential(opponent_hand_share=1.0, opponent_role_worth={DEFENDER: 30.0},
                        root_observation=observation)(observation)

    behind_families = dict(behind.families)
    parity = dict(even.families)["board"] / -behind_families["opponent_roles"]
    assert 0.0 < parity < 1.0                          # the fixture really is behind on board
    assert behind_families["opponent_hand"] == pytest.approx(
        dict(even.families)["opponent_hand"] * parity)


def test_opponent_hand_charge_stays_whole_at_board_parity_or_better():
    observation = _observation(opp_hand_count=4)
    even = _potential(opponent_hand_share=1.0)(observation)
    ahead = _potential(opponent_hand_share=1.0, opponent_role_worth={DEFENDER: 0.05},
                       root_observation=observation)(observation)

    assert dict(ahead.families)["opponent_hand"] == dict(even.families)["opponent_hand"]


def test_opponent_hand_charge_vanishes_with_nothing_of_our_own_in_play():
    observation = _observation(opp_hand_count=4)
    observation["current"]["players"][0]["active"] = []
    potential = BoardPotential(_stats(), registry=_registry(), root_seat=0,
                               opponent_hand_share=1.0,
                               opponent_role_worth={DEFENDER: 30.0},
                               root_observation=observation)

    assert dict(potential(observation).families)["opponent_hand"] == 0.0


def test_board_parity_holds_across_successors_of_the_position_it_was_read_from():
    """The read is of the root position: attacking must not move the opponent-hand charge."""
    root = _observation(opp_hand_count=4)
    potential = _potential(opponent_hand_share=1.0, opponent_role_worth={DEFENDER: 30.0},
                           root_observation=root)
    damaged = _observation(opp_hand_count=4)
    damaged["current"]["players"][1]["active"] = [_body(DEFENDER, hp=10)]

    assert (dict(potential(damaged).families)["opponent_hand"]
            == dict(potential(root).families)["opponent_hand"])


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


def test_poison_and_burn_on_the_opponent_active_are_pending_damage_progress():
    clean = _potential()(_observation())
    poisoned = _potential()(_observation(opp_conditions=("poisoned",)))
    burned = _potential()(_observation(opp_conditions=("burned",)))

    damage = lambda potential: dict(potential.families)["damage"]
    assert damage(poisoned) == damage(clean) + 10 / 200.0
    # Burn lands 2 counters unconditionally; the coin decides only the cure (docs/rules.md L161).
    assert damage(burned) == damage(clean) + 20 / 200.0


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


PAYAPA, SACRED_CHARM, THICK_SCALE = 1164, 1177, 1179


def _tool_forecast(tool_stat, *, attacker_stat=None, defender_stat=None):
    """Forecast value of a 60-damage hit into a 60 HP defender carrying ``tool_stat``."""
    stats = DictCardStatProvider(
        {ATTACKER: attacker_stat or CardStat(ATTACKER, name="Attacker", hp=120, attacks=(1,)),
         DEFENDER: defender_stat or CardStat(DEFENDER, name="Defender", hp=60),
         tool_stat.cardId: tool_stat},
        attacks={1: AttackStat(1, name="Hit", damage=60)},
    )
    potential = BoardPotential(stats, registry=_registry(), root_seat=0)
    attacker = _body(ATTACKER)
    defender = _body(DEFENDER, hp=60, max_hp=60)
    defender["tools"] = [{"id": tool_stat.cardId, "serial": 9}]
    me = {"active": [attacker], "bench": [], "hand": [], "discard": [], "prize": []}
    side = {"active": [defender], "bench": [], "hand": None, "discard": [], "prize": []}
    return potential._attack_value(
        attacker, [], defender, potential._side_facts(me), potential._side_facts(side))


def test_a_berry_tool_guards_only_against_its_printed_attacker_type():
    # Payapa Berry, gates per the CSV wording: 60 less, {P} (=5) attackers only.
    berry = CardStat(PAYAPA, name="Payapa Berry", damageReduction=60,
                     damageReductionTypes=(5,))
    psychic = CardStat(ATTACKER, name="Attacker", hp=120, attacks=(1,), energyType=5)
    water = CardStat(ATTACKER, name="Attacker", hp=120, attacks=(1,), energyType=3)

    assert _tool_forecast(berry, attacker_stat=psychic) == 0.0   # 60 - 60: fully absorbed
    assert _tool_forecast(berry, attacker_stat=water) == 1.0     # wrong type: a full KO


def test_sacred_charm_guards_only_against_ability_attackers():
    charm = CardStat(SACRED_CHARM, name="Sacred Charm", damageReduction=30,
                     damageReductionRequiresAbility=True)
    with_ability = CardStat(ATTACKER, name="Attacker", hp=120, attacks=(1,), hasAbility=True)
    plain = CardStat(ATTACKER, name="Attacker", hp=120, attacks=(1,))

    assert _tool_forecast(charm, attacker_stat=with_ability) == 0.5  # 30 absorbed
    assert _tool_forecast(charm, attacker_stat=plain) == 1.0         # no Ability: full KO


def test_thick_scale_guards_only_its_own_type_holder():
    # 50 less for a {N} (=9) holder against {G}{R}{W}{L} attackers; wrong holder = inert.
    scale = CardStat(THICK_SCALE, name="Thick Scale", damageReduction=50,
                     damageReductionTypes=(1, 2, 3, 4), damageReductionHolderTypes=(9,))
    water_attacker = CardStat(ATTACKER, name="Attacker", hp=120, attacks=(1,), energyType=3)
    dragon_holder = CardStat(DEFENDER, name="Defender", hp=60, energyType=9)
    water_holder = CardStat(DEFENDER, name="Defender", hp=60, energyType=3)

    guarded = _tool_forecast(scale, attacker_stat=water_attacker, defender_stat=dragon_holder)
    unguarded = _tool_forecast(scale, attacker_stat=water_attacker, defender_stat=water_holder)

    assert guarded == pytest.approx(10 / 60)          # 60 - 50 = 10 into 60 HP
    assert unguarded == 1.0                           # holder gate fails: full KO


def test_our_own_stadium_in_play_carries_its_board_worth():
    bare = _potential()(_observation())
    ours = _potential()(_observation(
        stadium=[{"id": STADIUM, "serial": 3, "playerIndex": 0}]))
    theirs = _potential()(_observation(
        stadium=[{"id": STADIUM, "serial": 3, "playerIndex": 1}]))

    board = lambda potential: dict(potential.families)["board"]
    assert board(ours) == board(bare) + worth_to_prizes(KNOWN_CARD_FLOOR)
    assert board(theirs) == board(bare)


def test_a_benched_tera_body_is_not_exposed_to_a_bench_attack():
    """Tera is a printed card fact, not deck doctrine: every deck must price it the same."""
    sniper, tera_body, plain = 800, 801, 802
    stats = DictCardStatProvider(
        {
            sniper: CardStat(sniper, name="Sniper", hp=100, attacks=(9,)),
            tera_body: CardStat(tera_body, name="Tera", hp=320, tera=True),
            plain: CardStat(plain, name="Plain", hp=320),
        },
        attacks={9: AttackStat(9, name="Snipe", damage=10, benchSnipe=100)},
    )
    registry = ValueRegistry(facts={
        sniper: CardFacts(pokemon=True),
        tera_body: CardFacts(pokemon=True, prize_value=2),
        plain: CardFacts(pokemon=True, prize_value=2),
    })
    potential = BoardPotential(stats, registry=registry, root_seat=0)
    attack = stats.attack(9)
    shielded = [_body(tera_body, hp=80, max_hp=320)]
    reachable = [_body(plain, hp=80, max_hp=320)]

    assert potential._bench_ko_indices(attack, shielded) == ()
    assert potential._bench_ko_indices(attack, reachable) == (0,)
    assert potential._bench_ko_prizes(attack, shielded) == 0.0
    assert potential._bench_ko_prizes(attack, reachable) > 0.0
