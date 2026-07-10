"""Blunder round 2026-07-09 (dragapult_ex) — play-energy-denial: threat- and KO-aware gating.

Proposal `play-energy-denial-threat-and-ko-aware` (data/strategy/proposals/blunder-20260709-dragapult_ex.md).
Two gate fixes to `play-energy-denial` (baseline_disruption.py), both keyed on signals that separate a
worthwhile strip from a wasted Item:

  - fix (b), f6: gate on `opp_active_can_damage_us` — the opponent's Active, with its CURRENT Energy, has
    an AFFORDABLE attack dealing >0 to us (oracle-resolved). Kyogre's Riptide off an empty discard computes
    to 0 and its Swirling Waves is unaffordable, so it cannot hurt us — the strip is worthless. Flips f6
    (Crushing Hammer -> Poké Pad).
  - fix (a): the KO stand-down now keys on `active_can_ko` (BEST affordable attack) instead of only
    `active_cheap_attack_kos` (cheapest) — so a deck whose KO comes from an EXPENSIVE attack (dragapult's
    Phantom Dive; Mega Starmie's Nebula Beam) also holds the Item. Synthetic proof below.

f32 (the third fixture) is deliberately SPLIT OUT: the opp there (Cynthia's Gabite, Dragonslice {F} 40) CAN
damage us, so no damage-gate stands the strip down without also breaking the legitimate race/setup strips
(test_blunder_20260629 :239/:257). It is a distinct DEVELOP-PRIORITY finding (advance the wincon line over a
marginal non-survival strip) routed to its own proposal.
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


@pytest.mark.req("REQ-GEN-0031")
def test_f6_hold_the_hammer_vs_a_harmless_conditional_attacker():
    """f6: opp Active Kyogre carries 1 Water but its only affordable attack (Riptide) scales off its
    EMPTY discard -> 0, and Swirling Waves is unaffordable. `opp_active_can_damage_us` is False, so
    play-energy-denial stands down and the Crushing Hammer is held (develop with Poké Pad instead)."""
    fx = _fixture("dragapult_hammer_no_threat_f6")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [2] Poké Pad, not [1] Crushing Hammer
    assert "play-energy-denial" not in _fired_ids(dec.options[1])   # the Hammer no longer endorsed
