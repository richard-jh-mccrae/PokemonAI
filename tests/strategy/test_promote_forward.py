"""Promote with forward search (the b7e483a promote blunders).

`promote-the-accelerator-for-the-ko`: bring up an accelerator that can KO the Active (it takes the
prize AND loads the benched win-condition) over the win-condition itself. `promote-the-staller` +
the `evolve_to_ready_wincon_available` gate: don't promote a BARE pre-evolution to evolve a dead
0-Energy wincon — promote the staller instead.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

TO_ACTIVE = 4
SWITCH = 3
MEGA, STARYU, CINDERACE = 1031, 1030, 666


def _fired(t):
    return {h.id for h, _ in t.fired}


def _pilot(hand_ids=()):
    # Every attacker's cheapest attack is a real record (the card-level minCostDamage KO
    # fallback is retired, ADR-0052) — same damage/cost the fallback used to read.
    A_MEGA, A_STAR, A_CIND = 31, 32, 33
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, minAttackCost=1,
                       minCostDamage=120, maxDamageCost=3, evolvesFrom="Staryu",
                       attacks=(A_MEGA,)),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, minCostDamage=20,
                         attacks=(A_STAR,)),
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, minAttackCost=1, minCostDamage=50,
                            attacks=(A_CIND,)),
        678: CardStat(678, name="Mega Lucario ex", hp=340, megaEx=True),
    }, attacks={A_MEGA: AttackStat(A_MEGA, damage=120, cost=1),
                A_STAR: AttackStat(A_STAR, damage=20, cost=1),
                A_CIND: AttackStat(A_CIND, damage=50, cost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"],
                            CINDERACE: ["accel_source", "starter"], STARYU: ["starter"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({CINDERACE: ["opener"]}))


def _obs(bench, opp_active, hand=(), ctx=TO_ACTIVE, active=None):
    me = {"active": [active], "bench": bench, "hand": [{"id": c} for c in hand]}
    opp = {"active": [opp_active], "bench": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 8},
            "select": {"context": ctx, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 3, "area": 5, "index": i, "playerIndex": 0}
                                  for i in range(len(bench))]}}


@pytest.mark.req("REQ-GEN-0026")
def test_promote_the_accelerator_that_kos_over_the_wincon():
    # Opp Active = 20-HP Mega Lucario ex. Both Cinderace (50) and benched Mega (120) KO it; promote
    # CINDERACE — takes the prize AND its Turbo Flare loads the Mega for next turn.
    p = _pilot()
    bench = [{"id": CINDERACE, "energies": [3], "hp": 160},      # idx0: accelerator, can KO
             {"id": MEGA, "energies": [3], "hp": 330}]           # idx1: ready wincon, can KO
    obs = _obs(bench, {"id": 678, "hp": 20, "energies": [1, 1, 1]})
    dec = p.explain(obs)
    assert "promote-the-accelerator-for-the-ko" in _fired(dec.options[0])
    assert "promote-the-ready-wincon" in _fired(dec.options[1])
    assert p.decide(obs) == [0]                                  # accelerator, not the wincon


@pytest.mark.req("REQ-GEN-0026")
def test_promote_the_staller_over_a_bare_preevo_even_with_the_payoff_in_hand():
    # Mega in hand, but only benched pre-evolution (Staryu) is BARE — evolving it exposes a dead
    # 0-Energy Mega. Promote Cinderace (staller that can act) instead.
    p = _pilot(hand_ids=[MEGA])
    bench = [{"id": CINDERACE, "energies": [1], "hp": 160},      # idx0: staller, 1 Energy
             {"id": STARYU, "energies": [], "hp": 70}]           # idx1: bare pre-evolution
    obs = _obs(bench, {"id": 678, "hp": 140, "energies": [1]}, hand=[MEGA])
    assert not p._board(obs, obs["select"]).evolve_to_ready_wincon_available
    dec = p.explain(obs)
    assert "promote-the-staller" in _fired(dec.options[0])
    assert "prefer-wincon-line-piece" not in _fired(dec.options[1])   # bare pre-evo: stands down
    assert p.decide(obs) == [0]                                  # staller, not the bare Staryu


@pytest.mark.req("REQ-GEN-0025")
def test_best_promote_slot_picks_the_most_built_ready_wincon():
    # Three Mega Starmie ex on the Bench: bare (0), online (1 Energy), most-built (3 Energy). Best
    # body to promote is the 3-Energy one — closest to its payoff hit (ep83007714 f104).
    p = _pilot()
    bench = [{"id": MEGA, "energies": [], "hp": 330},            # idx0: bare, not ready
             {"id": MEGA, "energies": [3, 3, 3], "hp": 430},     # idx1: most-built ready wincon
             {"id": MEGA, "energies": [3], "hp": 330}]           # idx2: online but less built
    obs = _obs(bench, {"id": 678, "hp": 200, "energies": [1]})
    board = p._board(obs, obs["select"])
    assert board.best_promote_slot == (5, 1)                     # (BENCH, index 1) — the 3-Energy Mega
    dec = p.explain(obs)
    assert "promote-the-ready-wincon" in _fired(dec.options[1])  # fires only on best body …
    assert "promote-the-ready-wincon" not in _fired(dec.options[0])  # … not bare copy
    assert "promote-the-ready-wincon" not in _fired(dec.options[2])  # … not lesser-built copy
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0025")
def test_promote_the_ready_wincon_fires_at_switch_too():
    # The new-Active pick on RETREAT (SWITCH) must also bring up the built wincon, not bench-slot-0
    # (ep83007714 f92: a bare Cinderace at slot 0, the 3-Energy Mega at slot 1).
    p = _pilot()
    bench = [{"id": CINDERACE, "energies": [], "hp": 160},       # idx0: bare off-line body (slot 0)
             {"id": MEGA, "energies": [3, 3, 3], "hp": 430}]     # idx1: the powered wincon
    obs = _obs(bench, {"id": 678, "hp": 200, "energies": [1]}, ctx=SWITCH, active={"id": MEGA})
    assert p._board(obs, obs["select"]).best_promote_slot == (5, 1)
    dec = p.explain(obs)
    assert "promote-the-ready-wincon" in _fired(dec.options[1])  # fires at SWITCH, on the wincon
    assert p.decide(obs) == [1]                                  # not bench-slot-0 Cinderace
