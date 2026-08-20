"""The preview seam changes plumbing, never judgment: identical prices on real frames."""
from __future__ import annotations

from pathlib import Path

import pytest

from bellman_helpers import deck as agent_deck

from common.engine import CgpyTransitionProvider, LedgerCgpyProvider
from common.ledger import (LedgerContext, LedgerDecider, LedgerNativeProvider, PreviewState,
                           preview_provider_factory)
from common.native_engine import NativeCgTransitionProvider
from common.state import DecisionState
from train.blunder.store import load_corrections

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260813_c9991b12"
DECK = agent_deck("mega_starmie")


def _main_frames(count=3):
    frames = [row for row in load_corrections(STORE)
              if row.obs is not None
              and (row.obs.get("select") or {}).get("context") == 0
              and int((row.obs.get("current") or {}).get("turn", 0)) > 0]
    return frames[:count]


def _decide(frame, factory):
    decider = LedgerDecider(DECK, "mega_starmie", LedgerContext.build(),
                            provider_factory=factory)
    return decider.decide(frame.obs)


@pytest.mark.parametrize("frame", _main_frames(), ids=lambda row: row.id)
def test_preview_seam_prices_identically_to_the_decisionstate_path(frame):
    heavy = _decide(frame, CgpyTransitionProvider)
    light = _decide(frame, LedgerCgpyProvider)
    assert light.chosen == heavy.chosen
    assert light.diagnostics["prices"] == heavy.diagnostics["prices"]
    assert light.diagnostics["gaps"] == heavy.diagnostics["gaps"]


def test_preview_state_enumerates_the_same_menu_as_decisionstate():
    frame = _main_frames(1)[0]
    state = DecisionState.from_observation(frame.obs, deck=DECK, deck_name="mega_starmie")
    preview = PreviewState(frame.obs, state.root_seat, "preview:0")
    assert preview.legal_actions == state.legal_actions


def test_factory_mapping_targets_the_preview_variants():
    from functools import partial
    assert preview_provider_factory(None) is LedgerNativeProvider
    assert preview_provider_factory(NativeCgTransitionProvider) is LedgerNativeProvider
    assert preview_provider_factory(CgpyTransitionProvider) is LedgerCgpyProvider
    mapped = preview_provider_factory(partial(NativeCgTransitionProvider, world_count=1))
    assert mapped.func is LedgerNativeProvider and mapped.keywords == {"world_count": 1}
    sentinel = object()
    assert preview_provider_factory(sentinel) is sentinel
