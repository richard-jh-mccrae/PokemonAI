"""Dead-fetch corpus — the behavioural pin for **Fetch Deadness** (issue #164, ADR-0073).

A search whose entire target class is provably gone from the deck realises no role: playing it
spends a card that had a live later use as discard fodder. `dont-search-an-empty-deck` is the
play-side veto, and this file replays the anchor Correction through the REAL shipped Pilot (fresh
per replay, no cross-fixture state) to pin that the veto holds.

The pin exists because the anchor's fix landed as a SIDE-EFFECT of ADR-0029/0065 work rather than as
a targeted change, and nothing guarded it — a regression would have been silent. Prior art for the
replay style: `test_evolve_valuation_corpus.py`.

Asserted on BEHAVIOUR, never on a magnitude: the dead search is not endorsed (`score > 0` is the
structural act/don't-act floor `_finish_turn_last` already gates on — the same boundary an
Endorsement Claim uses) and is not chosen. Whole-decision equality with the fixture's `correct` is
deliberately NOT asserted here — see the fixture's `note` (the evolve label is #140's question).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"

POFFIN = 1086          # Buddy-Buddy Poffin — "up to 2 Basic Pokémon with 70 HP or less"
STARYU = 1030          # the deck's only Basic at <=70 HP (70), 3 copies, all visible at f78


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def poffin_f78():
    fx = _fixture("mega_starmie_dead_fetch_poffin_f78")
    pilot = _pilot("mega_starmie")
    decision = pilot.explain(fx["obs"])
    return fx, pilot, decision


def _trace_of(decision, card_id):
    """The option trace whose card is ``card_id``, or None."""
    return next((o for o in decision.options if o.card_id == card_id), None)


def test_the_whiff_veto_fires_on_the_target_exhausted_poffin(poffin_f78):
    """The veto is named, not merely inferred from a low score: `dont-search-an-empty-deck` fires on
    the Poffin, because Staryu is PROVABLY gone (3 of 3 visible — 2 bare on the Bench, 1 stacked under
    the Active Mega Starmie ex) and it is the Poffin's only target. Without naming it, this pin would
    pass if the option sank for some unrelated reason, which is not what #164 is about."""
    _fx, _pilot, dec = poffin_f78
    poffin = _trace_of(dec, POFFIN)
    assert poffin is not None, "the Poffin is not on this menu — the fixture's premise changed"
    assert "dont-search-an-empty-deck" in {h.id for h, _w in poffin.fired}


def test_the_dead_poffin_is_not_endorsed(poffin_f78):
    """The play-side veto holds: the target-exhausted Poffin does not clear the endorsement floor."""
    _fx, _pilot, dec = poffin_f78
    poffin = _trace_of(dec, POFFIN)
    assert poffin is not None, "the Poffin is not on this menu — the fixture's premise changed"
    assert poffin.score <= 0, f"dead Poffin endorsed at {poffin.score}: {poffin.fired}"


def test_the_dead_poffin_is_not_chosen(poffin_f78):
    """End to end through the real decision path: the agent does not spend the dead search."""
    fx, _pilot, dec = poffin_f78
    poffin = _trace_of(dec, POFFIN)
    assert poffin is not None
    assert poffin.index not in dec.chosen, (
        f"regression: the agent again chose {fx['chosen_label']} ({dec.chosen})")
