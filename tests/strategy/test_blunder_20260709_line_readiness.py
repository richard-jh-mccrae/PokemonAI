"""Blunder round 2026-07-09 (dragapult_ex) — line-readiness: the multi-stage-line distance fix.

Dreepy -> Drakloak -> Dragapult ex is the corpus's FIRST 2-stage Line, and the readiness signals were
written where "a Line pre-evo in play" == "one evolution from ready". `_payoff_immediate_preevo_set`
makes them distance-aware; single-hop decks are inert by construction.
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
    """The bench pre-evo is TWO hops from ready, so `_evolve_to_ready_wincon_available` stands down."""
    fx = _fixture("dragapult_promote_over_fragile_base_f31")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [1] Budew, not [0] the bare Dreepy
    # `promote-the-staller` is DELETED (ADR-0100 §6a): a disposable staller decomposes with no
    # remainder into terms the decider already builds, so the pick is emergent rather than runged.


@pytest.mark.req("REQ-GEN-0073")
def test_f85_concentrate_on_the_started_line_preevo():
    """With no wincon BODY buildable, `_priority_wincon_slot` Pass 2 points at the started pre-evo."""
    fx = _fixture("dragapult_concentrate_line_preevo_f85")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [3] the started Dreepy
    # `concentrate-energy-on-wincon` is DELETED (ADR-0069): the convex typed build concentrates.
    assert next(r for r in dec.attach_working["eq"]
                if r["i"] == fx["correct"][0])["build"] > 0


@pytest.mark.req("REQ-GEN-0073")
def test_f14_strand_is_stopped_even_though_budew_preference_is_split_out():
    """Only the strand-stop is asserted: WHICH body is grabbed instead is a separate proposal."""
    fx = _fixture("dragapult_fetch_stranded_payoff_f14")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen != fx["chosen"]                          # not [6] Dragapult ex (the stranded payoff)


@pytest.mark.req("REQ-GEN-0073")
@pytest.mark.parametrize("deck", ["mega_starmie", "mega_lucario"])
def test_single_hop_immediate_preevo_equals_line_preevo(deck):
    pilot = _pilot(deck)
    assert pilot._payoff_immediate_preevo_set() == pilot._line_preevo_set()


@pytest.mark.req("REQ-GEN-0073")
def test_dragapult_immediate_preevo_is_only_the_stage1():
    """Drakloak only — a STRICT subset of the Line pre-evos, which is what the distance fix turns on."""
    pilot = _pilot("dragapult_ex")
    assert pilot._payoff_immediate_preevo_set() < pilot._line_preevo_set()
