"""Blunder round 2026-07-09 (dragapult_ex) — energy color + attach-target discipline.

`fetch-the-attack-color` breaks the starved-fetch tie toward a colour an IN-PLAY attacker needs;
`dont-power-the-draw-engine` keeps Energy off an off-Line draw engine.
"""
import json
import sys
from pathlib import Path

import pytest

from poc_t4_flips import marks

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
    """Every type ties at `fetch-energy-when-starved`, so the attack-colour rung is what breaks it."""
    fx = _fixture("dragapult_fetch_attack_color_f18")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [1] Basic {R} Fire, not [0] Basic {D}
    assert "fetch-the-attack-color" in _fired_ids(dec.options[fx["correct"][0]])


@pytest.mark.req("REQ-GEN-0074")
@pytest.mark.xfail(strict=True, reason=marks("dragapult_dont_feed_draw_engine_f21")[0].kwargs["reason"])
def test_f21_dont_sink_energy_into_the_draw_engine():
    """The role gate zeroes the engine's ATTACK AXIS, so a Colorless attack can no longer make an
    off-colour Energy read as attack progress (ADR-0069) — foreclosed structurally, not penalised."""
    fx = _fixture("dragapult_dont_feed_draw_engine_f21")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    engine = next(r for r in dec.attach_working["eq"] if r["target"] == 305)
    assert engine["role_gated"] is True
    assert engine["attack_axis"] == 0.0 and engine["build"] > 0   # gated, not merely unbuildable
    assert dec.chosen[0] != engine["i"]


@pytest.mark.req("REQ-GEN-0074")
def test_draw_engine_detection_flags_the_engine_line_not_the_single_hop_engines():
    """A base is flagged when its PAYOFF carries `draw`/`stall`, even when the base itself is untagged."""
    p = _pilot("dragapult_ex")
    assert p._is_draw_engine_body(305)                         # Dunsparce -> Dudunsparce
    assert p._is_draw_engine_body(66)                          # Dudunsparce itself
    assert not p._is_draw_engine_body(676)                     # Solrock — no draw, no drawing evolution
    assert p._is_draw_engine_body(675)                         # Lunatone — Lunar Cycle draws
