"""Pinned real engine frames through the live runtime: legality and determinism, never the
specific choice — that churns with every training round and is the dashboard's job to grade."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_helpers import deck as agent_deck, strategy as agent_strategy

from common.engine import CgpyTransitionProvider
from common.options import enumerate_legal_actions
from common.runtime import build_runtime
from train.blunder.store import load_corrections

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260813_c9991b12"


@pytest.fixture(scope="module")
def live_runtime():
    return build_runtime(agent_strategy("mega_starmie"), agent_deck("mega_starmie"),
                         provider_factory=CgpyTransitionProvider)


def _main_frames(count=2):
    frames = [row for row in load_corrections(STORE)
              if row.obs is not None
              and (row.obs.get("select") or {}).get("context") == 0
              and int((row.obs.get("current") or {}).get("turn", 0)) > 0]
    return frames[:count]


@pytest.mark.parametrize("frame", _main_frames(), ids=lambda row: row.id)
def test_ledger_answers_a_real_frame_legally_and_identically(live_runtime, frame):
    first = live_runtime.decide(frame.obs)
    second = live_runtime.decide(frame.obs)
    legal = {action.selection for action in enumerate_legal_actions(frame.obs)}
    assert first.diagnostics["backend"] == "ledger"
    assert first.chosen in legal
    assert first.chosen == second.chosen
    assert first.value == second.value
