"""The `_incoming_budget` base_attach sweep (doom-shadow grill follow-up #2) — REQ-BUDGETSWEEP.

The grill proved the pool carries GENERIC supporter accel (Crispin/Waitress, `energy_accel`
Supporters any deck can hold), so the matched-Read charged budget `{base_attach: 1}` is
optimistic-by-one for its OWN consumers — the ±50 survival nudge (`_incoming_worst` /
`_survives_after_ko`), the `-KO_SCORE` loss rung, and the promote stand-down
(`opp_cannot_punish_wincon`) — all of which flow through ONE seam: `combat.reachable_incoming`'s
`charged=` kwarg. The doom read does NOT flow through it (`doomed_incoming` → `incoming` directly,
with its own `_DOOM_CHARGED`), so a `reachable_incoming` wrapper isolates exactly the consumers
under study.

The sweep replays the corrections corpus twice per frame (fresh Pilot each — the cross-game
discipline): stock vs wrapped-upgraded (`base_attach 1 → 2`), and adjudicates decision flips
against the recorded human `correct`. These tests pin the pure core engine-free.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from train.probes.budget_sweep import (  # noqa: E402
    upgrade_charged,
    verdict,
    wrap_reachable,
)


@pytest.mark.req("REQ-BUDGETSWEEP-0001")
def test_upgrade_charged_bumps_only_the_base_1_budget():
    """base_attach 1 → 2, everything else untouched; None (unmatched worst-case) stays None so
    the wrapper can never relax-or-tighten an unmatched read; an already-2 budget is unchanged."""
    assert upgrade_charged({"base_attach": 1, "burst_on_evo": 2}) == {"base_attach": 2,
                                                                      "burst_on_evo": 2}
    assert upgrade_charged(None) is None
    assert upgrade_charged({"base_attach": 2, "burst_on_evo": 2}) == {"base_attach": 2,
                                                                      "burst_on_evo": 2}


@pytest.mark.req("REQ-BUDGETSWEEP-0002")
def test_wrap_reachable_upgrades_the_charged_kwarg_in_place():
    """The wrapper intercepts `reachable_incoming` alone: charged flows through `upgrade_charged`,
    every other argument passes verbatim, and the return value is untouched."""
    seen = {}

    class FakeCombat:
        def reachable_incoming(self, my_body, opp_bodies, **kw):
            seen.update(kw, my_body=my_body)
            return 77

        def doomed_incoming(self, *a, **kw):              # the doom seam — must stay untouched
            return 5

    combat = FakeCombat()
    wrap_reachable(combat)
    out = combat.reachable_incoming({"id": 1}, [], charged={"base_attach": 1, "burst_on_evo": 2},
                                    evo_min_energy=1)
    assert out == 77
    assert seen["charged"] == {"base_attach": 2, "burst_on_evo": 2}
    assert seen["evo_min_energy"] == 1 and seen["my_body"] == {"id": 1}
    # unmatched stays unmatched; the doom seam is not wrapped
    combat.reachable_incoming({"id": 1}, [], charged=None)
    assert seen["charged"] is None
    assert combat.doomed_incoming() == 5


@pytest.mark.req("REQ-BUDGETSWEEP-0003")
def test_verdict_classifies_flips_against_the_human_correct():
    assert verdict([1], [1], correct=[1]) == "SAME"
    assert verdict([0], [1], correct=[1]) == "IMPROVED"    # upgrade reaches the human pick
    assert verdict([1], [0], correct=[1]) == "REGRESSED"   # upgrade loses the human pick
    assert verdict([0], [2], correct=[1]) == "MOVED"       # both wrong, different picks
    assert verdict([0], [0], correct=[1]) == "SAME"        # both wrong, same pick — no signal
    assert verdict([0], [1], correct=None) == "MOVED"      # no label recorded — flip noted only
