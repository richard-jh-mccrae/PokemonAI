"""The two engines must price a Stadium's floating HP static identically. Issue #435.

`board_delta` and `cgpy` both carry a `stadium_hp_delta` computing the same quantity from two
different tables, and nothing checked that they agreed. The corpus cannot: a Stadium absent from
every committed trace is exactly where only a hand-built board can speak.

The sweep is DERIVED from the compendium's `stadium_static` / `hp_delta` clauses rather than naming
cards, so a third such Stadium is compared the day it lands.

What this does NOT establish: both clauses are ``symmetric: true`` and NEITHER engine reads that
key — both-sides application is structural, so these tests pass unchanged on ``symmetric: false``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cgpy.chain import def_for, stadium_hp_delta as cgpy_stadium_hp_delta
from cgpy.options import main_options
from cgpy.render import pokemon_dict
from cgpy.schema import CardType, OptionType
from cgpy.state import CardInstance

from common import board_delta as bd

from cgpy_state_helpers import DB, make_state

REPO = Path(__file__).resolve().parents[2]

LIVELY_STADIUM = 1251     # "Each Basic Pokémon in play (both yours and your opponent's) gets +30 HP."
GRAVITY_MOUNTAIN = 1252   # "Each Stage 2 Pokémon in play (both yours and your opponent's) gets -30 HP."

#: One real body per stage class. Riolu -> Mega Lucario ex is a SINGLE hop in this set, so the
#: Stage 2 comes from another line. Every stage is ASSERTED below rather than trusted from the id.
RIOLU, MEGA_LUCARIO_EX, DRAGAPULT_EX = 677, 678, 121
BY_STAGE = {"basic": RIOLU, "stage1": MEGA_LUCARIO_EX, "stage2": DRAGAPULT_EX}


@pytest.fixture(scope="module")
def combat():
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_lucario")
    return pilot.combat


@pytest.fixture(scope="module")
def hp_delta_stadiums() -> tuple[int, ...]:
    """Every card in the compendium carrying a `stadium_static` / `hp_delta` clause — derived, so a
    third one is swept the day it is parsed."""
    effects = json.loads((REPO / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    return tuple(sorted(
        int(card_id) for card_id, clauses in effects.items()
        if isinstance(clauses, list) and any(
            isinstance(c, dict) and c.get("kind") == "stadium_static" and c.get("effect") == "hp_delta"
            for c in clauses)))


def _common_delta(combat, stadium_id: int, stat) -> int:
    """`board_delta`'s price for this body under this Stadium — the shipped read, end to end."""
    clauses = bd.stadium_clauses_of(combat, stadium_id, event=bd.STADIUM_STATIC, stat=stat)
    return bd.stadium_hp_delta(clauses, stat)


def _seated(body_cid: int, stadium_id: int, seat: int, other: int = DRAGAPULT_EX):
    """Returns ``(gs, body)``. The Stadium is always owned by seat 0 while the body moves between
    seats, which is what makes every caller a BOTH-SIDES case rather than an own-side one."""
    if other == body_cid:                      # the sweep grades Dragapult ex against itself
        other = RIOLU if body_cid != RIOLU else DRAGAPULT_EX
    pair = (body_cid, other) if seat == 0 else (other, body_cid)
    gs = make_state(*pair, stadium=stadium_id)
    return gs, gs.players[seat].active


def _twin_delta(stadium_id: int, body_cid: int, *, seat: int) -> int:
    """`cgpy`'s price for the same body under the same Stadium, read off a real board."""
    gs, body = _seated(body_cid, stadium_id, seat)
    return cgpy_stadium_hp_delta(gs, body)


# ── the gate ──────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("stage", sorted(BY_STAGE))
@pytest.mark.parametrize("seat", (0, 1))
def test_the_two_engines_agree_on_every_stadium_hp_static_in_the_pool(
        combat, hp_delta_stadiums, stage, seat):
    """The gate: for every Stadium carrying an HP static, every body class and both seats, the
    composer's price and the twin's price must be the same number."""
    body_cid = BY_STAGE[stage]
    assert bd._stat(combat, body_cid).stage == stage, f"{body_cid}: fixture stage is wrong"

    for stadium_id in hp_delta_stadiums:
        common = _common_delta(combat, stadium_id, bd._stat(combat, body_cid))
        twin = _twin_delta(stadium_id, body_cid, seat=seat)
        assert common == twin, (
            f"stadium {stadium_id} on a {stage} body at seat {seat}: `board_delta` prices "
            f"{common:+d} and `cgpy` prices {twin:+d} — one of the two engines is playing a "
            f"different game")


def test_the_cross_engine_sweep_is_not_vacuous(combat, hp_delta_stadiums):
    """Two ways the gate could pass while measuring nothing: the sweep finds no Stadium, or every
    comparison is `0 == 0` — both engines silent, agreeing perfectly, both wrong."""
    assert hp_delta_stadiums == (LIVELY_STADIUM, GRAVITY_MOUNTAIN), \
        f"the compendium's HP statics moved to {hp_delta_stadiums} — re-derive this file's fixtures"

    nonzero = {sid for sid in hp_delta_stadiums for stage in BY_STAGE
               if _common_delta(combat, sid, bd._stat(combat, BY_STAGE[stage])) != 0}
    assert nonzero == set(hp_delta_stadiums), \
        f"only {sorted(nonzero)} ever priced non-zero — the rest of the sweep compares 0 to 0"


# ── the card, at its real consumers ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("seat", (0, 1))
def test_lively_stadium_renders_a_basic_at_printed_plus_30_on_both_sides(seat):
    """The STORED body must stay at printed HP, because a static is a floating modifier never
    written down — the invariant `search._fix_stadium_deltas` subtracts to recover on import."""
    gs, body = _seated(RIOLU, LIVELY_STADIUM, seat)

    printed = DB.card(RIOLU).hp
    assert printed == 80, "Riolu's printed HP moved — re-read `data/EN_Card_Data.csv`"
    assert (body.hp, body.max_hp) == (80, 80), "the static must never be STORED"

    rendered = pokemon_dict(gs, body)
    assert (rendered["hp"], rendered["maxHp"]) == (110, 110)


def test_lively_stadium_leaves_both_evolution_classes_alone():
    """The discriminating half: a def that matched everything would show up here as +30 on a Stage
    1 and a Stage 2."""
    for cid in (MEGA_LUCARIO_EX, DRAGAPULT_EX):
        gs, body = _seated(cid, LIVELY_STADIUM, 0, other=RIOLU)
        assert pokemon_dict(gs, body)["maxHp"] == DB.card(cid).hp


@pytest.mark.parametrize("seat", (0, 1))
def test_gravity_mountain_still_lowers_a_stage_2_by_30(seat):
    """The regression leg for the key change: 1252 moved from a bespoke ``stage2HpDelta`` to the
    general filter-based ``hpDelta`` and must answer exactly as before. Trace-pinned."""
    gs, body = _seated(DRAGAPULT_EX, GRAVITY_MOUNTAIN, seat, other=RIOLU)

    assert DB.card(DRAGAPULT_EX).hp == 320
    assert (body.hp, body.max_hp) == (320, 320), "the static must never be STORED"
    rendered = pokemon_dict(gs, body)
    assert (rendered["hp"], rendered["maxHp"]) == (290, 290)

    # ...and it must not have started reaching Basics on the way through the rewrite.
    basic = gs.players[1 - seat].active
    assert pokemon_dict(gs, basic)["maxHp"] == DB.card(RIOLU).hp


def test_the_twin_can_actually_play_lively_stadium():
    """A def-less Stadium is omitted from the MAIN menu outright, so the HP arithmetic is only half
    the card. The offered option is RESOLVED back to a card id, since a PLAY encodes only a hand index."""
    for stadium_cid in (LIVELY_STADIUM, GRAVITY_MOUNTAIN):
        assert DB.card(stadium_cid).cardType == CardType.STADIUM
        gs = make_state(RIOLU, DRAGAPULT_EX)
        serial = 900
        gs.cards[serial] = CardInstance(serial=serial, card_id=stadium_cid, owner=0)
        gs.players[0].hand = [serial]

        played = {gs.card_id(gs.players[0].hand[o["index"]])
                  for o in main_options(gs, 0) if o["type"] == int(OptionType.PLAY)}
        assert stadium_cid in played, \
            f"{stadium_cid} {DB.card(stadium_cid).name}: no PLAY option resolved to the Stadium"


def test_lively_stadium_is_no_longer_deferred_in_the_twin():
    """`chain.is_deferred` means known-unmodeled, must never run — the divergence in one field.
    The two controls bracket it, so this is a claim about 1251 and not about how the table loads."""
    lively = def_for(LIVELY_STADIUM)
    assert lively is not None and "deferred" not in lively, \
        "1251 is still flagged deferred — the twin refuses to run the card it is now defined for"
    assert "stadium" in lively

    for control in (GRAVITY_MOUNTAIN, 1260):
        assert "deferred" not in (def_for(control) or {})
