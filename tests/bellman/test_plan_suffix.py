from __future__ import annotations

from common import ActionIdentity, PlanRequest, PlanStep
from common.pilot_profile import PilotProfile
from common.runtime import BellmanRuntime
from common.state import DecisionState


def _observation(turn=4):
    return {
        "current": {"turn": turn, "yourIndex": 0, "players": [
            {"hand": [], "active": [], "bench": [], "prize": []},
            {"hand": None, "active": [], "bench": [], "prize": []},
        ]},
        "select": {"context": 0, "minCount": 1, "maxCount": 1,
                   "option": [{"type": 14}]},
    }


class _Planner:
    @staticmethod
    def state_for(request):
        return DecisionState.from_observation(
            request.observation, deck=request.deck, deck_name=request.deck_name,
            value_registry_identity="registry:profile")


def _runtime(state):
    deployed = object.__new__(BellmanRuntime)
    deployed.pilot_profile = PilotProfile.resolve()
    deployed._plan_suffix = (PlanStep(
        state.semantic_key, state.legal_menu_digest, (0,), ActionIdentity("end"),
        deployed.pilot_profile.hash, 4, 0),)
    return deployed


def test_exact_plan_suffix_guard_executes_without_planning():
    request = PlanRequest(_observation(), (), "test")
    state = _Planner.state_for(request)
    deployed = _runtime(state)

    decision, status = deployed._cached_decision(_Planner(), request)

    assert status == "hit"
    assert decision.chosen == (0,)
    assert decision.diagnostics["backend"] == "plan-suffix"


def test_plan_suffix_state_mismatch_discards_the_cache():
    request = PlanRequest(_observation(), (), "test")
    deployed = _runtime(_Planner.state_for(request))
    changed = PlanRequest(_observation(turn=5), (), "test")

    decision, status = deployed._cached_decision(_Planner(), changed)

    assert decision is None
    assert status == "turn_changed"
    assert deployed._plan_suffix == ()
