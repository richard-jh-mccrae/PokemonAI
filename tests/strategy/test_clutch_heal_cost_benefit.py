import copy
import json
import sys
from pathlib import Path

import pytest

from common.strategy.context import KO_SCORE
from common.scouting.provider import AttackStat, CardStat


REPO = Path(__file__).resolve().parents[2]
WALLYS = 1229
_TYPED_MEGA = 9900
_WATER_ATTACK = 9901


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("mega_starmie")[0]


def _typed_attach_heal_lines(attach_hand_index):
    """The 0cbc survival frame with a one-attack `{W}` Mega and one Active attach choice."""
    obs = copy.deepcopy(_fixture("planner_0cbc")["obs"])
    pilot = _pilot()
    pilot.stats._cache[_TYPED_MEGA] = CardStat(
        _TYPED_MEGA, synthetic=True, name="Typed Mega", hp=330, megaEx=True,
        maxDamage=120, maxDamageCost=1, minAttackCost=1, minCostDamage=120,
        attacks=(_WATER_ATTACK,), evolvesFrom="Staryu", energyType=3)
    pilot.stats._attack_stats[_WATER_ATTACK] = AttackStat(
        _WATER_ATTACK, name="Water hit", damage=120, cost=1, energyTypes=(3,))

    me = obs["current"]["players"][obs["current"]["yourIndex"]]
    me["active"][0]["id"] = _TYPED_MEGA
    for option in obs["select"]["option"]:
        if option.get("type") == 13:
            option["attackId"] = _WATER_ATTACK
    obs["select"]["option"] = [
        option for option in obs["select"]["option"]
        if not (option.get("type") == 8 and option.get("inPlayArea") == 4
                and option.get("index") != attach_hand_index)
    ]
    decision = pilot.explain(obs)
    board = pilot._board(obs, obs["select"], carried=pilot.carried())
    return pilot, pilot._stabilize_then_ko_lines(
        obs, obs["select"], board, obs["select"]["option"], decision.options)


@pytest.mark.req("REQ-PLANNER-0036")
@pytest.mark.parametrize("fixture,wally_index,attach_id", [
    ("planner_0cbc", 5, 3),
    ("planner_6858", 3, 17),
])
def test_clutch_heal_prices_the_card_and_cheapest_ko_attach(
        fixture, wally_index, attach_id):
    fx = _fixture(fixture)
    pilot = _pilot()
    decision = pilot.explain(fx["obs"])

    assert decision.chosen == fx["correct"] == [wally_index]
    assert decision.planned.goal == "stabilize_then_ko"
    assert decision.planned.ranked_by == "cost-benefit"

    obs = fx["obs"]
    board = pilot._board(obs, obs["select"], carried=pilot.carried())
    opp = pilot._opp_active(obs)
    active_stat = pilot.stats.get(board.my_active_id)
    units = len(pilot.combat.provision_codes_or_floor(attach_id, active_stat))
    _, energy = pilot._heal_body_candidate(
        WALLYS, active_stat, is_active=True, cur_hp=board.my_active_hp,
        attached=board.my_active_energy, attach_units=units)
    prizes = pilot._prize_value(opp)
    ko_value = pilot._best_affordable_ko_value(
        obs, board, opp, board.my_active_id, energy)
    benefit = pilot._leaf_value(
        prizes=prizes, active_survives=True,
        threat_removed=pilot._threat_magnitude(opp))
    benefit += ko_value - (KO_SCORE + prizes)
    cost = pilot._role_value(WALLYS) + pilot._role_value(attach_id)
    assert cost > 0
    assert decision.planned.value == pytest.approx(benefit - cost)


@pytest.mark.req("REQ-PLANNER-0036")
@pytest.mark.parametrize("fixture,attach_id", [
    ("planner_0cbc", 3),
    ("planner_6858", 17),
])
def test_clutch_heal_attach_unlocks_a_ko_and_survives_the_honest_promoter(
        fixture, attach_id):
    obs = _fixture(fixture)["obs"]
    pilot = _pilot()
    board = pilot._board(obs, obs["select"], carried=pilot.carried())
    active_stat = pilot.stats.get(board.my_active_id)
    units = len(pilot.combat.provision_codes_or_floor(attach_id, active_stat))
    healed_hp, energy = pilot._heal_body_candidate(
        WALLYS, active_stat, is_active=True, cur_hp=board.my_active_hp,
        attached=board.my_active_energy, attach_units=units)
    opp_player = pilot._opp_player(obs)
    incoming = pilot._incoming_worst(board.my_active_id, healed_hp, opp_player.get("bench") or [])

    assert board.my_active_hp <= incoming < healed_hp
    assert pilot._best_affordable_ko_value(
        obs, board, pilot._opp_active(obs), board.my_active_id, energy) > 0


@pytest.mark.req("REQ-PLANNER-0036")
def test_clutch_heal_line_declines_without_a_post_heal_ko():
    fx = _fixture("planner_82227388_43")
    pilot = _pilot()
    decision = pilot.explain(fx["obs"])
    board = pilot._board(fx["obs"], fx["obs"]["select"], carried=pilot.carried())

    assert pilot._stabilize_then_ko_lines(
        fx["obs"], fx["obs"]["select"], board,
        fx["obs"]["select"]["option"], decision.options) == []


@pytest.mark.req("REQ-PLANNER-0036")
def test_clutch_heal_rejects_off_type_attach_after_energy_bounce():
    pilot, lines = _typed_attach_heal_lines(attach_hand_index=0)  # Ignition: three {C} units

    assert pilot.combat.provision_codes_or_floor(17, pilot.stats.get(_TYPED_MEGA)) == (0, 0, 0)
    assert lines == []


@pytest.mark.req("REQ-PLANNER-0036")
def test_clutch_heal_accepts_matching_typed_attach_after_energy_bounce():
    pilot, lines = _typed_attach_heal_lines(attach_hand_index=5)  # Basic {W}

    assert pilot.combat.provision_codes_or_floor(3, pilot.stats.get(_TYPED_MEGA)) == (3,)
    assert len(lines) == 1
    assert lines[0].goal == "stabilize_then_ko"
