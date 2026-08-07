"""The two engines must price a Stadium's floating HP static identically. Issue #435.

`common/board_delta.py` mirrors the NATIVE engine (its evidence is the 377 committed native traces);
`src/cgpy/` is the pure-Python twin (ADR-0059) that `tools/train/leaf_lab.py` and
`tools/train/decider_lab.py` roll out on. Both carry a function called `stadium_hp_delta`, computing
the same quantity from two different tables — `src/common/card_effects.json`'s clause compendium on
one side, `src/cgpy/defs/`'s ChainDef table on the other. **Nothing checked that they agreed**, and
they did not.

## The divergence this file was written to catch

**Lively Stadium (1251)** — *"Each Basic Pokémon in play (both yours and your opponent's) gets +30
HP"* (`data/EN_Card_Data.csv`). Issue #433 taught `board_delta` to price it (+30 for a Basic);
`cgpy` did not implement the card at all — `def_for(1251)` carried no ``stadium`` key and was flagged
``deferred: "stadium passive unpinned"``, and `chain.stadium_hp_delta` branched on a single
``stage2HpDelta`` key. So the composer said +30 and the rollout engine said 0 for the same board.

No existing test could see it. `tests/parity/test_apply_seam_parity.py` compares `board_delta`
against **recorded native traces**, and 1251 appears in **0 of the 377** — which is exactly why the
gap survived: the corpus is evidence, and where it is silent only a hand-built board can speak.
That is what `tests/cgpy_state_helpers.py` is for.

## Why the sweep is derived rather than enumerated

The sweep reads the `stadium_static` / `hp_delta` clauses out of the compendium instead of naming
1251 and 1252, so a **third** such Stadium — a new set, a re-parse — is compared the day it lands
rather than the day someone remembers this file. The named tests below stay, because a derived sweep
that quietly found nothing would pass just as loudly as one that found everything;
:func:`test_the_cross_engine_sweep_is_not_vacuous` is the positive control that stops that.

## What this does NOT establish

Both `hp_delta` clauses in the pool are ``symmetric: true``, and **neither engine reads that key** —
`board_delta._admits` branches on ``applies_to`` alone and both `stadium_hp_delta` functions take a
body rather than a seat. Both-sides application is therefore *structural* on both sides of the seam,
not configured, and these tests would pass unchanged if a clause said ``symmetric: false``. The
seat-blindness is asserted (every case runs on seat 0 and seat 1); the key's meaning is not. A
``symmetric: false`` static would need a seat dimension in both engines, and none exists in either
— see `tests/strategy/test_lively_stadium_basic.py`, which records the same limitation for the
common side.
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

#: One real body per stage class, from `data/EN_Card_Data.csv`. Riolu -> Mega Lucario ex is a single
#: hop with no intermediate Lucario in this set (`docs/rulebook.txt` Appendix 1), so the Stage 2 has
#: to come from another line — Dragapult ex, the class Gravity Mountain reaches. Every stage is
#: ASSERTED below rather than trusted from the id.
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
    """A board with ``body_cid`` Active on ``seat`` under ``stadium_id``, and ``other`` opposite it.
    Returns ``(gs, body)``.

    The Stadium is always owned by seat 0 while the body under test moves between seats, which is
    what makes every caller a BOTH-SIDES case rather than an own-side one — the seat is the only
    thing that varies, so a modifier that reached only its owner's board would show up as a seat-1
    failure and nothing else."""
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
    """**The gate.** For every Stadium carrying an HP static, every body class, and both seats, the
    composer's price and the twin's price must be the same number.

    This is the test that did not exist. Before Issue #435 it fails on (1251, basic) with the
    composer at +30 and the twin at 0 — the exact board a Kaggle opponent running Lively Stadium
    would have put both engines on."""
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
    """The positive control for the gate above.

    Two ways it could pass while measuring nothing: the derived sweep finds no Stadium, or it finds
    them and every single comparison is `0 == 0` (which is what a *second* forgotten card would look
    like — both engines silent, agreeing perfectly, both wrong). So assert the sweep found the two
    cards the pool actually has, and that it observed a non-zero delta from **each** of them."""
    assert hp_delta_stadiums == (LIVELY_STADIUM, GRAVITY_MOUNTAIN), \
        f"the compendium's HP statics moved to {hp_delta_stadiums} — re-derive this file's fixtures"

    nonzero = {sid for sid in hp_delta_stadiums for stage in BY_STAGE
               if _common_delta(combat, sid, bd._stat(combat, BY_STAGE[stage])) != 0}
    assert nonzero == set(hp_delta_stadiums), \
        f"only {sorted(nonzero)} ever priced non-zero — the rest of the sweep compares 0 to 0"


# ── the card, at its real consumers ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("seat", (0, 1))
def test_lively_stadium_renders_a_basic_at_printed_plus_30_on_both_sides(seat):
    """The claim at the seam that actually feeds the composer: `render.pokemon_dict`, which is what
    turns a cgpy board into the observation dict every equation reads.

    Riolu is 80 HP printed (`data/EN_Card_Data.csv`), so it must render 110/110 under Lively — and
    the STORED body must still be 80/80, because a static is a floating modifier that is never
    written down. That is the invariant `search._fix_stadium_deltas` depends on when it imports a
    native observation: it subtracts the delta to recover the stored value, so a twin that renders
    0 where native rendered +30 would store the body 30 HP too heavy and keep it there after the
    Stadium left."""
    gs, body = _seated(RIOLU, LIVELY_STADIUM, seat)

    printed = DB.card(RIOLU).hp
    assert printed == 80, "Riolu's printed HP moved — re-read `data/EN_Card_Data.csv`"
    assert (body.hp, body.max_hp) == (80, 80), "the static must never be STORED"

    rendered = pokemon_dict(gs, body)
    assert (rendered["hp"], rendered["maxHp"]) == (110, 110)


def test_lively_stadium_leaves_both_evolution_classes_alone():
    """The discriminating half. A def that matched everything would show up here as +30 on a Stage 1
    and a Stage 2, and the Stage 1 is the one that matters most: under Lively, evolving Riolu must
    land Mega Lucario ex on its printed 340, which is precisely what
    `tests/strategy/test_lively_stadium_basic.py` asserts on the composer's side."""
    for cid in (MEGA_LUCARIO_EX, DRAGAPULT_EX):
        gs, body = _seated(cid, LIVELY_STADIUM, 0, other=RIOLU)
        assert pokemon_dict(gs, body)["maxHp"] == DB.card(cid).hp


@pytest.mark.parametrize("seat", (0, 1))
def test_gravity_mountain_still_lowers_a_stage_2_by_30(seat):
    """The regression leg for Issue #435's key change: 1252 moved from a bespoke ``stage2HpDelta``
    key to the general filter-based ``hpDelta``, and it must answer exactly as before.

    Trace-pinned, unlike everything else in this file: `ml_dx_2001` f112 renders a 320-HP Dragapult
    ex at 290 under Gravity Mountain (`cgpy/chain.py:stadium_hp_delta`), and f172/f181 show it back
    at 320/320 once the Stadium leaves — the floating-modifier proof."""
    gs, body = _seated(DRAGAPULT_EX, GRAVITY_MOUNTAIN, seat, other=RIOLU)

    assert DB.card(DRAGAPULT_EX).hp == 320
    assert (body.hp, body.max_hp) == (320, 320), "the static must never be STORED"
    rendered = pokemon_dict(gs, body)
    assert (rendered["hp"], rendered["maxHp"]) == (290, 290)

    # ...and it must not have started reaching Basics on the way through the rewrite.
    basic = gs.players[1 - seat].active
    assert pokemon_dict(gs, basic)["maxHp"] == DB.card(RIOLU).hp


def test_the_twin_can_actually_play_lively_stadium():
    """A def-less Stadium is omitted from the MAIN menu outright — *"un-def'd/deferred stadium:
    option absent -> visible divergence"* (`cgpy/options.py`). So the HP arithmetic is only half the
    card: without a ``stadium`` def the twin could never get 1251 onto the board to price it.

    Gravity Mountain is the **positive control** — a Stadium that was already offered, drawn through
    the identical call, so an empty option list for Lively would mean the card and not the harness.

    The offered option is RESOLVED back to a card id rather than merely counted: a PLAY encodes its
    target as an index into the hand (`{"type": 7, "index": 0}` — no ``area`` key at all), so
    asserting only that the list is non-empty would pass on any play of anything, and would keep
    passing if the hand ever held a second card."""
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
    """`chain.is_deferred` means *known-unmodeled, must never run*. 1251 sat there with
    ``"stadium passive unpinned"`` while `board_delta` priced it, which is the divergence in one
    field.

    The two controls bracket it: 1252 and 1260 were never deferred (they are the two Stadiums the
    committed traces exercise), so this is a claim about 1251 and not about how the table loads."""
    lively = def_for(LIVELY_STADIUM)
    assert lively is not None and "deferred" not in lively, \
        "1251 is still flagged deferred — the twin refuses to run the card it is now defined for"
    assert "stadium" in lively

    for control in (GRAVITY_MOUNTAIN, 1260):
        assert "deferred" not in (def_for(control) or {})
