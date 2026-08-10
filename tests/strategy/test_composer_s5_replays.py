"""S5 developer rulings on the Mega Starmie composer (Issue #460)."""
from __future__ import annotations

import pytest


#: Issues #466-#469 (PR #483) unified draw/fetch closed-form composition and re-priced both replays
#: below at the raw composer seam (`cp.compose`, not the full `Pilot.explain` pipeline). Packeted in
#: docs/plans/issue-sequence-466-wave3-packet.md — `82752045|1|decision|115` (leaf) and
#: `85164605|1|decision|64` (decider, "Lillie's now precedes the direct attack") — as unruled flips;
#: neither baseline was recaptured.
_PENDING_REASON = ("Issues #466-#469 (PR #483) re-priced this replay at the composer seam; "
                    "docs/plans/issue-sequence-466-wave3-packet.md, pending developer ruling")


@pytest.mark.req("REQ-PLANNER-0012")
@pytest.mark.parametrize(
    ("episode", "frame", "expected"),
    [
        # Nebula Beam takes the last prizes from the active Mega Lucario ex.
        pytest.param("82752045", 115, 5,
                     marks=pytest.mark.xfail(strict=True, reason=_PENDING_REASON)),
        # Jetting Blow KOs the active Kadabra; Boss adds no terminal prize.
        pytest.param("85164605", 64, 5,
                     marks=pytest.mark.xfail(strict=True, reason=_PENDING_REASON)),
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
