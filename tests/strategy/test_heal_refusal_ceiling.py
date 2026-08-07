"""The clutch-heal REFUSAL CEILING — three CRITICAL corpus frames the composer cannot reach.

All three are the same card, refused for the same registered reason: `apply_option` declines to
model Wally's Compassion, whose clauses write attached_energy + damage_counters + my_hand_ids
(Issue #300 `_covers`). So this is a COVERAGE ceiling, not a valuation miss — no scoring change
reaches these frames, and "fixing" them by tuning would be conforming.

The tests come in pairs: a refusal assertion with teeth today, and the human's ruled ACTION kept
verbatim under `xfail(strict=True)` so the day the seam widens, the build fails until they are
promoted.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

WALLYS = 1229           # Wally's Compassion — heal to full, bounce the attached Energy, hand write

#: ``(fixture, the human's ruled option index, what the agent did at capture)``. The literals are
#: documentation; `test_the_fixtures_still_rule_what_this_module_says_they_rule` asserts they agree.
FRAMES = [
    ("planner_0cbc", 5, 3),              # CRITICAL 0cbc: heal instead of the filler card
    ("planner_6858", 3, 1),              # CRITICAL 6858: heal BEFORE the Ignition attach
    ("planner_82227388_43", 7, 12),      # ep82227388 f43: open the clutch-heal turn, not the attack
]


def _shipped_pilot(agent="mega_starmie"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
    return pilot


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _refusal_for(pilot, obs, index):
    """What the apply seam says about taking option ``index`` first, from the shipped leaf model."""
    from common import apply_option as ao
    my_index = int((obs.get("current") or {}).get("yourIndex") or 0)
    model = pilot._leaf_state_model(obs, my_index)
    option = obs["select"]["option"][index]
    return ao.apply_option(model, option, search_api=getattr(pilot, "_search_api", None))


@pytest.mark.req("REQ-PLANNER-0036")
@pytest.mark.parametrize("fixture,ruled,_at_capture", FRAMES)
def test_the_seam_refuses_the_ruled_heal_and_says_why(fixture, ruled, _at_capture):
    """Keeps the pair honest: without it the xfail below could go green for the wrong reason and
    nobody would notice the ceiling had never moved."""
    from common import apply_option as ao
    pilot = _shipped_pilot()
    result = _refusal_for(pilot, _fx(fixture)["obs"], ruled)
    assert isinstance(result, ao.Refusal), (
        f"{fixture}: the seam now MODELS the ruled heal — the ceiling moved. Promote the xfail "
        f"below to a plain assertion and delete this expectation; got {type(result).__name__}")
    assert str(WALLYS) in result.reason and "Effect Clauses" in result.reason


@pytest.mark.req("REQ-PLANNER-0036")
@pytest.mark.parametrize("fixture,ruled,_at_capture", FRAMES)
@pytest.mark.xfail(strict=True, reason=(
    "seam refusal ceiling, not a valuation miss: `apply_option` declines to model Wally's "
    "Compassion (Issue #300 `_covers`), so the ruled play is never a candidate the beam can commit. "
    "strict=True — an unexpected PASS means the seam widened and these must be promoted."))
def test_the_agent_plays_the_ruled_heal(fixture, _at_capture, ruled):
    """The human's ruling, kept verbatim and kept failing until the mechanism can honour it. Pins
    the DECISION, not which rung fired — the assertion that outlives a swap."""
    fx = _fx(fixture)
    assert _shipped_pilot().explain(fx["obs"]).chosen == fx["correct"] == [ruled]


@pytest.mark.req("REQ-PLANNER-0036")
def test_the_fixtures_still_rule_what_this_module_says_they_rule():
    """A fixture re-ruled upstream would leave the parametrisation testing a different option. Also
    asserts the ruled option is the same CARD on all three — that is the finding, not a coincidence."""
    for fixture, ruled, at_capture in FRAMES:
        fx = _fx(fixture)
        assert fx["correct"] == [ruled], f"{fixture}: ruling moved to {fx['correct']}"
        assert fx["chosen"] == [at_capture], f"{fixture}: capture moved to {fx['chosen']}"
        opt = fx["obs"]["select"]["option"][ruled]
        hand = (((fx["obs"].get("current") or {}).get("players") or [])[0] or {}).get("hand") or []
        card = hand[opt["index"]] if opt.get("index", -1) < len(hand) else {}
        assert card.get("id") == WALLYS, f"{fixture}: the ruled play is card {card.get('id')}, not Wally's"
