"""Card-fact Posture (the deferred-debt 'needs Posture' blunders, resolved closed-form via card facts).

- `prevent_ex_damage` (Crustle's ex-lock): my ex attacker does 0, so retreat into a NON-ex attacker
  that can KO it. - `stall_target_is_keystone`: gust the opponent's energyless ex to strand it.
- `opp_has_hand_size_attacker`: play Harlequin to shrink a hand-size deck (Alakazam).
"""
import pytest

from common.cards import CardFunctions
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

MAIN, ATTACK, PLAY, RETREAT, ATTACH, HAND = 0, 13, 7, 12, 8, 2
MEGA, CINDER, CRUSTLE, ALAKAZAM, KADABRA, HARLEQUIN = 1031, 666, 345, 743, 742, 1223


def _fired(t):
    return {h.id for h, _ in t.fired}


DREEPY = 998


def _stats():
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, minAttackCost=1,
                       minCostDamage=120, attacks=(11,), evolvesFrom="Staryu"),
        DREEPY: CardStat(DREEPY, name="Dreepy", hp=40),
        CINDER: CardStat(CINDER, name="Cinderace", hp=160, minAttackCost=1, minCostDamage=50, attacks=(20,)),
        CRUSTLE: CardStat(CRUSTLE, name="Crustle", hp=150, retreatCost=3, maxDamage=120),
        ALAKAZAM: CardStat(ALAKAZAM, name="Alakazam", hp=140, retreatCost=2, ex=True, maxDamage=10,
                           minCostDamage=10, evolvesFrom="Kadabra"),
        KADABRA: CardStat(KADABRA, name="Kadabra", hp=80, maxDamage=30, evolvesFrom="Abra"),
        HARLEQUIN: CardStat(HARLEQUIN, name="Harlequin", cardType=3),
    })


def _funcs():
    return CardFunctions({CRUSTLE: ["prevent_ex_damage"], ALAKAZAM: ["hand_size_attacker"],
                          KADABRA: [], HARLEQUIN: ["draw", "hand_disruption", "shuffle_hand"]})


def _pilot():
    strat = Strategy(lines=[Line(path=[1030, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"], CINDER: ["accel_source"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=_funcs(), attacks={11: 120, 20: 50}, attack_costs={11: 1, 20: 1},
                 bench_snipe={11: 50})


@pytest.mark.req("REQ-GEN-0052")
def test_retreat_off_an_ex_locked_wall_into_a_non_ex_attacker():
    # Opp Active = Crustle (prevents ex damage). My Mega ex does 0 to it; benched non-ex Cinderace
    # (50 dmg) KOs the 50-HP Crustle. Retreat into Cinderace -- don't whiff with the Mega.
    p = _pilot()
    me = {"active": [{"id": MEGA, "energies": [1] * 6, "hp": 330}],
          "bench": [{"id": CINDER, "energies": [1], "hp": 160}], "hand": []}
    opp = {"active": [{"id": CRUSTLE, "energies": [1], "hp": 50}], "bench": []}
    obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": 7},
           "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                      "option": [{"type": ATTACK, "attackId": 11}, {"type": RETREAT}, {"type": 14}]}}
    traces = p.explain(obs)
    assert traces.options[0].tactical <= 0                # Mega's attack is prevented (whiff --
    assert traces.options[1].tactical >= KO_SCORE         # also pays the efficiency cost);
    # retreat -> Cinderace KOs Crustle
    assert p.decide(obs) == [1]                           # retreat off the ex-locked wall


@pytest.mark.req("REQ-GEN-0052")
def test_play_harlequin_against_a_hand_size_attacker_line():
    # Opp has Kadabra (line reaches Alakazam, a hand_size_attacker). Play Harlequin to shrink hand.
    p = _pilot()
    me = {"active": [{"id": MEGA, "energies": [1], "hp": 330}], "bench": [], "hand": [{"id": HARLEQUIN}]}
    opp = {"active": [{"id": KADABRA, "energies": [], "hp": 80}], "bench": []}
    obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": 6},
           "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                      "option": [{"type": PLAY, "index": 0}]}}
    assert p._board(obs, obs["select"]).opp_has_hand_size_attacker
    assert "play-harlequin-vs-hand-size" in _fired(p.explain(obs).options[0])


@pytest.mark.req("REQ-DMG-0006")
def test_prevented_active_damage_does_not_kill_the_bench_snipe_credit():
    # ADR-0032 per-target semantics: vs Crustle, Mega's Jetting Blow (attack 11) deals 0 to the
    # ACTIVE -- but its 50 bench rider still KOs the benched 40-HP Dreepy, banking a real prize.
    # Old attack-blind path early-returned 0 and the snipe was invisible.
    p = _pilot()
    me = {"active": [{"id": MEGA, "energies": [1] * 6, "hp": 330}], "bench": [], "hand": []}
    opp = {"active": [{"id": CRUSTLE, "energies": [1], "hp": 150}],
           "bench": [{"id": DREEPY, "hp": 40}]}
    obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": 7},
           "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                      "option": [{"type": ATTACK, "attackId": 11}, {"type": 14}]}}
    traces = p.explain(obs)
    assert traces.options[0].tactical >= KO_SCORE          # snipe-KO is a banked prize
    assert p.decide(obs) == [0]                            # attack -- don't pass the turn


@pytest.mark.req("REQ-GEN-0052")
def test_a_non_ex_attacker_is_not_prevented():
    # Sanity: Cinderace (non-ex) NOT blocked by Crustle's ex-lock -- KO oracle still fires.
    p = _pilot()
    assert not p._ability_prevents_damage(p.stats.get(CINDER), CRUSTLE)
    assert p._ability_prevents_damage(p.stats.get(MEGA), CRUSTLE)        # Mega ex IS blocked
