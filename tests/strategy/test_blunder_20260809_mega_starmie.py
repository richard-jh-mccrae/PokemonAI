"""Approved Mega Starmie correction replays from the 2026-08-09 strategy round."""
from __future__ import annotations

from pathlib import Path

import pytest

from train.blunder.store import load_corrections
from train.tune import _build_pilot
from train.tuner.retest import retest


REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260809_da61a511-dirty"


@pytest.fixture(scope="module")
def pilot():
    return _build_pilot("mega_starmie")[0]


def _correction(episode: int, frame: int):
    return next(c for c in load_corrections(STORE)
                if c.episode_id == episode and c.decision.get("frame") == frame)


@pytest.mark.req("REQ-MEGA-STARMIE-20260809")
@pytest.mark.parametrize("episode,frame", [
    (91393371, 9),   # Pokégear before the Supporter commitment
    (91393371, 38),  # deterministic active KO
    (91393371, 69),  # Wally's before the Energy it returns
    (91394270, 9),   # Pokégear before resource commitment
    (91394270, 12),  # Pokegear before the retreat commitment
])
def test_approved_decision_corrections_replay(pilot, episode, frame):
    result = retest(_correction(episode, frame), pilot)
    assert result["fixed"] is True, result


@pytest.mark.req("REQ-MEGA-STARMIE-20260809")
def test_energyless_promote_chooses_the_free_retreat_supporter(pilot):
    result = retest(_correction(91394270, 102), pilot)
    assert result["chosen_after"] == [1]
