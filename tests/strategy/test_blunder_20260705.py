"""Blunder round 2026-07-05 (mega_lucario) — real-replay regression gates on setup resource discipline.

Replayed through the SHIPPED Pilot at SEED weights (no tuned.json).
"""
import json
import sys
from pathlib import Path

import pytest

from poc_t4_flips import marks

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_lucario")
    return pilot


def _fixture(name):
    p = REPO / "tests" / "fixtures" / "corrections" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _fired_ids(option):
    return {h.id for h, _w in option.fired}


@pytest.mark.req("REQ-GEN-0068")
def test_critical_f9_energy_beats_a_redundant_engine_grab_when_starved():
    """`fetch-energy-when-starved` must DOMINATE the engine/starter grabs at a TO_HAND search."""
    fx = _fixture("ml0705_starved_solrock_f9")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # the Basic {F} Energy


@pytest.mark.req("REQ-GEN-0069")
def test_critical_f14_never_play_a_damage_boost_when_it_cannot_attack():
    """A boost that cannot be cashed changes no end-of-turn board, so the composer prices it at nothing
    — EMERGENT since `dont-play-damage-boost-when-cant-attack` was deleted (Issue #386 §4)."""
    fx = _fixture("ml0705_ppp_cant_attack_f14")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # End turn
    ppp = fx["chosen"][0]
    assert dec.options[ppp].score <= 0, (
        "the dead boost is priced at or above zero — End no longer wins on the numbers, so this "
        "frame would be passing by tie-break rather than by valuation")


@pytest.mark.req("REQ-GEN-0070")
def test_critical_f27_refresh_wins_the_supporter_slot_over_a_needless_tutor():
    """`demote-needless-search-supporter-in-setup` neutralises the tutor's dig endorsement so the
    refresh wins the mutually-exclusive Supporter slot."""
    fx = _fixture("ml0705_petrel_over_lillies_f27")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # Lillie's Determination
    petrel = fx["chosen"][0]
    assert "demote-needless-search-supporter-in-setup" in _fired_ids(dec.options[petrel])


@pytest.mark.req("REQ-GEN-0047")
def test_critical_f44_refill_when_the_held_wincon_is_undeployable():
    """`hold-wincon-dont-shuffle` stands down on `wincon_in_hand_undeployable` — a held payoff with no
    base in play is dead weight."""
    fx = _fixture("ml0705_refill_undeployable_f44")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # Play Lillie's Determination
    lillies = fx["correct"][0]
    assert "hold-wincon-dont-shuffle" not in _fired_ids(dec.options[lillies])


@pytest.mark.req("REQ-GEN-0068")
def test_critical_ep2_f14_energy_beats_a_redundant_lunatone_when_starved():
    """The starved-fetch sibling of f9, with a redundant Lunatone as the distractor."""
    fx = _fixture("ml0705_starved_lunatone_f14")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # the Basic {F} Energy


@pytest.mark.req("REQ-GEN-0071")
@pytest.mark.xfail(strict=True, reason=marks("ml0705_ultraball_starved_f17")[0].kwargs["reason"])
def test_critical_ep2_f17_save_the_costly_tutor_while_starved_and_developed():
    """`dont-costly-tutor-when-starved-and-developed` nets a two-card-discard tutor below End."""
    fx = _fixture("ml0705_ultraball_starved_f17")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # End turn
    ball = fx["chosen"][0]
    assert "dont-costly-tutor-when-starved-and-developed" in _fired_ids(dec.options[ball])
