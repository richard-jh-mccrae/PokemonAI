"""M2.0 — wire the Read onto the Board (Posture-OFF).

The Pilot senses the opponent via an injected Scout and surfaces the Read on its public
`explain()` output, without changing any decision yet (nothing scores off it — that's M2.1b).
See ADR-0026 (the wiring staircase) and docs/scouting.md (the Read).
"""
import pytest

from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.scouting.scout import Scout
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from scouting_helpers import MEGA_LUCARIO, RIOLU, SOLROCK, tiny_artifact

MAIN, PLAY = 0, 7
MEGA, STARYU = 1031, 1030


def _stats():
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True,
                       minAttackCost=1, minCostDamage=120, attacks=(11,), evolvesFrom="Staryu"),
    })


def _pilot(scout=None):
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 attacks={11: 120}, attack_costs={11: 1}, scout=scout)


def _obs_facing_mega_lucario():
    """A MAIN-phase menu where the opponent's board reveals the Mega Lucario ex line."""
    me = {"active": [{"id": MEGA, "energies": [1], "hp": 330}], "bench": [],
          "hand": [{"id": 1}], "discard": [], "prize": []}
    opp = {"active": [{"id": MEGA_LUCARIO, "energies": [], "hp": 0}],
           "bench": [{"id": SOLROCK, "energies": []}, {"id": RIOLU, "energies": []}],
           "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None},
            "logs": []}


def _obs_two_option_menu():
    """A 2-option MAIN menu vs the recognized Mega Lucario ex board (ordering can matter)."""
    obs = _obs_facing_mega_lucario()
    obs["current"]["players"][0]["hand"] = [{"id": 1}, {"id": 2}]
    obs["select"]["option"] = [{"type": PLAY, "index": 0}, {"type": PLAY, "index": 1}]
    return obs


@pytest.mark.req("REQ-POSTURE-0001")
def test_explain_surfaces_the_recognized_archetype():
    # The Pilot senses via the Scout and exposes the Read on its public explain() output.
    decision = _pilot(scout=Scout(tiny_artifact())).explain(_obs_facing_mega_lucario())
    assert decision.read is not None
    assert decision.read.candidates[0][0] == "Mega Lucario ex"


@pytest.mark.req("REQ-POSTURE-0001")
def test_wiring_a_scout_changes_no_decision_or_score():
    # M2.0 is Posture-OFF: the Read rides on the Board, but nothing scores off it yet. A wired Scout
    # (even confidently recognizing the opponent) must produce byte-identical choices AND scores.
    obs = _obs_two_option_menu()
    off, on = _pilot(scout=None), _pilot(scout=Scout(tiny_artifact()))
    assert on.decide(obs) == off.decide(obs)
    assert [o.score for o in on.explain(obs).options] == [o.score for o in off.explain(obs).options]


def _obs_early_unknown():
    """Early game: the opponent has revealed nothing diagnostic (empty board)."""
    me = {"active": [{"id": MEGA, "energies": [1], "hp": 330}], "bench": [],
          "hand": [{"id": 1}], "discard": [], "prize": []}
    opp = {"active": [], "bench": [], "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 1},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None},
            "logs": []}


@pytest.mark.req("REQ-POSTURE-0001")
def test_unrecognized_opponent_yields_low_confidence_read():
    # Unknown / off-meta opponent: the Read stays below the recognition bar, so Posture (which will
    # γ-gate on confidence in M2.1b) is off by construction. The Pilot never crashes (Read never raises).
    decision = _pilot(scout=Scout(tiny_artifact())).explain(_obs_early_unknown())
    assert decision.read is not None
    assert decision.read.confidence[0] < 0.6     # below the Scout's recognition threshold -> Posture off
