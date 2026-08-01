"""Blunder round 2026-07-09 (dragapult_ex) — line-readiness: the multi-stage-line distance fix.

Proposal `line-readiness-signals-model-the-multi-stage-line` (data/strategy/proposals/
blunder-20260709-dragapult_ex.md). Dreepy -> Drakloak -> Dragapult ex is the corpus's FIRST 2-stage
Line, and three win-condition-readiness signals were written against single-hop lines where "a Line
pre-evo in play" == "the payoff is ONE evolution from ready". A new helper
`_payoff_immediate_preevo_set` (the payoff's IMMEDIATE pre-evo — Drakloak, NOT the Stage-0 Dreepy)
makes them distance-aware:

  - f31 (CRITICAL, promote): `_evolve_to_ready_wincon_available` now needs the IMMEDIATE pre-evo on
    the Bench; with only a Stage-0 Dreepy it stands down, so `prefer-wincon-line-piece` no longer
    promotes the bare Dreepy and `promote-the-staller` (now firing on `item_lock`) brings up Budew.
  - f85 (attach): `_priority_wincon_slot` falls to the most-energized Line PRE-EVO short of the
    payoff cost when no wincon BODY is buildable, so `concentrate-energy-on-wincon` finishes the
    started 1-Energy Dreepy instead of `power-up-attacker` dribbling onto a bare Dreepy.

f14 (the third cluster member) is deliberately SPLIT OUT (grill 2026-07-09): the distance fix stops
the CRITICAL strand (a two-hop Dragapult ex is no longer grabbed), but landing on Budew specifically
over a redundant 2nd Dreepy needs a separate develop-preference rule (routed to its own proposal).
This file pins only the strand-stop for f14.

Single-hop decks (mega_starmie / mega_lucario) are inert by construction: the immediate pre-evo IS
the only Line pre-evo, so the three signals are unchanged there.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _pilot(deck):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(deck)
    return pilot


def _fixture(name):
    p = REPO / "tests" / "fixtures" / "corrections" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _fired_ids(option):
    return {h.id for h, _w in option.fired}


@pytest.mark.req("REQ-GEN-0073")
def test_f31_promote_item_lock_staller_over_bare_stage0_base():
    """CRITICAL f31: Active KO'd; bench = [Stage-0 Dreepy(1e), Budew, Dunsparce], Dragapult ex in
    hand. The bench pre-evo is TWO hops from ready, so `_evolve_to_ready_wincon_available` stands
    down -> `prefer-wincon-line-piece` drops the bare Dreepy and the promote/retreat decider brings
    up Budew, keeping the fragile Dreepy line safe."""
    fx = _fixture("dragapult_promote_over_fragile_base_f31")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [1] Budew, not [0] the bare Dreepy
    # `promote-the-staller` is DELETED (ADR-0100 §6a): a disposable staller decomposes with no
    # remainder into terms the decider already builds, so the pick is emergent rather than runged.


@pytest.mark.req("REQ-GEN-0073")
def test_f85_concentrate_on_the_started_line_preevo():
    """f85: Active Dragapult ex is fully powered (no wincon BODY buildable); bench has a started
    1-Energy Dreepy and a bare Dreepy. `_priority_wincon_slot` Pass 2 points at the started Dreepy,
    so `concentrate-energy-on-wincon` finishes it toward Phantom Dive rather than `power-up-attacker`
    spreading onto the bare body."""
    fx = _fixture("dragapult_concentrate_line_preevo_f85")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [3] the started Dreepy
    # `concentrate-energy-on-wincon` is DELETED (#139, ADR-0069): concentration falls out of the
    # convex typed build, so the started Line pre-evo simply out-builds the bare one.
    assert next(r for r in dec.attach_working["eq"]
                if r["i"] == fx["correct"][0])["build"] > 0


@pytest.mark.req("REQ-GEN-0073")
def test_f14_strand_is_stopped_even_though_budew_preference_is_split_out():
    """f14 (partial — split out): the distance fix makes `wincon_base_deployable` require the
    IMMEDIATE pre-evo (Drakloak, here in the discard), so `fetch-base-before-stranded-payoff` fires
    and the two-hop Dragapult ex is NO LONGER grabbed. The specific Budew-over-redundant-Dreepy
    landing is a separate develop-preference proposal, so we pin only the CRITICAL strand-stop."""
    fx = _fixture("dragapult_fetch_stranded_payoff_f14")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen != fx["chosen"]                          # not [6] Dragapult ex (the stranded payoff)


@pytest.mark.req("REQ-GEN-0073")
@pytest.mark.parametrize("deck", ["mega_starmie", "mega_lucario"])
def test_single_hop_immediate_preevo_equals_line_preevo(deck):
    """Inert by construction for single-hop lines: the payoff's IMMEDIATE pre-evo IS the only Line
    pre-evo, so `wincon_base_deployable` / `_evolve_to_ready_wincon_available` are unchanged there."""
    pilot = _pilot(deck)
    assert pilot._payoff_immediate_preevo_set() == pilot._line_preevo_set()


@pytest.mark.req("REQ-GEN-0073")
def test_dragapult_immediate_preevo_is_only_the_stage1():
    """For the 2-stage Dreepy -> Drakloak -> Dragapult ex Line the immediate pre-evo is ONLY Drakloak
    — a strict subset of the Line pre-evos (which also include the Stage-0 Dreepy). That distinction
    is what the distance fix turns on."""
    pilot = _pilot("dragapult_ex")
    assert pilot._payoff_immediate_preevo_set() < pilot._line_preevo_set()
