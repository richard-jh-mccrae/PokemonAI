"""The clutch-heal corpus after Wally's full choice synthesis (Issue #455).

The seam now reaches all three boards. Two human actions become ordinary regression pins; the
remaining 0cbc disagreement is explicitly a valuation question, not a hidden coverage ceiling.
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
    return ao.apply_option(model, option, expand_deferred_targets=True,
                           search_api=getattr(pilot, "_search_api", None))


def _healed_zones(expectation):
    zones = set()
    for outcome in expectation.classes:
        current = outcome.model.source_obs.get("current") or {}
        me = ((current.get("players") or [{}])[0] or {})
        for zone in ("active", "bench"):
            if any(int(body.get("hp") or 0) == int(body.get("maxHp") or 0)
                   and not (body.get("energies") or ()) for body in (me.get(zone) or ())):
                zones.add(zone)
    return zones


@pytest.mark.req("REQ-PLANNER-0036")
@pytest.mark.parametrize("fixture,ruled,_at_capture", FRAMES)
def test_the_seam_models_the_ruled_heal(fixture, ruled, _at_capture):
    """All listed Wally options now enter the choice node rather than stopping at the point seam."""
    from common import apply_option as ao
    pilot = _shipped_pilot()
    result = _refusal_for(pilot, _fx(fixture)["obs"], ruled)
    assert isinstance(result, ao.Expectation), (
        f"{fixture}: expected the Wally choice synthesis, got {type(result).__name__}")
    if fixture == "planner_0cbc":
        assert len(result.classes) == 2 and _healed_zones(result) == {"active", "bench"}


@pytest.mark.req("REQ-PLANNER-0036")
@pytest.mark.parametrize("fixture,ruled,_at_capture", FRAMES[1:])
def test_the_agent_plays_the_promoted_ruled_heal(fixture, _at_capture, ruled):
    """Two former refusal cases now reproduce the human's decision without an exemption."""
    fx = _fx(fixture)
    assert _shipped_pilot().explain(fx["obs"]).chosen == fx["correct"] == [ruled]


@pytest.mark.req("REQ-PLANNER-0036")
@pytest.mark.parametrize("fixture,ruled,_at_capture", FRAMES[:1])
def test_global_retirement_defers_the_remaining_heal_valuation(
        fixture, _at_capture, ruled):
    """Issue #459 leaves 0cbc's immutable ruling intact while composer valuation is deferred."""
    fx = _fx(fixture)
    d = _shipped_pilot().explain(fx["obs"])
    assert fx["correct"] == [ruled] and d.options[ruled].card_id == WALLYS
    assert d.options[ruled].score == 0.0


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
