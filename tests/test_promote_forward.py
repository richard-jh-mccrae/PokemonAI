"""Promote with forward search (the b7e483a promote blunders).

`promote-the-accelerator-for-the-ko`: bring up an accelerator that can KO the Active (it takes the
prize AND loads the benched win-condition) over the win-condition itself. `promote-the-staller` +
the `evolve_to_ready_wincon_available` gate: don't promote a BARE pre-evolution to evolve a dead
0-Energy wincon — promote the staller instead.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

TO_ACTIVE = 4
MEGA, STARYU, CINDERACE = 1031, 1030, 666


def _fired(t):
    return {h.id for h, _ in t.fired}


def _pilot(hand_ids=()):
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, minAttackCost=1,
                       minCostDamage=120, maxDamageCost=3, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, minCostDamage=20),
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, minAttackCost=1, minCostDamage=50),
        678: CardStat(678, name="Mega Lucario ex", hp=340, megaEx=True),
    })
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"],
                            CINDERACE: ["accel_source", "starter"], STARYU: ["starter"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({CINDERACE: ["opener"]}), attacks={}, attack_costs={})


def _obs(bench, opp_active, hand=()):
    me = {"active": [None], "bench": bench, "hand": [{"id": c} for c in hand]}
    opp = {"active": [opp_active], "bench": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 8},
            "select": {"context": TO_ACTIVE, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 3, "area": 5, "index": i, "playerIndex": 0}
                                  for i in range(len(bench))]}}


@pytest.mark.req("REQ-GEN-0026")
def test_promote_the_accelerator_that_kos_over_the_wincon():
    # Opp Active = a 20-HP Mega Lucario ex. Both Cinderace (50) and the benched Mega (120) KO it; promote
    # CINDERACE — it takes the prize AND its Turbo Flare loads the Mega for next turn.
    p = _pilot()
    bench = [{"id": CINDERACE, "energies": [3], "hp": 160},      # idx0: accelerator, can KO
             {"id": MEGA, "energies": [3], "hp": 330}]           # idx1: ready wincon, can KO
    obs = _obs(bench, {"id": 678, "hp": 20, "energies": [1, 1, 1]})
    dec = p.explain(obs)
    assert "promote-the-accelerator-for-the-ko" in _fired(dec.options[0])
    assert "promote-the-ready-wincon" in _fired(dec.options[1])
    assert p.decide(obs) == [0]                                  # the accelerator, not the wincon


@pytest.mark.req("REQ-GEN-0026")
def test_promote_the_staller_over_a_bare_preevo_even_with_the_payoff_in_hand():
    # Mega in hand, but the only benched pre-evolution (Staryu) is BARE — evolving it exposes a dead
    # 0-Energy Mega. Promote Cinderace (a staller that can act) instead.
    p = _pilot(hand_ids=[MEGA])
    bench = [{"id": CINDERACE, "energies": [1], "hp": 160},      # idx0: staller, 1 Energy
             {"id": STARYU, "energies": [], "hp": 70}]           # idx1: bare pre-evolution
    obs = _obs(bench, {"id": 678, "hp": 140, "energies": [1]}, hand=[MEGA])
    assert not p._board(obs, obs["select"]).evolve_to_ready_wincon_available
    dec = p.explain(obs)
    assert "promote-the-staller" in _fired(dec.options[0])
    assert "prefer-wincon-line-piece" not in _fired(dec.options[1])   # bare pre-evo: stands down
    assert p.decide(obs) == [0]                                  # the staller, not the bare Staryu
