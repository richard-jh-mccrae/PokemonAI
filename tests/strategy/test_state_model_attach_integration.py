"""Issue #138 Phase 0b — every `_attach_value` input is available from the StateModel and agrees.

Buildability proof for the Phase-1a re-point, deliberately NOT a swap: 0b changes no decider (ADR-0068).
"""
import pytest

from card_facts import ignition_tags
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import (AttackStat, CardStat, DictCardStatProvider, _BASIC_ENERGY,
                                      _SPECIAL_ENERGY)
from common.state_model import StateModel
from common.strategy import Strategy
from common.strategy.context import _ATTACH, _BENCH, _HAND, _MAIN
from common.strategy.general_strategy import GENERAL_STRATEGY

MEGA, STARYU, WATER, IGNITION = 1031, 1030, 3, 17
NEBULA, JETTING = 210, 211
WATER_TYPE, COLORLESS = 3, 0


def _stats():
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                       minCostDamage=120, minAttackCost=1, maxDamageCost=3, evolvesFrom="Staryu",
                       energyType=WATER_TYPE, attacks=(JETTING, NEBULA)),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, maxDamage=20, minCostDamage=20,
                         minAttackCost=1, maxDamageCost=1, energyType=WATER_TYPE),
        WATER: CardStat(WATER, synthetic=True, name="Water", cardType=_BASIC_ENERGY, energyType=WATER_TYPE),
        IGNITION: CardStat(IGNITION, synthetic=True, name="Ignition", cardType=_SPECIAL_ENERGY, energyType=COLORLESS),
    }, attacks={
        JETTING: AttackStat(JETTING, damage=120, cost=1, energyTypes=(WATER_TYPE,)),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3,
                           energyTypes=(COLORLESS, COLORLESS, COLORLESS)),
    })


def _pilot():
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], STARYU: ["starter"]})
    return Pilot(strat, deck=[WATER] * 8 + [MEGA] * 3 + [STARYU] * 4 + [IGNITION],
                 general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=CardFunctions({IGNITION: ignition_tags()}))


def _obs(*, active, bench=(), hand=(), opp_active=None, turn=6):
    me = {"active": [active], "bench": list(bench), "hand": list(hand),
          "handCount": len(hand), "discard": [], "prize": [None] * 4, "deckCount": 20}
    opp = {"active": [opp_active], "bench": [], "hand": None, "handCount": 5,
           "discard": [], "prize": [None] * 6, "deckCount": 22}
    options = [{"type": _ATTACH, "area": _HAND, "index": 0, "inPlayArea": _BENCH, "inPlayIndex": 0}]
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": turn,
                        "energyAttached": False, "supporterPlayed": False, "stadium": []},
            "logs": [],
            "select": {"context": _MAIN, "minCount": 1, "maxCount": 1, "option": options}}


@pytest.fixture
def frame():
    pilot = _pilot()
    obs = _obs(active={"id": STARYU, "hp": 70, "energies": [], "serial": 1},
               bench=[{"id": MEGA, "hp": 330, "energies": [WATER, WATER], "serial": 2}],
               hand=[{"id": WATER}],
               opp_active={"id": STARYU, "hp": 70, "energies": [], "serial": 9})
    board = pilot._board(obs, obs["select"], carried=pilot.carried())
    model = StateModel.build(obs, combat=pilot.combat, deck=pilot.deck)
    return pilot, obs, board, model


def test_the_attach_equations_board_inputs_come_off_the_model(frame):
    _pilot_, _obs_, board, model = frame
    assert board.turn == model.mine.turn
    assert board.my_prizes_remaining == model.prize_race.my_prizes_remaining
    assert board.hand_basic_energy == model.mine.hand_energy_counts
    assert board.hand_ids == frozenset(model.mine.hand_ids)


def test_every_per_body_input_the_attach_equation_derives_is_on_the_model(frame):
    pilot, obs, _board, model = frame
    target = model.mine.bench[0]
    raw_target = obs["current"]["players"][0]["bench"][0]
    assert target.card_id == raw_target["id"]
    assert target.energy_count == len(raw_target["energies"] or [])
    assert target.is_active is False
    assert model.theirs.active.hp_remaining == 70
    assert model.theirs.active.prize_value == pilot._prize_value(
        obs["current"]["players"][1]["active"][0])


def test_the_model_supplies_the_typed_affordability_1a_replaces_the_plus_one_read_with(frame):
    """Per-slot TYPED reachability for ANY body, replacing the equation's Active-only, cheapest-only,
    +1 approximation."""
    _pilot_, _obs_, _board_, model = frame
    mega = model.mine.bench[0]
    assert model.mine.reachable_attach(mega, NEBULA) is True
    assert model.mine.reachable_attach(mega, JETTING) is True
    assert model.mine.readiness_p(mega, NEBULA) == 1.0
    assert model.mine.attach_budget(mega).size >= 1


def test_the_attach_equation_still_prices_the_option_unchanged(frame):
    pilot, obs, board, _model = frame
    row = pilot._attach_value(obs, obs["select"], board, obs["select"]["option"][0])
    assert row is not None
    assert set(row) >= {"marginal", "line_value", "resource_cost"}
    assert row["marginal"] >= 0.0


def test_the_integration_needs_no_carried_state_and_leaves_none_behind(frame):
    pilot, obs, _board_, _model_ = frame
    before = pilot.carried()
    StateModel.build(obs, combat=pilot.combat, deck=pilot.deck).mine.active_famine
    assert pilot.carried() == before
