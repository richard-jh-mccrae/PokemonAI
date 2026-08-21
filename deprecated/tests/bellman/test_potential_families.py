"""Phase-2 families: opponent hand pressure, special conditions, and stadium board worth."""
from __future__ import annotations

import pytest

from deprecated.bellman import BoardPotential, CardFacts, ValueRegistry
from common.card_worth import KNOWN_CARD_FLOOR
from common.cards.card_facts import (
    Attack, BASIC, Clause, PokemonCard, STADIUM as STADIUM_KIND, TrainerCard,
)
from deprecated.bellman.value import worth_to_prizes


ATTACKER, DEFENDER, STADIUM = 700, 701, 1260


def _stats():
    hit = Attack(1, "Hit", (), 60)
    return {
        ATTACKER: PokemonCard(ATTACKER, "Attacker", 120, 0, BASIC, attacks=(hit,)),
        DEFENDER: PokemonCard(DEFENDER, "Defender", 120, 0, BASIC, attacks=(hit,)),
        STADIUM: TrainerCard(STADIUM, "Stadium", STADIUM_KIND),
    }


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
    # bench_spread counters can all land on one benched target, so forecast reach is
    # max(bench_snipe, bench_spread) — not snipe-only with spread read as zero.
    spread = Attack(2, "Spread", (), 0, clauses=(Clause("bench_spread", amount=60),))
    cards = {ATTACKER: PokemonCard(ATTACKER, "Spreader", 120, 0, BASIC, attacks=(spread,)),
             DEFENDER: PokemonCard(DEFENDER, "Bench", 60, 0, BASIC)}
    potential = BoardPotential(cards, registry=_registry(), root_seat=0)
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


_HIT = Attack(1, "Hit", (), 60)


def _tool_forecast(tool, *, attacker=None, defender=None):
    """Forecast value of a 60-damage hit into a 60 HP defender carrying ``tool``."""
    cards = {ATTACKER: attacker or PokemonCard(ATTACKER, "Attacker", 120, 0, BASIC,
                                               attacks=(_HIT,)),
             DEFENDER: defender or PokemonCard(DEFENDER, "Defender", 60, 0, BASIC),
             tool.card_id: tool}
    potential = BoardPotential(cards, registry=_registry(), root_seat=0)
    attacker_body = _body(ATTACKER)
    defender_body = _body(DEFENDER, hp=60, max_hp=60)
    defender_body["tools"] = [{"id": tool.card_id, "serial": 9}]
    me = {"active": [attacker_body], "bench": [], "hand": [], "discard": [], "prize": []}
    side = {"active": [defender_body], "bench": [], "hand": None, "discard": [], "prize": []}
    return potential._attack_value(
        attacker_body, [], defender_body,
        potential._side_facts(me), potential._side_facts(side))


def _tool(card_id, name, **params):
    from common.cards.card_facts import TOOL
    return TrainerCard(card_id, name, TOOL,
                       clauses=(Clause("damage_reduction", **params),))


def test_a_berry_tool_guards_only_against_its_printed_attacker_type():
    # Payapa Berry, gates per the CSV wording: 60 less, {P} (=5) attackers only.
    berry = _tool(PAYAPA, "Payapa Berry", amount=60, attacker_types=(5,))
    psychic = PokemonCard(ATTACKER, "Attacker", 120, 5, BASIC, attacks=(_HIT,))
    water = PokemonCard(ATTACKER, "Attacker", 120, 3, BASIC, attacks=(_HIT,))

    assert _tool_forecast(berry, attacker=psychic) == 0.0   # 60 - 60: fully absorbed
    assert _tool_forecast(berry, attacker=water) == 1.0     # wrong type: a full KO


def test_sacred_charm_guards_only_against_ability_attackers():
    from common.cards.card_facts import Ability
    charm = _tool(SACRED_CHARM, "Sacred Charm", amount=30, requires_ability=True)
    with_ability = PokemonCard(ATTACKER, "Attacker", 120, 0, BASIC, attacks=(_HIT,),
                               abilities=(Ability("Test Ability"),))
    plain = PokemonCard(ATTACKER, "Attacker", 120, 0, BASIC, attacks=(_HIT,))

    assert _tool_forecast(charm, attacker=with_ability) == 0.5  # 30 absorbed
    assert _tool_forecast(charm, attacker=plain) == 1.0         # no Ability: full KO


def test_thick_scale_guards_only_its_own_type_holder():
    # 50 less for a {N} (=9) holder against {G}{R}{W}{L} attackers; wrong holder = inert.
    scale = _tool(THICK_SCALE, "Thick Scale", amount=50,
                  attacker_types=(1, 2, 3, 4), holder_types=(9,))
    water_attacker = PokemonCard(ATTACKER, "Attacker", 120, 3, BASIC, attacks=(_HIT,))
    dragon_holder = PokemonCard(DEFENDER, "Defender", 60, 9, BASIC)
    water_holder = PokemonCard(DEFENDER, "Defender", 60, 3, BASIC)

    guarded = _tool_forecast(scale, attacker=water_attacker, defender=dragon_holder)
    unguarded = _tool_forecast(scale, attacker=water_attacker, defender=water_holder)

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
    snipe = Attack(9, "Snipe", (), 10, clauses=(Clause("bench_snipe", amount=100),))
    cards = {
        sniper: PokemonCard(sniper, "Sniper", 100, 0, BASIC, attacks=(snipe,)),
        tera_body: PokemonCard(tera_body, "Tera", 320, 0, BASIC, tera=True, ex=True),
        plain: PokemonCard(plain, "Plain", 320, 0, BASIC, ex=True),
    }
    registry = ValueRegistry(facts={
        sniper: CardFacts(pokemon=True),
        tera_body: CardFacts(pokemon=True, prize_value=2),
        plain: CardFacts(pokemon=True, prize_value=2),
    })
    potential = BoardPotential(cards, registry=registry, root_seat=0)
    attack = snipe
    shielded = [_body(tera_body, hp=80, max_hp=320)]
    reachable = [_body(plain, hp=80, max_hp=320)]

    assert potential._bench_ko_indices(attack, shielded) == ()
    assert potential._bench_ko_indices(attack, reachable) == (0,)
    assert potential._bench_ko_prizes(attack, shielded) == 0.0
    assert potential._bench_ko_prizes(attack, reachable) > 0.0
