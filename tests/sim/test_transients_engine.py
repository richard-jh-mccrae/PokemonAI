"""Engine verification of the transient takes-less family (ADR-0033, plan item 4).

Both seats attack; the dealt HP delta must be printed − reduction. The engine is the authority for
the window semantics the tracker assumes: the grant lives exactly through the opponent's next turn.

REQ-TRANS-0005.
"""
import sys
from pathlib import Path

import pytest

from conftest import on_cgpy_twin

if on_cgpy_twin():
    pytest.skip("transient-window measurement requires native effects deferred by cgpy",
                allow_module_level=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

ATTACK, PLAY, ATTACH, CARD, END, YES, NO = 13, 7, 8, 3, 14, 1, 2

# Shaymin's Grass is neither resisted nor weak against Sigilyph, so Reflect's −40 is the ONLY
# modifier on the hit — a type that resisted too would compose two reductions and muddy the read.
ATTACKER, ATK_ENERGY, ATK_AID, PRINTED = 45, 1, 43, 50     # Shaymin: Rear Kick 50 (plain)
DEFENDER, DEF_ENERGY, DEF_AID, REDUCTION = 591, 5, 849, 40  # Sigilyph: Reflect — "takes 40 less"


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


def _hand_ids(obs, seat):
    pl = _players(obs)
    return [c.get("id") for c in ((pl[seat] or {}).get("hand") or [])] if seat < len(pl) else []


def _choose(obs, key, want_attack):
    """Greedy per-seat driver. Prefers ``want_attack`` (Sigilyph must Reflect) but takes any attack."""
    opts = (obs.get("select") or {}).get("option") or []
    seat = _seat(obs)
    attacks = [i for i, o in enumerate(opts) if o.get("type") == ATTACK]
    if attacks:
        return next(([i] for i in attacks if opts[i].get("attackId") == want_attack), [attacks[0]])
    if any(o.get("type") in (YES, NO) for o in opts):  # mulligan check
        want = YES if key not in _hand_ids(obs, seat) else NO
        return next(([i] for i, o in enumerate(opts) if o.get("type") == want), [0])
    if _my_active(obs, seat) is not None:
        for i, o in enumerate(opts):
            if o.get("type") == ATTACH:
                return [i]
    plays = [i for i, o in enumerate(opts) if o.get("type") == PLAY]
    if plays:
        hand = _hand_ids(obs, seat)
        for i in plays:
            idx = opts[i].get("index")
            if idx is not None and idx < len(hand) and hand[idx] == key:
                return [i]
        return [plays[0]]
    cards = [i for i, o in enumerate(opts) if o.get("type") == CARD]
    if cards:
        return next(([i] for i in cards if opts[i].get("id") == key), [cards[0]])
    return next(([i] for i, o in enumerate(opts) if o.get("type") == END), [0])


@pytest.mark.req("REQ-TRANS-0005")
def test_engine_confirms_next_turn_reduction():
    battle_start, battle_select, battle_finish = _engine()
    atk_deck = [ATTACKER] * 4 + [ATK_ENERGY] * 56
    def_deck = [DEFENDER] * 4 + [DEF_ENERGY] * 56
    obs, start = battle_start(atk_deck, def_deck)      # attacker = seat 0, defender = seat 1
    assert getattr(start, "errorPlayer", -1) < 0
    prev_hp, dealt = None, []
    try:
        for _ in range(600):
            cur = obs.get("current") or {}
            if cur.get("result") not in (None, -1) or obs.get("select") is None:
                break
            pl = _players(obs)
            d = next((p for p in ((pl[1] or {}).get("active") or []) if p), None) if len(pl) > 1 else None
            hp = d.get("hp") if (d and d.get("id") == DEFENDER) else None
            if hp is not None and prev_hp is not None and hp < prev_hp:
                dealt.append(prev_hp - hp)
            prev_hp = hp
            mine = _seat(obs) == 0
            obs = battle_select(_choose(obs, ATTACKER if mine else DEFENDER,
                                        ATK_AID if mine else DEF_AID))
            if len(dealt) >= 2:
                break
    finally:
        battle_finish()
    # Sigilyph Reflects every turn, so EVERY hit lands under a fresh shield; an unshielded hit
    # would read the full printed damage.
    assert dealt, "no hit landed — driver failure, not a model verdict"
    assert all(d == PRINTED - REDUCTION for d in dealt), f"dealt {dealt}, want {PRINTED - REDUCTION}"
