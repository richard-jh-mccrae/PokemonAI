"""tune._build_pilot rides the shared runtime (ADR-0055) — the mirror class is dead.

Pre-0055 tune.py kept a hand-maintained copy of main.py's kill-switch list, and it HAD
drifted: promote_ko_aware / boost_lethal / brief_preevo shipped ON but the tune-built Pilot
ran them OFF, so every retest (and score_diff, which rides `_build_pilot`) decided with
different backstops than the live agent. This pins the fix: the tune-built Pilot's flags are
exactly the runtime profile resolved through the deck's own params.
"""
import pytest

from common.runtime import PROFILE
from train.tune import _build_pilot


@pytest.mark.req("REQ-TUNER-0012")
def test_tune_pilot_decides_with_the_deployed_profile():
    """REQ-TUNER-0012: for every profile flag, the engine-backed tune Pilot reads
    ``strategy.params.get(flag, PROFILE[flag])`` — identical to the deployed agent's
    resolution, so a retest can never again run a shipped layer dark."""
    pilot, seeds = _build_pilot("mega_starmie")
    for flag, shipped in PROFILE.items():
        expected = pilot.strategy.params.get(flag, shipped)
        if flag == "value_model":
            assert (pilot.value_model is not None) == bool(expected)
            continue
        assert getattr(pilot, flag) == expected, f"{flag}: tune != deployed profile"
    assert seeds                        # authored seed weights still come back beside the Pilot
    assert pilot.scout is not None      # the Read stays wired (posture/favorability alive)
    assert pilot.briefs                 # Matchup Briefs stay wired
