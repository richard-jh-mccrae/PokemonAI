"""Card-fact Posture (the deferred-debt 'needs Posture' blunders, resolved closed-form via card facts).

- `prevent_ex_damage` (Crustle's ex-lock): my ex attacker does 0, so retreat into a NON-ex attacker
  that can KO it. - `stall_target_is_keystone`: gust the opponent's energyless ex to strand it.
- hand-size posture: Harlequin against an Alakazam line, priced by the survival it buys (ADR-0102 —
  the `opp_has_hand_size_attacker` boolean and its flat rung are retired).
"""
import pytest

from common.cards import CardFunctions
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
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
        # `handSizeDamage=20` is the card fact this posture now turns on (MEG 743 Powerful Hand,
        # "2 damage counters … for each card in your hand"): its printed 10 hides the whole threat,
        # and the scaler is what the Damage Formula — and so the survival clock — actually reads.
        ALAKAZAM: CardStat(ALAKAZAM, name="Alakazam", hp=140, retreatCost=2, ex=True, maxDamage=10,
                           minCostDamage=10, evolvesFrom="Kadabra", handSizeDamage=20),
        KADABRA: CardStat(KADABRA, name="Kadabra", hp=80, maxDamage=30, evolvesFrom="Abra"),
        HARLEQUIN: CardStat(HARLEQUIN, name="Harlequin", cardType=3),
    }, attacks={11: AttackStat(11, damage=120, cost=1, benchSnipe=50),
                20: AttackStat(20, damage=50, cost=1)})


def _funcs():
    return CardFunctions({CRUSTLE: ["prevent_ex_damage"], ALAKAZAM: ["hand_size_attacker"],
                          KADABRA: [], HARLEQUIN: ["draw", "hand_disruption", "shuffle_hand"]})


def _pilot():
    strat = Strategy(lines=[Line(path=[1030, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"], CINDER: ["accel_source"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=_funcs())


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
def test_harlequin_against_a_hand_size_attacker_line_is_priced_BOTH_ways():
    # Opp has Kadabra (line reaches Alakazam, whose Powerful Hand scales off THEIR hand). The posture
    # is unchanged; what changed (ADR-0102) is that it is PRICED rather than flagged. The retired
    # `play-harlequin-vs-hand-size` (+25) fired off `opp_has_hand_size_attacker` — a boolean, so it
    # endorsed the play at full strength on BOTH boards below, including the one where the refresh
    # REFILLS them. `_hand_size_relief_tactical` reads the survival clock instead, so the same card
    # against the same line is worth a lot, nothing, or less than nothing depending on the hand.
    from types import SimpleNamespace

    from common.strategy.context import _PLAY as PLAY_OPT
    p = _pilot()

    def relief(opp_hand):
        me = {"active": [{"id": MEGA, "energies": [1], "hp": 330}], "bench": [],
              "hand": [{"id": HARLEQUIN}]}
        opp = {"active": [{"id": KADABRA, "energies": [], "hp": 80}], "bench": [],
               "handCount": opp_hand}
        obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": 6},
               "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                          "option": [{"type": PLAY, "index": 0}]}}
        board = p._board(obs, obs["select"])
        return p._hand_size_relief_tactical(
            obs, board, SimpleNamespace(card_id=HARLEQUIN, option_type=PLAY_OPT, tags=()))

    assert relief(opp_hand=12) > 0     # 240/turn down to 80: the strip buys real survival
    assert relief(opp_hand=4) == 0     # already at Harlequin's redraw count: nothing moves
    assert relief(opp_hand=1) < 0      # 20/turn UP to 80: the refill arms the attacker
    assert "play-harlequin-vs-hand-size" not in _fired(p.explain(
        {"current": {"players": [{"active": [{"id": MEGA, "energies": [1], "hp": 330}], "bench": [],
                                  "hand": [{"id": HARLEQUIN}]},
                                 {"active": [{"id": KADABRA, "energies": [], "hp": 80}],
                                  "bench": [], "handCount": 12}], "yourIndex": 0, "turn": 6},
         "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                    "option": [{"type": PLAY, "index": 0}]}}).options[0])


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
    # Sanity: Cinderace (non-ex) NOT blocked by Crustle's ex-lock — the oracle lands its 50;
    # the Mega ex's plain attack IS zeroed (attack-scoped prevention, the one damage.py home —
    # the Pilot-side _ability_prevents_damage pair is retired, ADR-0052).
    p = _pilot()
    assert p.predicted_damage(CINDER, 20, {"id": CRUSTLE, "hp": 150}) == 50
    assert p.predicted_damage(MEGA, 11, {"id": CRUSTLE, "hp": 150}) == 0
