"""S5 developer rulings on the Mega Starmie composer (Issue #460)."""
from __future__ import annotations

import pytest


@pytest.mark.req("REQ-PLANNER-0012")
@pytest.mark.parametrize(
    ("episode", "frame", "expected"),
    [
        ("82752045", 115, 5),  # Nebula Beam takes the last prizes from the active Mega Lucario ex.
        ("85164605", 64, 5),   # Jetting Blow KOs the active Kadabra; Boss adds no terminal prize.
    ],
)
def test_s5_replay_prefers_the_direct_terminal_pick(episode, frame, expected):
    """The replay uses the production leaf seam, not a hand-built score surrogate."""
    from common import composer as cp
    from corpus_helpers import corpus_record
    from train.tune import _build_pilot

    record = corpus_record(episode, frame)
    obs = record.obs
    pilot = _build_pilot("mega_starmie")[0]
    select = obs["select"]
    mine = int((obs.get("current") or {}).get("yourIndex") or 0)
    pilot._board(obs, select)
    result = cp.compose(pilot._leaf_state_model(obs, mine), select["option"],
                        shed=pilot.cost_shed_indices)

    assert result.chosen is not None
    assert result.chosen.first_index == expected
