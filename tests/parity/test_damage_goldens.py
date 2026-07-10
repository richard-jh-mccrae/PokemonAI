"""ADR-0032 damage goldens re-asserted on cgpy (ADR-0050 M2 close-out).

Weakness x2, Resistance -30, Jetting Blow's 120-base + flat-50 bench snipe, Nebula
Beam's 210 ignoring W/R, and the benched-Tera zero — each trace-pinned during the M2
burn-down. The Crustle-immunity variants (Nebula Beam 210 THROUGH Crustle / Jetting
Blow 0 into Crustle) need the defender-side effect seam, which no parity trace
exercises yet — they land with the pool-wide fan-out (M4). REQ-CGPY-0002.
"""
from __future__ import annotations

import pytest

from cgpy.cards import CardDB
from cgpy.chain import def_for, start_program
from cgpy.damage import attack_damage
from cgpy.state import CardInstance, GameState, PokemonInPlay
from cgpy.turn import apply_answer

DB = CardDB.load()

CINDERACE = 666        # fire, weak to water
MEGA_STARMIE = 1031    # water attacker (Jetting Blow 1487 / Nebula Beam 1488)
DRAGAPULT = 121        # Tera: benched attack damage is prevented
STARYU = 1030
JETTING_BLOW = 1487
NEBULA_BEAM = 1488


def make_state(attacker_cid: int, defender_cid: int,
               defender_bench: list[int] = ()) -> GameState:
    cards: dict[int, CardInstance] = {}
    serial = iter(range(3, 200))

    def mon(cid: int, owner: int) -> PokemonInPlay:
        s = next(serial)
        cards[s] = CardInstance(serial=s, card_id=cid, owner=owner)
        hp = DB.card(cid).hp
        return PokemonInPlay(stack=[s], hp=hp, max_hp=hp)

    gs = GameState(db=DB, cards=cards, players=[], rng=None)
    from cgpy.state import PlayerBoard
    b0, b1 = PlayerBoard(), PlayerBoard()
    b0.active = mon(attacker_cid, 0)
    b1.active = mon(defender_cid, 1)
    b1.bench = [mon(c, 1) for c in defender_bench]
    gs.players = [b0, b1]
    gs.turn = 3
    gs.phase = "TURN"
    return gs


def test_weakness_doubles():
    """Jetting Blow (water 120) into Cinderace (weak {W}) = 240 — pinned
    ms_mirror_1002 f25 (HP_CHANGE -240)."""
    gs = make_state(MEGA_STARMIE, CINDERACE)
    dmg = attack_damage(gs, gs.players[0].active, DB.attacks[JETTING_BLOW],
                        gs.players[1].active)
    assert dmg == 240


def test_nebula_beam_ignores_weakness():
    """Nebula Beam = 210 flat even into a water-weak defender (card text; def flag)."""
    adef = def_for(f"attack:{NEBULA_BEAM}") or {}
    assert adef.get("ignoreWeaknessResistance") is True
    gs = make_state(MEGA_STARMIE, CINDERACE)
    dmg = attack_damage(gs, gs.players[0].active, DB.attacks[NEBULA_BEAM],
                        gs.players[1].active, ignore_wr=True)
    assert dmg == 210


def test_resistance_reduces_30():
    """Resistance -30 after weakness, floor 0 (docs/rules.md §5)."""
    found = None
    for d in DB.cards.values():
        if d.cardType != 0 or d.resistance is None:
            continue
        for a in DB.cards.values():
            if a.cardType != 0 or int(a.energyType) != int(d.resistance):
                continue
            for i in a.attacks:
                if DB.attacks[i].damage > 30:
                    found = (a, d, DB.attacks[i])
                    break
            if found:
                break
        if found:
            break
    if not found:
        pytest.skip("pool has no resistance pair with a >30-damage attack")
    atk_stat, dfn_stat, attack = found
    gs = make_state(atk_stat.cardId, dfn_stat.cardId)
    dmg = attack_damage(gs, gs.players[0].active, attack, gs.players[1].active)
    expected = attack.damage
    if dfn_stat.weakness is not None and dfn_stat.weakness == atk_stat.energyType:
        expected *= 2
    assert dmg == expected - 30


def _run_rider(gs: GameState, rider: list, pick: int) -> None:
    start_program(gs, 0, gs.players[0].active.top, rider, kind="attack")
    assert gs.pending is not None
    apply_answer(gs, [pick])


def test_jetting_blow_bench_snipe_is_flat_50():
    """The rider hits a chosen benched Pokémon for exactly 50, no W/R — pinned
    ms_mirror_1002 f26 (HP_CHANGE -50 on a water-weak bench Staryu... snipe stays 50)."""
    rider = (def_for(f"attack:{JETTING_BLOW}") or {}).get("rider")
    assert rider, "Jetting Blow def must carry its bench-snipe rider"
    gs = make_state(MEGA_STARMIE, CINDERACE, defender_bench=[STARYU])
    before = gs.players[1].bench[0].hp
    _run_rider(gs, rider, pick=0)
    assert before - gs.players[1].bench[0].hp == 50


def test_benched_tera_takes_zero():
    """Attack damage into a benched Tera Pokémon is prevented (HP unchanged) — pinned
    v2_ms_dx_5401 f100 (HP_CHANGE value 0 on benched Dragapult ex)."""
    rider = (def_for(f"attack:{JETTING_BLOW}") or {}).get("rider")
    gs = make_state(MEGA_STARMIE, CINDERACE, defender_bench=[DRAGAPULT])
    before = gs.players[1].bench[0].hp
    _run_rider(gs, rider, pick=0)
    assert gs.players[1].bench[0].hp == before
