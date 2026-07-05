"""Blunder round 2026-07-05 (mega_lucario) — real-replay regression gates (/blunder-buster).

All six corrections this round carried the uppercase CRITICAL marker (setup resource discipline).
Each test replays a captured state through the SHIPPED Pilot (the exact `tune._build_pilot`
construction, SEED weights — no tuned.json) and pins the fix. Two of these depend on a
`_finish_turn_last` sequencing THRESHOLD, not a ranking margin (Petrel f27, the undeployable-wincon
refill f44), so they gate here rather than via the weight fit — see the rule rationales.
"""
import json
import sys
from pathlib import Path

import pytest

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
    """CRITICAL ('we need energy, be sure to fetch it with this'): at a TO_HAND search with Riolu
    unpowered and no Energy in hand, the agent grabbed a redundant Solrock (engine already down) over
    the Basic {F} Energy it needed. `fetch-energy-when-starved` (+35) now DOMINATES the engine/starter
    grabs, so the Energy wins."""
    fx = _fixture("ml0705_starved_solrock_f9")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # the Basic {F} Energy


@pytest.mark.req("REQ-GEN-0069")
def test_critical_f14_never_play_a_damage_boost_when_it_cannot_attack():
    """CRITICAL ('must never play Premium Power Pro when unable to attack this turn'): turn-1-going-
    first with a 0-Energy Riolu and no Energy in hand, the agent played a dead this-turn {F} attack
    boost over End. `dont-play-damage-boost-when-cant-attack` (−12) now nets it below End."""
    fx = _fixture("ml0705_ppp_cant_attack_f14")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # End turn
    ppp = fx["chosen"][0]
    assert "dont-play-damage-boost-when-cant-attack" in _fired_ids(dec.options[ppp])


@pytest.mark.req("REQ-GEN-0070")
def test_critical_f27_refresh_wins_the_supporter_slot_over_a_needless_tutor():
    """CRITICAL ('used Petrel to grab a supporter that we already have in hand. waste'): both Petrel
    (narrow Trainer tutor) and Lillie's (refresh) tied at `dig-before-commit` +20, and
    `_finish_turn_last` sequenced the non-shuffle Petrel (tier 1) ahead of the tier-3 refresh.
    `demote-needless-search-supporter-in-setup` (−20) neutralises Petrel's dig endorsement so it drops
    to tier 4, and the refresh — the human's `correct` — wins the mutually-exclusive Supporter slot."""
    fx = _fixture("ml0705_petrel_over_lillies_f27")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # Lillie's Determination
    petrel = fx["chosen"][0]
    assert "demote-needless-search-supporter-in-setup" in _fired_ids(dec.options[petrel])


@pytest.mark.req("REQ-GEN-0047")
def test_critical_f44_refill_when_the_held_wincon_is_undeployable():
    """CRITICAL ('hand contains mega lucario, we have no riolu in play, thus its worthless … should
    refill hand'): the agent ended the turn holding a Mega Lucario ex with no Riolu anywhere, because
    `hold-wincon-dont-shuffle` (−25) wrongly held the dead payoff. Gated on the new
    `wincon_in_hand_undeployable`, the hold now stands down and the refresh (the human's `correct`) is
    chosen."""
    fx = _fixture("ml0705_refill_undeployable_f44")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # Play Lillie's Determination
    lillies = fx["correct"][0]
    assert "hold-wincon-dont-shuffle" not in _fired_ids(dec.options[lillies])


@pytest.mark.req("REQ-GEN-0068")
def test_critical_ep2_f14_energy_beats_a_redundant_lunatone_when_starved():
    """CRITICAL ('we already have lunatone in hand but dont have any energy … only ever need a single
    lunatone and a single solrock'): the starved-fetch sibling of f9 — the agent grabbed a redundant
    Lunatone over the Energy. `fetch-energy-when-starved` (+35) now wins."""
    fx = _fixture("ml0705_starved_lunatone_f14")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # the Basic {F} Energy


@pytest.mark.req("REQ-GEN-0071")
def test_critical_ep2_f17_save_the_costly_tutor_while_starved_and_developed():
    """CRITICAL ('still just setting up. nothing needs evolving. just save the ultra ball for next
    turn'): energy-starved with a developed Bench, the agent paid Ultra Ball's two-card discard to
    tutor a Pokémon it could not use this turn. `dont-costly-tutor-when-starved-and-developed` (−30)
    nets the play below End — the human's `correct`."""
    fx = _fixture("ml0705_ultraball_starved_f17")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # End turn
    ball = fx["chosen"][0]
    assert "dont-costly-tutor-when-starved-and-developed" in _fired_ids(dec.options[ball])
