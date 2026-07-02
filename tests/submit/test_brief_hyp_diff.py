"""The Agent Brief's strategy-change callout: weight / rule / status diffs vs the previous build,
so each iteration shows at a glance what tuning changed (companion to the deck-change callout)."""
from submit.brief import _hyp_diff, render_brief


def _hyp(hid, *, effective, status="assumed", authored=None):
    return {"id": hid, "rationale": "r", "authored": authored if authored is not None else effective,
            "effective": effective, "overridden": authored not in (None, effective),
            "status": status, "trigger": "lambda c: True"}


def _manifest(strategy, general):
    return {
        "provenance": {"agent": "mega_starmie", "built_at": "2026-01-01T00:00:00", "git_hash": "abc",
                       "artifact": "mega_starmie_20260101_abc"},
        "capabilities": {"tier": 0, "card_functions": {"present": True}, "posture": {"enabled": False},
                         "overrides": {"count": 1}},
        "deck": {"size": 0, "cards": []},
        "strategy": {"name": "mega_starmie", "hypotheses": strategy},
        "general_strategy": {"hypotheses": general},
    }


def test_hyp_diff_detects_weight_rule_and_status_changes():
    """REQ-BRIEF-0007: weight change, new rule, removed rule, and status change are each surfaced."""
    prev = {"strategy": [{"id": "accel", "effective": 30, "status": "assumed"},
                         {"id": "gone", "effective": 10, "status": "assumed"}],
            "general": [{"id": "g", "effective": -5, "status": "testing"}]}
    cur_s = [_hyp("accel", effective=2), _hyp("new-rule", effective=20, status="testing")]
    cur_g = [_hyp("g", effective=-5, status="assumed")]

    weights, added, removed, status, marks = _hyp_diff(prev, cur_s, cur_g)

    assert weights == [{"id": "accel", "from": 30, "to": 2}]
    assert [h["id"] for h in added] == ["new-rule"]
    assert [h["id"] for h in removed] == ["gone"]
    assert status == [{"id": "g", "from": "testing", "to": "assumed"}]
    assert marks["accel"].startswith("w 30→2") and marks["new-rule"] == "new rule"


def test_no_baseline_means_no_callout_on_the_first_build():
    """REQ-BRIEF-0007: with no previous hypotheses, nothing is flagged (don't call every rule 'new')."""
    assert _hyp_diff(None, [_hyp("a", effective=10)], []) == ([], [], [], [], {})


def test_render_brief_shows_the_strategy_change_callout():
    """REQ-BRIEF-0007: the rendered brief carries a 'Strategy changed' callout + an inline badge."""
    manifest = _manifest([_hyp("accel", effective=2, authored=30)], [_hyp("g", effective=-5)])
    prev_hyps = {"strategy": [{"id": "accel", "effective": 30, "status": "assumed"}],
                 "general": [{"id": "g", "effective": -5, "status": "assumed"}]}

    html_out = render_brief(manifest, prev_hyps=prev_hyps, prev_build_id=4)

    assert "Strategy changed since build #4" in html_out
    assert "weight 30 → 2" in html_out          # the callout
    assert "w 30→2" in html_out                 # inline badge on the row
    # first build (no baseline) renders no strategy callout
    assert "Strategy changed" not in render_brief(manifest)
