"""Issue #494 — public canonical potential and difference contract."""
from __future__ import annotations

import json

import pytest

from common import state_value as sv


def _result(family: str, *legs: sv.PotentialLeg) -> sv.PotentialResult:
    return sv.PotentialResult(family, sum(leg.value_prizes for leg in legs), tuple(legs))


def test_registry_is_the_six_state_families_and_one_terminal_family():
    assert tuple(family.name for family in sv.REGISTRY) == (
        "prize_race", "survival", "threat", "readiness", "hand", "development")
    assert tuple(family.name for family in sv.TERMINAL_REGISTRY) == ("attack_ev",)
    assert all(family.evaluator is not None for family in sv.REGISTRY)
    assert sv.TERMINAL_REGISTRY[0].evaluator is None
    assert sv.double_counted() == sv.undeclared_shared_inputs() == []


def test_registry_identity_is_stable_and_json_projection_is_primitive():
    identity = sv.registry_identity()
    assert identity.startswith("state-value/3:") and len(identity.rsplit(":", 1)[1]) == 64
    payload = sv.ValueBreakdown(0.0, (), identity).as_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_status_invariants_keep_unknown_and_deliberate_zero_visible():
    unknown = sv.PotentialLeg("owed", 0.0, sv.PotentialStatus.UNKNOWN, "oracle absent")
    result = sv.PotentialResult("hand", 0.0, (unknown,), sv.PotentialStatus.UNKNOWN,
                                unknowns=("owed",))
    assert result.as_dict()["status"] == "unknown"
    with pytest.raises(ValueError):
        sv.PotentialLeg("bad", 1.0, sv.PotentialStatus.UNKNOWN, "not numeric knowledge")


def test_difference_aligns_dynamic_legs_in_before_then_after_order(monkeypatch):
    before = sv.ValueBreakdown(1.0, (_result("x", sv.PotentialLeg("a", 1.0)),), "id")
    after = sv.ValueBreakdown(3.0, (_result("x", sv.PotentialLeg("b", 2.0),
                                             sv.PotentialLeg("a", 1.0)),), "id")
    monkeypatch.setattr(sv, "value_breakdown", lambda model: before if model == "before" else after)
    difference = sv.value_difference("before", "after")
    assert difference.delta == 2.0
    assert tuple(leg.key for leg in difference.families[0].legs) == ("a", "b")
    assert difference.families[0].legs[1].before_status is sv.PotentialStatus.KNOWN
    assert difference.as_dict()["families"][0]["delta"] == 2.0


def test_scalar_and_diagnostic_memos_are_separate_and_diagnostics_seed_scalar(monkeypatch):
    class Model:
        def __init__(self):
            self.memo = {}
            self.calls = []

        def _memoized(self, key, supplier):
            if key not in self.memo:
                self.memo[key] = supplier()
            return self.memo[key]

    def evaluator(model, diagnostics=False):
        model.calls.append(diagnostics)
        return _result("only", sv.PotentialLeg("leg", 2.0)) if diagnostics else 2.0

    family = sv.TermFamily("only", (sv.ConsequenceSpec("only.value", (), "test"),), (),
                           "test family", evaluator=evaluator)
    monkeypatch.setattr(sv, "REGISTRY", (family,))
    monkeypatch.setattr(sv, "FAMILIES", {"only": family})

    scalar_first = Model()
    assert sv.state_value(scalar_first) == 2.0
    assert tuple(scalar_first.memo) == (("state_value",),)
    assert sv.value_breakdown(scalar_first).total == 2.0
    assert any(key[0] == "value_breakdown" for key in scalar_first.memo)
    assert scalar_first.calls == [False, True]

    diagnostic_first = Model()
    assert sv.value_breakdown(diagnostic_first).total == 2.0
    assert sv.state_value(diagnostic_first) == 2.0
    assert diagnostic_first.calls == [True]
