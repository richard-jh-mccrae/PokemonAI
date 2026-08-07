"""The clutch-heal REFUSAL CEILING — three CRITICAL corpus frames the composer cannot reach, and why.

POC-T4/5 (Issue #386) deleted `baseline_heal`'s two rungs (`hold-clutch-heal` +60,
`dont-waste-clutch-heal` −40) on the ground that the composer scores heal-then-attack sequences by
construction. It does — but not on these three, and the reason is worth a module of its own because
it is NOT the one a reader assumes.

**All three frames are the same card, refused for the same registered reason.** Every one is a
mega_starmie board where the human ruled *play Wally's Compassion first*, and on every one the apply
seam declines to model that card at all::

    1229 Wally's Compassion: its Effect Clauses write
    ['attached_energy', 'damage_counters', 'my_hand_ids'] — the structural floor is not the whole
    play, and modelling three quarters of a card is what Issue #300's `_covers` verdict exists to
    prevent

So this is a COVERAGE ceiling, not a valuation miss, and the distinction decides what to do about it:

* A valuation miss would be answerable by scoring — a term the leaf is missing, a weight that is
  wrong. Someone could "fix" these three frames by tuning, and that is precisely the conforming this
  repo forbids.
* A coverage ceiling is answerable ONLY by teaching `apply_option` to write the board Wally's
  produces (heal to full + bounce the attached Energy + the hand write). Until it can, no scoring
  change reaches these frames, because the option is never a candidate the beam can commit.

These three are members of the population Issue #386 §2 already counts — *of 92 human-ruled `_PLAY`
frames the composer misses, 76 are REFUSED by the seam* — but they are the three that used to be
CRITICAL regression gates, so they get named rather than left inside an aggregate.

The tests come in pairs, deliberately:

1. ``test_the_seam_refuses_the_ruled_heal_and_says_why`` PASSES today and has teeth today. It asserts
   the refusal and its subject, so "the composer misses this frame" can never quietly become a
   different problem than the one measured here.
2. ``test_the_agent_plays_the_ruled_heal`` is ``xfail(strict=True)`` and carries the human's ruled
   ACTION verbatim. It is not deleted, and it is not softened to something the agent already does.
   ``strict`` is the point: the day the seam learns to write a multi-clause heal, these turn into
   unexpected PASSES and fail the build until someone comes back and promotes them.

Prior art for the shape: `test_sound_rules.py`'s detector + positive-control pairing.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

WALLYS = 1229           # Wally's Compassion — heal to full, bounce the attached Energy, hand write

#: ``(fixture, the human's ruled option index, what the agent did at capture)``. The ruled index is
#: re-read from the fixture at run time; the literal here is documentation, and
#: `test_the_fixtures_still_rule_what_this_module_says_they_rule` asserts the two agree — a fixture
#: re-ruled upstream must not silently turn this module into a test of nothing.
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
    """The finding, asserted rather than described: on each frame the seam REFUSES the human's ruled
    play, and the refusal names Wally's Compassion and the clause set that defeats it.

    This is what keeps the pair honest. Without it, the xfail below could go green for the wrong
    reason — the agent stumbling onto index 5 for unrelated reasons on a re-tuned board — and nobody
    would notice that the ceiling this module documents had never moved."""
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
    """The human's ruling, kept verbatim and kept failing until the mechanism can honour it.

    Each of these was a hard CRITICAL regression gate under the rung ladder: `hold-clutch-heal` (+60)
    made the agent play Wally's, and the tests asserted the rung fired. That assertion pinned an
    implementation. THIS one pins the decision — what the agent played — which is the assertion that
    outlives a swap, and which the composer does not currently satisfy."""
    fx = _fx(fixture)
    assert _shipped_pilot().explain(fx["obs"]).chosen == fx["correct"] == [ruled]


@pytest.mark.req("REQ-PLANNER-0036")
def test_the_fixtures_still_rule_what_this_module_says_they_rule():
    """A guard on the table above. Every claim here rests on the human's `correct` index, and a
    fixture re-ruled upstream would leave the parametrisation quietly testing a different option
    than the prose describes. Also asserts the ruled option really is the same card on all three —
    "one card, three frames" is the finding, so it cannot be left as an unchecked coincidence."""
    for fixture, ruled, at_capture in FRAMES:
        fx = _fx(fixture)
        assert fx["correct"] == [ruled], f"{fixture}: ruling moved to {fx['correct']}"
        assert fx["chosen"] == [at_capture], f"{fixture}: capture moved to {fx['chosen']}"
        opt = fx["obs"]["select"]["option"][ruled]
        hand = (((fx["obs"].get("current") or {}).get("players") or [])[0] or {}).get("hand") or []
        card = hand[opt["index"]] if opt.get("index", -1) < len(hand) else {}
        assert card.get("id") == WALLYS, f"{fixture}: the ruled play is card {card.get('id')}, not Wally's"
