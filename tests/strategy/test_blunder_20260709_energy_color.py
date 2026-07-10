"""Blunder round 2026-07-09 (dragapult_ex) — energy color + attach-target discipline.

Proposal `energy-color-and-attach-target-discipline` (data/strategy/proposals/blunder-20260709-dragapult_ex.md).
The deck's off-color {D} (niche Munkidori fuel) was mishandled twice by the color-blind / attacker-blind
energy signals; two fixes, each keyed on a new signal:

  - f18 (fetch): `fetch-the-attack-color` (+3) breaks the `fetch-energy-when-starved` tie toward a color an
    IN-PLAY attacker needs (`board.in_play_attack_colors`, via AttackStat energy types) — grab the Fire
    for Phantom Dive [Fire, Psychic] and save {D} for when Munkidori is benched.
  - f21 (attach, CRITICAL): `dont-power-the-draw-engine` (-18) penalises attaching to a draw-engine body
    (`attach_target_is_draw_engine`: Dunsparce -> Dudunsparce) that is NOT on the win-condition Line, so
    the {D} goes to the on-Line Dreepy rather than the Dunsparce -> Dudunsparce draw engine.

Inert on the single-hop decks: Solrock/Lunatone draw via an ABILITY (untagged), so the draw-engine rung
never trips, and a mono-color deck's every fetch is on-color.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _pilot(deck):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(deck)[0]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json").read_text(encoding="utf-8"))


def _fired_ids(option):
    return {h.id for h, _w in option.fired}


@pytest.mark.req("REQ-GEN-0074")
def test_f18_fetch_an_on_attack_color_energy_not_the_off_color_utility():
    """f18: at an Energy search every type ties at `fetch-energy-when-starved` +35; `fetch-the-attack-
    color` (+3) tips it to the Fire the in-play Dreepy line needs for Phantom Dive, not the off-color {D}
    (Munkidori's fuel — Munkidori isn't in play)."""
    fx = _fixture("dragapult_fetch_attack_color_f18")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [1] Basic {R} Fire, not [0] Basic {D}
    assert "fetch-the-attack-color" in _fired_ids(dec.options[fx["correct"][0]])


@pytest.mark.req("REQ-GEN-0074")
def test_f21_dont_sink_energy_into_the_draw_engine():
    """f21 (CRITICAL): the only Energy is {D}; Dunsparce's Colorless attack made {D} 'payable', so
    `power-up-attacker` sank it into the Dunsparce -> Dudunsparce DRAW ENGINE. `dont-power-the-draw-engine`
    penalises that attach so the {D} goes to the on-Line Dreepy instead."""
    fx = _fixture("dragapult_dont_feed_draw_engine_f21")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [2] on-Line Dreepy, not [4] Dunsparce
    assert "dont-power-the-draw-engine" in _fired_ids(dec.options[4])   # penalised on the Dunsparce attach


@pytest.mark.req("REQ-GEN-0074")
def test_draw_engine_detection_flags_the_engine_line_not_the_single_hop_engines():
    """`_is_draw_engine_body` flags the Dunsparce -> Dudunsparce line (the base is untagged but its payoff
    carries `draw`/`stall`); it does NOT flag Solrock/Lunatone, whose draw is an Ability (untagged), so
    the rung is inert on mega_lucario. Card facts (Function Tags) are engine ground truth."""
    p = _pilot("dragapult_ex")
    assert p._is_draw_engine_body(305)                         # Dunsparce -> Dudunsparce (draw/stall)
    assert p._is_draw_engine_body(66)                          # Dudunsparce itself
    assert not p._is_draw_engine_body(676)                     # Solrock — Ability-draw, untagged
    assert not p._is_draw_engine_body(675)                     # Lunatone — Ability-draw, untagged
