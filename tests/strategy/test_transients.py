"""Transient attack effects (ADR-0033): the "during your (opponent's) next turn" family — 138
attacks whose effects the observation does NOT expose, tracked match-scoped from ATTACK logs
(deck-tracker precedent) and consumed by the damage oracle + Incoming.

Requirements:
  REQ-TRANS-0001  parse the transient families off attack text (fields on AttackStat).
  REQ-TRANS-0002  tracker: an ATTACK log with transient fields grants an effect for that side,
                  bound to the attacker serial; the grant EXPIRES when the granter's next turn
                  starts (TURN_START); per-viewer log replays are idempotent; a new match
                  (turn regression) resets.
  REQ-TRANS-0003  oracle: a live defender-side grant (reduction / prevent-all) joins
                  compute_active_damage after W/R — pierced by ignoresEffects (Nebula class).
  REQ-TRANS-0004  Incoming: a live attacker-side grant on the opponent's Active — self-lock
                  zeroes it, a same-attack lock excludes that attack, a self-bonus raises it.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.transients import TransientTracker
from pilot_helpers import make_select, opt, poke, state

TURN_START, ATTACK_LOG = 2, 15
FB, PLAIN, LOCKED, NAMED, BONUS = 1047, 11, 60, 61, 62


def _stats():
    return {
        FB: AttackStat(attackId=FB, damage=200, cost=3, nextTurnReduction=30),
        PLAIN: AttackStat(attackId=PLAIN, damage=120, cost=1),
        LOCKED: AttackStat(attackId=LOCKED, damage=90, cost=1, nextTurnSelfLock=True),
        NAMED: AttackStat(attackId=NAMED, damage=150, cost=1, nextTurnSameAttackLock=True),
        BONUS: AttackStat(attackId=BONUS, damage=50, cost=1, nextTurnSelfBonus=120),
    }


def _obs(turn, logs, my_serial=1, opp_serial=9):
    return {"current": {"turn": turn, "yourIndex": 0, "players": [
        {"active": [{"id": 1, "serial": my_serial, "hp": 100, "energies": []}], "bench": [],
         "hand": [], "handCount": 0, "discard": [], "prize": [None]},
        {"active": [{"id": 2, "serial": opp_serial, "hp": 100, "energies": []}], "bench": [],
         "hand": None, "handCount": 0, "discard": [], "prize": [None]}]},
            "logs": logs}


def _atk(side, aid, serial):
    return {"type": ATTACK_LOG, "playerIndex": side, "attackId": aid, "serial": serial}


@pytest.mark.req("REQ-TRANS-0002")
def test_grant_lives_through_their_turn_and_expires_on_granters_next():
    tr = TransientTracker(_stats().get)
    tr.observe(_obs(3, [_atk(1, FB, 9)]))                      # opp (side 1) used Frost Barrier
    g = tr.grant_for_serial(9)
    assert g and g.get("reduction") == 30
    tr.observe(_obs(4, [{"type": TURN_START, "playerIndex": 0}]))   # MY turn: still live
    assert tr.grant_for_serial(9)
    tr.observe(_obs(5, [{"type": TURN_START, "playerIndex": 1}]))   # THEIR next turn starts: gone
    assert tr.grant_for_serial(9) is None


@pytest.mark.req("REQ-TRANS-0002")
def test_replayed_logs_are_idempotent_and_new_match_resets():
    tr = TransientTracker(_stats().get)
    logs = [_atk(1, FB, 9)]
    tr.observe(_obs(3, logs))
    tr.observe(_obs(3, logs))                                  # per-viewer replay: same logs again
    assert tr.grant_for_serial(9).get("reduction") == 30
    tr.observe(_obs(1, [{"type": TURN_START, "playerIndex": 0}]))   # turn regressed: NEW MATCH
    assert tr.grant_for_serial(9) is None


@pytest.mark.req("REQ-TRANS-0003")
def test_live_reduction_and_prevent_join_the_oracle():
    from common.strategy.damage import compute_active_damage
    atk = AttackStat(attackId=1, damage=120)
    nebula = AttackStat(attackId=2, damage=210, ignoresWeakness=True, ignoresResistance=True,
                        ignoresEffects=True)
    me = CardStat(cardId=50, name="Me", hp=200, energyType=3)
    them = CardStat(cardId=2, name="Them", hp=200, energyType=7)
    assert compute_active_damage(atk, me, them, frozenset(),
                                 defender_transient={"reduction": 30}) == 90
    assert compute_active_damage(atk, me, them, frozenset(),
                                 defender_transient={"prevent_all": True}) == 0
    # Nebula-class pierces transient protection just like static effects (Drednaw finding)
    assert compute_active_damage(nebula, me, them, frozenset(),
                                 defender_transient={"prevent_all": True}) == 210


def _pilot():
    stats = DictCardStatProvider({
        1: CardStat(cardId=1, name="Mine", hp=100, energyType=3, attacks=(PLAIN,), minAttackCost=1),
        2: CardStat(cardId=2, name="Theirs", hp=300, energyType=7,
                    attacks=(LOCKED, BONUS), minAttackCost=1),
    }, attacks=_stats())
    return Pilot(Strategy(), deck=[1] * 60, stats=stats, functions=CardFunctions({}))


@pytest.mark.req("REQ-TRANS-0004")
def test_opponents_frost_barrier_shrinks_my_tactical_damage_and_expires():
    # their Active (serial 9) used Frost Barrier last turn -> my Jetting-class 120 lands 90;
    # after THEIR next turn starts, shield gone -> full 120 again
    p = _pilot()
    p._transients.observe(_obs(3, [_atk(1, FB, 9)]))

    def _menu(turn):
        board = state(active=poke(1, energy=1, hp=100), opp_active=poke(2, hp=300),
                      prizes=2, opp_prizes=2, turn=turn)      # turns stay monotonic (real play)
        board["players"][1]["active"][0]["serial"] = 9
        return make_select([{"type": 13, "attackId": PLAIN}, opt(14)], current=board)

    assert p.explain(_menu(4)).options[0].tactical == pytest.approx(90 - 0.1)   # 120-30, minus eff.
    p._transients.observe(_obs(5, [{"type": TURN_START, "playerIndex": 1}]))
    assert p.explain(_menu(6)).options[0].tactical == pytest.approx(120 - 0.1)


@pytest.mark.req("REQ-TRANS-0004")
def _incoming(p, ma, oa):
    """`Board.incoming_active_damage` through a FRESH per-decision snapshot.

    The read routes via the StateModel now (POC-T1, Issue #260) and the model MEMOIZES, so a
    transient grant observed between two reads needs a rebuilt snapshot to be seen — which is the
    model's purity contract working, not a workaround for it."""
    p._snapshot({"current": {"yourIndex": 0, "players": [
        {"active": [ma], "bench": []}, {"active": [oa], "bench": []}]}})
    return p._incoming_active_damage(ma, oa)


def test_incoming_respects_their_self_lock_and_self_bonus():
    p = _pilot()
    oa = {"id": 2, "serial": 9, "hp": 300, "energies": [7]}
    ma = {"id": 1, "serial": 1, "hp": 100, "energies": [3]}
    base = _incoming(p, ma, oa)                   # no grants: max(90, 50) = 90
    assert base == 90
    p._transients.observe(_obs(3, [_atk(1, LOCKED, 9)]))       # their Active self-locked
    assert _incoming(p, ma, oa) == 0              # can't attack me next turn
    p._transients.observe(_obs(5, [{"type": TURN_START, "playerIndex": 1}]))   # lock expired
    p._transients.observe(_obs(5, [_atk(1, BONUS, 9)]))        # now +120 self-bonus
    assert _incoming(p, ma, oa) == 90 + 120


@pytest.mark.req("REQ-TRANS-0004")
def test_incoming_same_attack_lock_excludes_only_that_attack():
    p = _pilot()
    p.stats._stats[2] = CardStat(cardId=2, name="Theirs", hp=300, energyType=7,
                                 attacks=(NAMED, PLAIN), minAttackCost=1)
    oa = {"id": 2, "serial": 9, "hp": 300, "energies": [7]}
    ma = {"id": 1, "serial": 1, "hp": 100, "energies": [3]}
    assert _incoming(p, ma, oa) == 150            # NAMED 150 beats PLAIN 120
    p._transients.observe(_obs(3, [_atk(1, NAMED, 9)]))        # NAMED is locked next turn
    assert _incoming(p, ma, oa) == 120            # other attack still threatens
