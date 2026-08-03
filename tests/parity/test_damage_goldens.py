"""ADR-0032 damage goldens re-asserted on cgpy (ADR-0059 M2 close-out), plus the
attached-Tool `attackBonus` gates that ride the same `attack_damage` path.

Weakness x2, Resistance -30, Jetting Blow's 120-base + flat-50 bench snipe, Nebula
Beam's 210 ignoring W/R, and the benched-Tera zero — each trace-pinned during the M2
burn-down. The Crustle-immunity variants (Nebula Beam 210 THROUGH Crustle / Jetting
Blow 0 into Crustle) need the defender-side effect seam, which no parity trace
exercises yet — they land with the pool-wide fan-out (M4). REQ-CGPY-0002.

Not every assertion here is trace-pinned: `test_resistance_reduces_30` sweeps the pool
for a matching pair, and Issue #346's Tool block below is derived from printed card
text. This module is the one home for hand-built `attack_damage` assertions — it owns
`make_state`, the suite's only hand-built cgpy `GameState` — so text-derived damage
gates live here rather than in a second builder somewhere else.
"""
from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

import pytest

from cgpy.cards import CardDB
from cgpy.chain import def_for, load_chain_defs, start_program
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
               defender_bench: Sequence[int] = (),
               attacker_tools: Sequence[int] = (),
               attacker_bench: Sequence[int] = ()) -> GameState:
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
    b0.bench = [mon(c, 0) for c in attacker_bench]
    b1.bench = [mon(c, 1) for c in defender_bench]
    for cid in attacker_tools:                 # attached Pokémon Tool (owner = attacker)
        s = next(serial)
        cards[s] = CardInstance(serial=s, card_id=cid, owner=0)
        b0.active.tools.append(s)
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
                        gs.players[1].active, adef=adef)
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


# --------------------------------------------------------------- attached-Tool bonuses
# Issue #346. `damage.attack_damage` adds an attached Tool's `tool.attackBonus["n"]` to the
# opposing Active, pre-W/R, subject to TWO independent gates read off the ChainDef:
# `defenderEx` (the defending Active must be a Pokémon {ex}) and `holder` (a `_card_matches`
# filter on the attacker). Brave Bangle prints BOTH and its def carried only the holder half,
# so the twin credited +30 against every Active. The cast is `src/agents/slowking/deck.csv` —
# the one shipped deck that runs Brave Bangle — and every pair below is W/R-neutral
# (attacker energyType {P}=5 matches no listed weakness or resistance), so the printed
# attack damage is the whole baseline and any delta is the Tool.

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
    """Brave Bangle (1175), verbatim from `data/EN_Card_Data.csv`:

        "If the Pokémon this card is attached to doesn't have a Rule Box, the attacks it
        uses do 30 more damage to your opponent's Active Pokémon {ex} (before applying
        Weakness and Resistance). (Pokémon {ex}, Pokémon {V}, etc. have Rule Boxes.)"

    Two gates, so four combinations and exactly one payout. Row 2 is the regression: with
    `defenderEx` absent from the ChainDef it read 150, a phantom +30 against every Active.
    """
    assert _tool_damage(holder, attack_id, defender, BRAVE_BANGLE) == expected, why


def test_a_Mega_Evolution_Pokemon_ex_counts_as_a_Pokemon_ex_for_the_defender_gate():
    """`docs/rulebook.txt` Appendix 1: "Mega Evolution Pokémon ex are considered to be
    Pokémon ex, so any card effects that affect Pokémon ex also affect Mega Evolution
    Pokémon ex." Mega Kangaskhan ex carries `megaEx` and NOT `ex`, so a gate testing only
    `ex` would silently exclude the 300-HP bodies the boost matters most against."""
    assert DB.card(MEGA_KANGASKHAN_EX).megaEx and not DB.card(MEGA_KANGASKHAN_EX).ex
    assert _tool_damage(SLOWKING, SUPER_PSY_BOLT, MEGA_KANGASKHAN_EX, BRAVE_BANGLE) == 150


def test_maximum_belt_proves_the_defenderEx_gate_is_LIVE_on_this_path():
    """The positive control for the instrument, not for the card. If `defenderEx` were dead
    code — read from a def that `def_for` never returns, or short-circuited before the tool
    loop — the four assertions above could go green on a change that does nothing. Maximum
    Belt (1158) prints the identical `{ex}` restriction with no holder gate and its def has
    always carried the flag, so it must swing 50/0 across the SAME two defenders through the
    SAME helper. A silent instrument fails here first."""
    assert _tool_damage(SLOWKING, SUPER_PSY_BOLT, LATIAS_EX, MAXIMUM_BELT) == 170
    assert _tool_damage(SLOWKING, SUPER_PSY_BOLT, METAGROSS, MAXIMUM_BELT) == 120


def test_every_attackBonus_Tool_agrees_with_its_printed_ex_restriction():
    """The whole `tool.attackBonus` inventory, both directions — a one-card fix that leaves a
    sibling wrong is the same bug filed twice.

    The card table is the authority: a def carries `defenderEx` if and only if its text prints
    "Active Pokémon {ex}". Three tools qualify today — Maximum Belt (True/True), Hop's Choice
    Band (False/False) and Brave Bangle, the row this issue moved from False/True.

    Reads the inventory through `chain.load_chain_defs()` itself, NOT through a local re-merge
    of the two JSON files. A copy of the merge order would leave the sweep blind to the one
    drift it most needs to see: overrides ceasing to win over `generated_chains.json` would
    silently restore the unflagged seed def while this test stayed green.

    The sweep also carries a positive control in the assertion: BOTH directions must be
    populated. An instrument that silently matched nothing — wrong path, a text probe defeated
    by the table's U+00A0 and U+2019 — would report a vacuous all-clear, so
    `agree_true`/`agree_false` being non-empty is asserted, not assumed.

    NOT in this inventory, and deliberately: Light Ball (1178) prints the same `{ex}` clause
    but its def carries `"deferred": "tool passive unpinned"` (plus the raw `_seed` text) and no
    `attackBonus` at all, so there is no flag to disagree with. It is a modelling gap, not a
    gate mismatch — no shipped deck runs it and `deferred` is the file's own record of that.
    The turn-marker family (Kieran 1191, Black Belt's Training 1211) spells the same restriction
    `defenderExOnly` under `play`, a different key on a different mechanism; `damage.py` reads
    both.
    """
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


# ------------------------------------------------- the open FILTERED-COUNT family (Issue #361)
# ADR-TEMP-361 grew the agent-side scaler vocabulary a filtered-count FORM: `scaleVar` names the
# family and `AttackStat.scaleFilter` carries the predicate's argument. Two implementations of one
# predicate now exist — `cgpy.damage.attack_damage`'s `scale` leg and
# `common.strategy.damage.compute_active_damage` — and two implementations of one fact are the thing
# most likely to drift, so these assert they AGREE board-for-board rather than each asserting a
# number it computed itself. The engine names its members differently (`atk_named_attack` vs
# `atk_in_play_with_attack`) and always has (`all_bench` vs `both_bench`, `atk_discard_basic_energy`
# vs `atk_discard_energy`): the contract between the two vocabularies is the VALUE, not the spelling.

TR_KOFFING, TR_WEEZING = 461, 462       # the pool's ONLY two "Koffing"/"Weezing" names
TYMPOLE, PALPITOAD, SEISMITOAD = 500, 501, 502
REGIGIGAS = 251                         # neutral defender: weakness {F}=6, no Resistance, no
                                        # Ability, no `defense` ChainDef — so nothing but the
                                        # scaling term moves the number for a {D}/{W} attacker
EXPLODE, ROUND_708 = 651, 708


def _agent_damage(gs: GameState, attack_id: int) -> float:
    """The AGENT's oracle on the same board — shipped `attack_overrides.json` and all.

    `build_attack_stats` is pure, so it takes cgpy's own `Attack` records (`attackId`/`name`/`text`/
    `damage`/`energies`) and folds the SHIPPED override table over them. That is the point: this is
    the table CI ships, not a fixture that could agree with the engine while the table does not.
    """
    from common.scouting.provider import (CardStat, build_attack_stats, load_attack_overrides)
    from common.strategy.damage import compute_active_damage
    from common.strategy.damage_context import SideFacts, damage_context

    stats = build_attack_stats(list(DB.attacks.values()), load_attack_overrides())

    def side(seat: int) -> SideFacts:
        bodies = gs.in_play(seat)
        return SideFacts(
            in_play_names=tuple(gs.stat(p.top).name for p in bodies),
            in_play_attack_names=tuple(tuple(DB.attacks[a].name for a in gs.stat(p.top).attacks)
                                       for p in bodies))

    def card(p) -> CardStat:
        d = gs.stat(p.top)
        return CardStat(d.cardId, name=d.name, hp=d.hp, energyType=d.energyType,
                        weakness=d.weakness, resistance=d.resistance)

    return compute_active_damage(stats[attack_id], card(gs.players[0].active),
                                 card(gs.players[1].active),
                                 context=damage_context(side(0), side(1)))


@pytest.mark.req("REQ-SCALER-0013")
@pytest.mark.parametrize("mine,theirs,units", [
    ((), (), 1),                                    # the attacker alone — the COMMON board, and the
                                                    # one the frozen {"damage": 80} doubled
    ((TR_KOFFING,), (), 2),
    ((), (TR_WEEZING,), 2),                         # "both yours and your opponent's"
    ((TR_KOFFING, TR_KOFFING), (TR_WEEZING,), 4),
])
def test_explode_together_now_agrees_between_the_engine_and_the_agent(mine, theirs, units):
    """651, verbatim (`data/EN_Card_Data.csv` 462): *"This attack does 40 damage for each Pokémon in
    play that has "Koffing" or "Weezing" in its name (both yours and your opponent's)."* Printed
    `damage: 0` (`src/cgpy/defs/attack_data.json`), so the scaler is the whole number.

    The `units=1` row IS the defect this issue exists for: the attacker matches its own predicate, so
    a lone Team Rocket's Weezing deals 40 and the shipped table used to promise 80."""
    gs = make_state(TR_WEEZING, REGIGIGAS, attacker_bench=list(mine), defender_bench=list(theirs))
    engine = attack_damage(gs, gs.players[0].active, DB.attacks[EXPLODE],
                           gs.players[1].active, adef=def_for(f"attack:{EXPLODE}") or {})
    assert engine == 40 * units
    assert _agent_damage(gs, EXPLODE) == engine


@pytest.mark.req("REQ-SCALER-0013")
@pytest.mark.parametrize("mine,theirs,units", [
    ((), (), 1),
    ((TYMPOLE,), (), 2),
    ((TYMPOLE, SEISMITOAD), (), 3),
    ((), (TYMPOLE, SEISMITOAD), 1),                 # "each of YOUR Pokémon" — theirs never count
])
def test_round_agrees_between_the_engine_and_the_agent(mine, theirs, units):
    """708, verbatim (`data/EN_Card_Data.csv` 501): *"This attack does 40 damage for each of your
    Pokémon in play that has the Round attack."* Printed `damage: 0`.

    Tympole (500/`Round` 707) and Seismitoad (502/`Round` 710) carry the same attack NAME at
    different per-unit values, which is what makes this a name predicate rather than an id list."""
    gs = make_state(PALPITOAD, REGIGIGAS, attacker_bench=list(mine), defender_bench=list(theirs))
    engine = attack_damage(gs, gs.players[0].active, DB.attacks[ROUND_708],
                           gs.players[1].active, adef=def_for(f"attack:{ROUND_708}") or {})
    assert engine == 40 * units
    assert _agent_damage(gs, ROUND_708) == engine


@pytest.mark.req("REQ-SCALER-0013")
def test_the_pool_holds_exactly_the_matching_cards_this_family_was_ruled_against():
    """A positive control for the two predicates above: if the pool held a third "Koffing" name or a
    fifth `Round` the parametrised counts would be reasoning about a board that cannot occur. Asserts
    the predicate's own reach off `card_data.json`, so a set refresh that widens it fails HERE."""
    named = sorted(c.cardId for c in DB.cards.values()
                   if "Koffing" in c.name or "Weezing" in c.name)
    assert named == [TR_KOFFING, TR_WEEZING], "the name predicate's reach moved"
    rounds = sorted(c.cardId for c in DB.cards.values()
                    if any(DB.attacks[a].name == "Round" for a in c.attacks))
    assert rounds == [TYMPOLE, PALPITOAD, SEISMITOAD, 842], "the Round predicate's reach moved"
