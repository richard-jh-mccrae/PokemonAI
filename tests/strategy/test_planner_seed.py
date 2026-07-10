"""ADR-0050 Phase 1 — the Lethal Solver's engine verify seeds the EXACT remaining deck, not a
decklist prefix. Offline unit seam (`Pilot._exact_own_zones`): no native engine, runs on every CI
leg, and pins the SOUNDNESS the prefix lacked (the exact deck/prize split, never a pool-into-deck
over-count that could false-confirm a fetch of a fully-prized card).

Ground truth is the full-information film for correction 84071010:f15 (mega_lucario): of the deck's
TWO Air Balloons (id 1174), exactly ONE is in the deck and ONE is prized — so a Petrel tutor can
fetch exactly one. See docs/adr/0050-multi-step-lethal-verification-tool.md.
"""
import json
from pathlib import Path

import pytest

from common.pilot import Pilot
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

REPO = Path(__file__).resolve().parents[2]
_F15 = REPO / "tests" / "fixtures" / "corrections" / "ml_dead_hand_full_refresh_f15.json"
_DECK = REPO / "src" / "agents" / "mega_lucario" / "deck.csv"
_AIR_BALLOON = 1174
# the full-info film's exact seat-0 prizes at f15 (independent source of truth, not recomputed)
_F15_PRIZES = {675: 1, 677: 1, 1142: 2, 1174: 1, 1227: 1}


def _deck():
    return [int(x) for x in _DECK.read_text(encoding="utf-8").split("\n")[:60]]


def _pilot(deck):
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY)


def _f15_obs():
    return json.loads(_F15.read_text(encoding="utf-8"))["obs"]


def _me(obs):
    cur = obs["current"]
    return cur["players"][cur["yourIndex"]]


@pytest.mark.req("REQ-LETHAL-SEED-0001")
def test_exact_own_zones_keeps_the_prized_copy_out_of_the_deck():
    """The Petrel→Air Balloon lethal is sound only because one Air Balloon is still in the deck. The
    exact seed must place exactly ONE Air Balloon in your_deck (fetchable) and ONE in your_prize —
    the decklist has two, one is prized. A pool-into-deck seed would seat BOTH in the deck: the
    over-count that could false-confirm a win when a needed card is actually all prized."""
    deck = _deck()
    assert deck.count(_AIR_BALLOON) == 2                    # decklist truly has two
    pilot = _pilot(deck)
    obs = _f15_obs()
    obs["own_prizes"] = dict(_F15_PRIZES)
    me = _me(obs)

    your_deck, your_prize = pilot._exact_own_zones(obs, me)

    assert your_deck.count(_AIR_BALLOON) == 1              # exactly one fetchable (NOT the pool's two)
    assert your_prize.count(_AIR_BALLOON) == 1             # the other is prized
    assert len(your_deck) == me["deckCount"]              # exact deck size (search_begin requires it)
    assert len(your_prize) == len(me["prize"])            # exact prize size


@pytest.mark.req("REQ-LETHAL-SEED-0001")
def test_exact_own_zones_is_none_when_prizes_unanchored():
    """No `own_prizes` on the obs → (None, None): the caller keeps the sound decklist-prefix fallback
    rather than guess a split. A guessed split could seat a prized card in the deck (a false
    confirm), so positive certainty is never asserted without the anchored prizes."""
    pilot = _pilot(_deck())
    obs = _f15_obs()
    obs.pop("own_prizes", None)
    assert pilot._exact_own_zones(obs, _me(obs)) == (None, None)


def _opp(obs):
    cur = obs["current"]
    return cur["players"][1 - cur["yourIndex"]]


@pytest.mark.req("REQ-LETHAL-SEED-0003")
def test_seed_zones_exposes_the_enabler_that_the_prefix_hides():
    """The seeding fix, at the pure decision seam. `deck.csv` is id-sorted, so the decklist prefix
    `deck[:deckCount]` cuts mid-Trainer and hides the high-id Air Balloon (positions 45–46, outside
    deck[:44]); the exact split from `own_prizes` puts the one deck-certain copy back in `your_deck`.
    Same board, opposite reachability — this is the whole seeding gap, engine-free."""
    deck = _deck()
    obs = _f15_obs()
    obs["own_prizes"] = dict(_F15_PRIZES)
    me, opp = _me(obs), _opp(obs)

    exact = _pilot(deck)                                   # lethal_seed_exact defaults ON
    your_deck, _yp, *_ = exact._seed_zones(obs, me, opp)
    assert your_deck.count(_AIR_BALLOON) == 1             # exact seeding: the enabler is reachable
    assert len(your_deck) == me["deckCount"]

    prefix = _pilot(deck)
    prefix.lethal_seed_exact = False                      # kill-switch OFF = the old prefix behavior
    your_deck_p, _yp2, *_ = prefix._seed_zones(obs, me, opp)
    assert your_deck_p == deck[: me["deckCount"]]         # a raw id-sorted prefix …
    assert _AIR_BALLOON not in your_deck_p               # … which hides the enabler


@pytest.mark.req("REQ-LETHAL-SEED-0003")
def test_seed_zones_falls_back_to_prefix_when_unanchored():
    """Kill-switch ON but no `own_prizes`: `_seed_zones` falls back to the prefix rather than seed a
    guessed split. Sound because only non-fetch lines (verdict deck-independent) reach the search
    pre-anchor — the fetch tiers gate on `deck_definitely_has`, which needs the anchor."""
    deck = _deck()
    obs = _f15_obs()
    obs.pop("own_prizes", None)
    pilot = _pilot(deck)                                   # exact ON, but nothing to anchor from
    your_deck, _yp, *_ = pilot._seed_zones(obs, _me(obs), _opp(obs))
    assert your_deck == deck[: _me(obs)["deckCount"]]
