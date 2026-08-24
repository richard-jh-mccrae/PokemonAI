"""ADR-0032 damage goldens re-asserted on cgpy, plus the attached-Tool `attackBonus` gates that
ride the same `attack_damage` path. REQ-CGPY-0002.

Not every assertion here is trace-pinned: `test_resistance_reduces_30` sweeps the pool for a
matching pair, and the Tool block below is derived from printed card text. This module is the one
home for hand-built `attack_damage` assertions; its builder lives in `tests/cgpy_state_helpers.py`.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from cgpy.chain import def_for, load_chain_defs, start_program
from cgpy.damage import attack_damage
from cgpy.turn import apply_answer

from cgpy_state_helpers import DB, make_state

CINDERACE = 666        # fire, weak to water
MEGA_STARMIE = 1031    # water attacker (Jetting Blow 1487 / Nebula Beam 1488)
DRAGAPULT = 121        # Tera: benched attack damage is prevented
STARYU = 1030
JETTING_BLOW = 1487
NEBULA_BEAM = 1488


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
                        gs.players[1].active, adef=adef)
    assert dmg == 210


def test_resistance_reduces_30():
    """Resistance -30 after weakness, floor 0 (docs/rulebook.txt §5)."""
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


# ------------------------------------------------------------------- attached-Tool bonuses
# Every pair below is W/R-neutral, so the printed attack damage is the baseline and a delta is Tool.

BRAVE_BANGLE = 1175        # +30, holder must have no Rule Box, defender must be {ex}
MAXIMUM_BELT = 1158        # +50, defender must be {ex}, no holder gate — the control
SLOWKING = 163             # no Rule Box; Super Psy Bolt (214) = vanilla 120
SUPER_PSY_BOLT = 214
LATIAS_EX = 184            # Rule Box (`ex`); Eon Blade (243) = 200, no damage rider
EON_BLADE = 243
METAGROSS = 276            # no Rule Box — the non-{ex} defender
MEGA_KANGASKHAN_EX = 756   # `megaEx`, NOT `ex` — the Mega leg of the defender gate


def _tool_damage(holder: int, attack_id: int, defender: int, *tools: int) -> int:
    gs = make_state(holder, defender, attacker_tools=list(tools))
    return attack_damage(gs, gs.players[0].active, DB.attacks[attack_id],
                         gs.players[1].active)


@pytest.mark.parametrize("holder,attack_id,defender,expected,why", [
    (SLOWKING, SUPER_PSY_BOLT, LATIAS_EX, 150,
     "no Rule Box AND defender {ex} — the one combination the card pays out"),
    (SLOWKING, SUPER_PSY_BOLT, METAGROSS, 120,
     "no Rule Box but defender is not {ex} — the gate this issue restores"),
    (LATIAS_EX, EON_BLADE, MEGA_KANGASKHAN_EX, 200,
     "defender {ex} but the holder HAS a Rule Box"),
    (LATIAS_EX, EON_BLADE, METAGROSS, 200,
     "neither gate holds"),
])
def test_brave_bangle_pays_out_only_when_BOTH_of_its_gates_hold(
        holder, attack_id, defender, expected, why):
    """Brave Bangle (1175): +30 only when the holder has NO Rule Box and the defending Active is a
    Pokémon {ex}, pre-W/R. Two gates, so four combinations and exactly one payout."""
    assert _tool_damage(holder, attack_id, defender, BRAVE_BANGLE) == expected, why


def test_a_Mega_Evolution_Pokemon_ex_counts_as_a_Pokemon_ex_for_the_defender_gate():
    """`docs/rulebook.txt` Appendix 1 makes a Mega Evolution Pokémon ex a Pokémon ex, but the
    card carries `megaEx` and NOT `ex`, so a gate testing only `ex` silently excludes it."""
    assert DB.card(MEGA_KANGASKHAN_EX).megaEx and not DB.card(MEGA_KANGASKHAN_EX).ex
    assert _tool_damage(SLOWKING, SUPER_PSY_BOLT, MEGA_KANGASKHAN_EX, BRAVE_BANGLE) == 150


def test_maximum_belt_proves_the_defenderEx_gate_is_LIVE_on_this_path():
    """The positive control for the INSTRUMENT, not the card: Maximum Belt prints the identical
    `{ex}` restriction with no holder gate, so it must swing across the same two defenders."""
    assert _tool_damage(SLOWKING, SUPER_PSY_BOLT, LATIAS_EX, MAXIMUM_BELT) == 170
    assert _tool_damage(SLOWKING, SUPER_PSY_BOLT, METAGROSS, MAXIMUM_BELT) == 120


def test_every_attackBonus_Tool_agrees_with_its_printed_ex_restriction():
    """The card table is the authority: a def carries `defenderEx` IF AND ONLY IF its text prints
    "Active Pokémon {ex}". Read through `load_chain_defs()`, never a local re-merge."""
    printed: dict[str, str] = {}
    csv_path = Path(__file__).resolve().parents[2] / "data" / "EN_Card_Data.csv"
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):     # one row per ATTACK — 723 ids repeat, so ACCUMULATE
            cid = row["Card ID"]           # rather than let the last row win and drop the rest
            printed[cid] = printed.get(cid, "") + (row["Effect Explanation"] or "")

    agree_true, agree_false, mismatched = [], [], []
    for cid, cdef in load_chain_defs().items():
        if not isinstance(cdef, dict):
            continue
        bonus = (cdef.get("tool") or {}).get("attackBonus")
        if not bonus:
            continue
        prints_ex = "Active Pokémon {ex}" in printed.get(cid, "")
        flagged = bool(bonus.get("defenderEx"))
        if flagged != prints_ex:
            mismatched.append((cid, cdef.get("name"), flagged, prints_ex))
        elif prints_ex:
            agree_true.append(cid)
        else:
            agree_false.append(cid)

    assert agree_true, "sweep found no {ex}-restricted attackBonus Tool — instrument is broken"
    assert agree_false, "sweep found no unrestricted attackBonus Tool — instrument is broken"
    assert not mismatched, f"ChainDef disagrees with printed card text: {mismatched}"


# -------------------------------------------------- the open FILTERED-COUNT family (ADR-0115)
# Two implementations of one predicate: the contract between their vocabularies is the VALUE.

TR_KOFFING, TR_WEEZING = 461, 462       # the pool's ONLY two "Koffing"/"Weezing" names
TYMPOLE, PALPITOAD, SEISMITOAD = 500, 501, 502
REGIGIGAS = 251                         # neutral defender: weakness {F}=6, no Resistance, no
                                        # Ability, no `defense` ChainDef — so nothing but the
                                        # scaling term moves the number for a {D}/{W} attacker
EXPLODE, ROUND_708 = 651, 708


@pytest.mark.req("REQ-SCALER-0013")
def test_the_pool_holds_exactly_the_matching_cards_this_family_was_ruled_against():
    """A positive control: if the pool widened, the parametrised counts above would be reasoning
    about a board that cannot occur, so a set refresh fails HERE."""
    named = sorted(c.cardId for c in DB.cards.values()
                   if "Koffing" in c.name or "Weezing" in c.name)
    assert named == [TR_KOFFING, TR_WEEZING], "the name predicate's reach moved"
    rounds = sorted(c.cardId for c in DB.cards.values()
                    if any(DB.attacks[a].name == "Round" for a in c.attacks))
    assert rounds == [TYMPOLE, PALPITOAD, SEISMITOAD, 842], "the Round predicate's reach moved"
