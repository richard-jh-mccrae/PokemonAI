"""Engine verification of the retreat-lock mechanic (ADR-0033 follow-up, wiring item 4).

Drives a real two-sided battle: Maractus (255) Corners the defending Totodile ("During your
opponent's next turn, the Defending Pokémon can't retreat" — 1-colorless, so any Energy pays it).
The defender keeps a benched body and attached Energy, so RETREAT (OptionType 12) would normally
be offered — and IS, on its pre-lock turn. On every post-Corner turn the engine must OMIT the
RETREAT option from the locked side's menu.

This test is the reason there is NO `retreat_lock` transient field (deleted 2026-07-02): the
engine enforces the lock at the menu, so a menu-driven this-turn Pilot has nothing to read — a
parsed-but-unconsumed field was dead weight. Re-adding a parse requires a real consumer AND this
enforcement fact changing.

REQ-TRANS-0006: the engine omits RETREAT from the locked defender's menu; an unlocked defender
with Energy + a Bench is offered it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

ATTACK, PLAY, ATTACH, CARD, END, YES, NO, RETREAT = 13, 7, 8, 3, 14, 1, 2, 12
MARACTUS, GRASS = 255, 1        # Corner: 1 colorless, 20 dmg, defender can't retreat next turn
TOTODILE, PAWNIARD, WATER = 47, 544, 3   # defender basics (retreat 1) + Water Energy


def _engine():
    try:
        from cg.game import battle_finish, battle_select, battle_start
        return battle_start, battle_select, battle_finish
    except Exception:
        pytest.skip("native engine unavailable")


def _seat(obs):
    return (obs.get("current") or {}).get("yourIndex", 0)


def _players(obs):
    return (obs.get("current") or {}).get("players") or []


def _my_active(obs, seat):
    pl = _players(obs)
    if seat >= len(pl) or not pl[seat]:
        return None
    return next((p for p in (pl[seat].get("active") or []) if p), None)


def _bench_count(obs, seat):
    pl = _players(obs)
    return sum(1 for b in ((pl[seat] or {}).get("bench") or []) if b) if seat < len(pl) else 0


def _choose(obs, attack_now):
    """Seat 0 (Maractus): attach; Corner only once ``attack_now`` (so the defender's unlocked
    control menu is observed first, whatever the draw order). Seat 1 (defender): bench one body,
    attach, END — it never retreats or attacks, so its menu shows exactly what the engine offers."""
    opts = (obs.get("select") or {}).get("option") or []
    s = _seat(obs)
    if any(o.get("type") in (YES, NO) for o in opts):            # mulligan: accept any keepable hand
        return next(([i] for i, o in enumerate(opts) if o.get("type") == NO),
                    [next(i for i, o in enumerate(opts) if o.get("type") == YES)])
    if s == 0 and attack_now:
        atk = [i for i, o in enumerate(opts) if o.get("type") == ATTACK]
        if atk:
            return [atk[0]]
    if s == 1 and _my_active(obs, 1) is not None and _bench_count(obs, 1) < 1:
        plays = [i for i, o in enumerate(opts) if o.get("type") == PLAY]
        if plays:
            return [plays[0]]                                    # bench the retreat target
    for i, o in enumerate(opts):
        if o.get("type") == ATTACH:
            return [i]
    plays = [i for i, o in enumerate(opts) if o.get("type") == PLAY]
    if plays and _my_active(obs, _seat(obs)) is None:
        return [plays[0]]                                        # place the opening Active
    cards = [i for i, o in enumerate(opts) if o.get("type") == CARD]
    if cards:
        return [cards[0]]
    return next(([i] for i, o in enumerate(opts) if o.get("type") == END), [0])


@pytest.mark.req("REQ-TRANS-0006")
def test_engine_omits_retreat_from_the_locked_defenders_menu():
    battle_start, battle_select, battle_finish = _engine()
    obs, start = battle_start([MARACTUS] * 4 + [GRASS] * 56,
                              [TOTODILE] * 4 + [PAWNIARD] * 4 + [WATER] * 52)
    assert getattr(start, "errorPlayer", -1) < 0
    pre_lock, post_lock = [], []
    cornered = False
    try:
        for _ in range(400):
            cur = obs.get("current") or {}
            if cur.get("result") not in (None, -1) or obs.get("select") is None:
                break
            sel = obs.get("select") or {}
            opts = sel.get("option") or []
            for lg in (obs.get("logs") or []):                   # LogType 15 = ATTACK
                if (lg or {}).get("type") == 15 and lg.get("playerIndex") == 0:
                    cornered = True                              # the defender's NEXT turn is locked
            s = _seat(obs)
            if (s == 1 and sel.get("context") == 0 and sel.get("maxCount") == 1
                    and len((_my_active(obs, 1) or {}).get("energies") or []) >= 1
                    and _bench_count(obs, 1) >= 1):
                offered = any(o.get("type") == RETREAT for o in opts)
                (post_lock if cornered else pre_lock).append(offered)
            step = _choose(obs, attack_now=bool(pre_lock))       # hold fire until the control is seen
            ended = opts and opts[step[0]].get("type") == END and s == 1
            obs = battle_select(step)
            if ended:
                cornered = False                                 # the lock window closes with its turn
            if pre_lock and len(post_lock) >= 3:
                break
    finally:
        battle_finish()
    assert pre_lock and any(pre_lock), \
        f"driver failure: no unlocked menu with Energy+Bench was seen (pre_lock={pre_lock})"
    assert post_lock and not any(post_lock), \
        f"engine offered RETREAT on a locked turn (post_lock={post_lock})"
