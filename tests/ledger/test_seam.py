"""The preview seam changes plumbing, never judgment: identical prices on real frames."""
from __future__ import annotations

from observation_builders import build_observation, advance_observation

from pathlib import Path

import pytest

from agent_helpers import deck as agent_deck

from common.engine import CgpyTransitionProvider, LedgerCgpyProvider
from common.ledger import (EvaluationModel, LedgerDecider, LedgerNativeProvider, PreviewState,
                           preview_provider_factory)
from common.native_engine import NativeCgTransitionProvider
from deprecated.bellman.state import DecisionState
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


@pytest.mark.parametrize("frame", _main_frames(), ids=lambda row: row.id)
def test_preview_seam_prices_identically_to_the_decisionstate_path(frame):
    """Same frame, same swings: the DecisionState-successor path (built explicitly here — the
    decider itself no longer constructs one) against the live board-native path."""
    from common.observation import ObservationState
    from common.ledger.evaluate import evaluate
    from common.ledger.preview import price_actions

    ctx = EvaluationModel.build()
    board = build_observation(frame.obs, decklist=DECK)
    baseline = evaluate(board, ctx).total
    heavy_state = DecisionState.from_observation(frame.obs, deck=DECK,
                                                 deck_name="mega_starmie")
    heavy = price_actions(heavy_state, board, baseline,
                          CgpyTransitionProvider(heavy_state), ctx)

    light_decider = LedgerDecider(DECK, "mega_starmie", EvaluationModel.build(),
                                  provider_factory=LedgerCgpyProvider)
    light = light_decider.decide(frame.obs)

    heavy_prices = {str(price.action.identity): round(price.swing, 12) for price in heavy}
    light_prices = {entry["action"]: round(entry["swing"], 12)
                    for entry in light.diagnostics["prices"]}
    assert light_prices == heavy_prices


def test_the_ledger_path_constructs_no_decisionstate(monkeypatch):
    """The boundary itself, pinned: a full live decision through the seam never touches the
    legacy state layer."""
    frame = _main_frames(1)[0]
    calls = []
    original = DecisionState.from_observation.__func__

    def counting(cls, *args, **kwargs):
        calls.append(1)
        return original(cls, *args, **kwargs)

    monkeypatch.setattr(DecisionState, "from_observation", classmethod(counting))
    decider = LedgerDecider(DECK, "mega_starmie", EvaluationModel.build(),
                            provider_factory=LedgerCgpyProvider)
    decision = decider.decide(frame.obs)
    assert decision.diagnostics["backend"] == "ledger"
    assert calls == []


def test_preview_state_enumerates_the_same_menu_as_decisionstate():
    frame = _main_frames(1)[0]
    state = DecisionState.from_observation(frame.obs, deck=DECK, deck_name="mega_starmie")
    preview = PreviewState(frame.obs, state.root_seat, "preview:0")
    assert preview.legal_actions == state.legal_actions


def test_the_preview_seam_refuses_multiple_hidden_worlds():
    """Identity keys never merge worlds, so choosing per-world inside a forced menu would
    decide on facts the player cannot know (strategy fusion) — construction refuses before it
    ever opens an engine session."""
    frame = _main_frames(1)[0]
    state = PreviewState(frame.obs, 0, "root", deck=DECK)
    with pytest.raises(ValueError):
        LedgerNativeProvider(state, world_count=4)


def test_factory_mapping_targets_the_preview_variants():
    from functools import partial
    assert preview_provider_factory(None) is LedgerNativeProvider
    assert preview_provider_factory(NativeCgTransitionProvider) is LedgerNativeProvider
    assert preview_provider_factory(CgpyTransitionProvider) is LedgerCgpyProvider
    mapped = preview_provider_factory(partial(NativeCgTransitionProvider, world_count=1))
    assert mapped.func is LedgerNativeProvider and mapped.keywords == {"world_count": 1}
    sentinel = object()
    assert preview_provider_factory(sentinel) is sentinel
