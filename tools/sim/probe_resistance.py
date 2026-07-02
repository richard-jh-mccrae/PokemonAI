"""Behavioral probe of the engine's RESISTANCE reduction amount (ADR-0022; CLAUDE.md: sim is authority).

The Resistance amount is in NO card data — `CardData.resistance` and the CSV are type-only, and the
amount appears in no text field. So it is determinable ONLY from the simulator. This probe drives the
native engine (`cg.game`) with two stacked legal decks built so the ONLY damage modifier on the hit is
Resistance, then reads the defender's HP delta: `resistance = printed_damage - damage_dealt`.

    python tools/sim/probe_resistance.py        # quick 3-card smoke (below)

The amount is the card's PRINTED Resistance (a per-card fact, e.g. Slowking "Fighting -30"), which is
absent from our data export. Verified 2026-06-29 as a uniform **-30** across this set: probing all 47
*basic* resistant Pokémon (32 Fighting-resist + 15 Grass-resist, ex & non-ex, HP 90-280) returned -30
on every one (2 cards unmeasurable — abilities the greedy driver mishandles — but none a different
value). The 3 MATCHUPS below are a fast smoke; widen `MATCHUPS` to re-sweep. Re-run if the engine
(`cg/*.dll` / `*.so`) is updated, or when adding a Fighting/Grass deck that relies on it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cg.game import battle_finish, battle_select, battle_start  # noqa: E402

ATTACK, PLAY, ATTACH, CARD, END, YES, NO = 13, 7, 8, 3, 14, 1, 2

# (label, attacker_cid, printed_dmg, attacker_energy_id, defender_cid) — attacker's TYPE drives
# resistance match; defender is NOT Weak to that type, so only modifier on the hit is Resistance.
MATCHUPS = [
    ("Fighting -> Iron Crown ex (F-resist, ex)", 116, 70, 6, 80),
    ("Fighting -> Ho-Oh (F-resist, non-ex)", 116, 70, 6, 318),
    ("Grass -> Heatran (G-resist, non-ex)", 45, 50, 1, 118),
]


def _players(obs):
    return (obs.get("current") or {}).get("players") or []


def _seat(obs):
    return (obs.get("current") or {}).get("yourIndex", 0)


def _active(obs, seat):
    pl = _players(obs)
    if seat >= len(pl) or not pl[seat]:
        return None
    return next((p for p in (pl[seat].get("active") or []) if p), None)


def _defender_hp(obs, defender_cid):
    for pl in _players(obs):
        for p in ((pl or {}).get("active") or []):
            if p and p.get("id") == defender_cid:
                return p.get("hp")
    return None


def _hand_ids(obs, seat):
    pl = _players(obs)
    if seat >= len(pl) or not pl[seat]:
        return []
    return [c.get("id") for c in (pl[seat].get("hand") or [])]


def _choose(obs, atk_seat, attacker_cid, defender_cid):
    """Greedy seat-aware policy: the attacker plays its basic, attaches energy, and attacks; the
    defender just places a basic and ends, sitting still to receive the hit."""
    opts = (obs.get("select") or {}).get("option") or []
    seat = _seat(obs)
    is_attacker = (seat == atk_seat)
    key = attacker_cid if is_attacker else defender_cid

    if is_attacker:                                       # ATTACK whenever offered — the hit we want
        for i, o in enumerate(opts):
            if o.get("type") == ATTACK:
                return [i]
    if any(o.get("type") in (YES, NO) for o in opts):     # mulligan: redraw only if key basic not in hand
        want = YES if key not in _hand_ids(obs, seat) else NO
        for i, o in enumerate(opts):
            if o.get("type") == want:
                return [i]
        return [0]
    if is_attacker and _active(obs, seat) is not None:    # power Active before benching extra copies
        for i, o in enumerate(opts):
            if o.get("type") == ATTACH:
                return [i]
    play = [i for i, o in enumerate(opts) if o.get("type") == PLAY]
    if play:
        hand = _hand_ids(obs, seat)
        for i in play:
            idx = opts[i].get("index")
            if idx is not None and idx < len(hand) and hand[idx] == key:
                return [i]
        return [play[0]]
    cards = [i for i, o in enumerate(opts) if o.get("type") == CARD]
    if cards:
        for i in cards:
            if opts[i].get("id") == key:
                return [i]
        return [cards[0]]
    for i, o in enumerate(opts):
        if o.get("type") == END:
            return [i]
    return [0]


def probe(attacker_cid, printed, energy_id, defender_cid, max_steps=4000):
    """Return the observed Resistance amount, or None if no clean hit landed."""
    atk_deck = [attacker_cid] * 4 + [energy_id] * 56
    def_deck = [defender_cid] * 4 + [energy_id] * 56
    obs, start = battle_start(atk_deck, def_deck)         # attacker is seat 0
    if getattr(start, "errorPlayer", -1) >= 0:
        battle_finish()
        return None
    prev = None
    try:
        for _ in range(max_steps):
            cur = obs.get("current") or {}
            if cur.get("result") not in (None, -1) or obs.get("select") is None:
                return None
            hp = _defender_hp(obs, defender_cid)
            if hp is not None and prev is not None and hp < prev:
                return printed - (prev - hp)              # resistance = printed - dealt
            if hp is not None:
                prev = hp
            try:
                obs = battle_select(_choose(obs, 0, attacker_cid, defender_cid))
            except Exception:
                return None                              # illegal select (e.g. an ability prompt the
                                                         # greedy driver mishandles) — skip this card
    finally:
        battle_finish()
    return None


def main() -> int:
    results = []
    for label, acid, dmg, aen, dcid in MATCHUPS:
        r = probe(acid, dmg, aen, dcid)
        results.append(r)
        print(f"{label}: resistance = {r}")
    clean = [r for r in results if r is not None]
    if clean and all(r == clean[0] for r in clean):
        print(f"\n=> uniform Resistance reduction: -{clean[0]}")
        return 0
    print("\n=> INCONCLUSIVE (no clean hit on some matchup, or non-uniform) — inspect the driver")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
