from __future__ import annotations

from common import PlanRequest, PlanStep, enumerate_legal_actions
from common.pilot_profile import PilotProfile
from common.runtime import BellmanRuntime
from common.state import DecisionState
from common.terminal import ProofStep


def _observation(turn=4, options=None):
    return {
        "current": {"turn": turn, "yourIndex": 0, "players": [
            {"hand": [], "active": [], "bench": [], "prize": []},
            {"hand": None, "active": [], "bench": [], "prize": []},
        ]},
        "select": {"context": 0, "minCount": 1, "maxCount": 1,
                   "option": options or [{"type": 14}]},
    }


class _Planner:
    @staticmethod
    def state_for(request):
        return DecisionState.from_observation(
            request.observation, deck=request.deck, deck_name=request.deck_name,
            value_registry_identity="registry:profile")


def _runtime(state, *, chosen=(0,), action=None):
    deployed = object.__new__(BellmanRuntime)
    deployed.pilot_profile = PilotProfile.resolve()
    if action is None:
        action = next(candidate.identity for candidate in enumerate_legal_actions(state.obs)
                      if candidate.selection == chosen)
    deployed._plan_suffix = (PlanStep(
        state.plan_key, state.legal_menu_digest, chosen, action,
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


def test_plan_suffix_resolves_semantic_action_against_reordered_live_menu():
    planned_request = PlanRequest(_observation(options=[{"type": 14}, {"type": 12}]), (), "test")
    planned_state = _Planner.state_for(planned_request)
    planned_action = next(action for action in enumerate_legal_actions(planned_state.obs)
                          if action.identity.kind == "retreat")
    deployed = _runtime(
        planned_state, chosen=planned_action.selection, action=planned_action.identity)
    live_request = PlanRequest(_observation(options=[{"type": 12}, {"type": 14}]), (), "test")

    decision, status = deployed._cached_decision(_Planner(), live_request)

    assert status == "hit"
    assert decision.action == planned_action.identity
    assert decision.chosen == (0,)


def test_terminal_proof_lock_replays_before_ordinary_plan_suffix():
    request = PlanRequest(_observation(options=[{"type": 13}, {"type": 14}]), (), "test")
    state = _Planner.state_for(request)
    attack = next(action for action in enumerate_legal_actions(state.obs)
                  if action.identity.kind == "attack")
    deployed = _runtime(state)
    deployed._proof_id = "proof-1"
    deployed._proof_suffix = (ProofStep(
        state.plan_key, state.legal_menu_digest, attack.selection, attack.identity,
        deployed.pilot_profile.hash, "proof-1", 4, 0),)

    decision, status = deployed._cached_proof_decision(_Planner(), request)

    assert status == "hit"
    assert decision.action == attack.identity
    assert decision.diagnostics["backend"] == "terminal-proof-lock"
    assert deployed._plan_suffix


def test_terminal_proof_lock_mismatch_discards_only_the_proof():
    request = PlanRequest(_observation(), (), "test")
    state = _Planner.state_for(request)
    deployed = _runtime(state)
    action = next(iter(enumerate_legal_actions(state.obs)))
    deployed._proof_id = "proof-1"
    deployed._proof_suffix = (ProofStep(
        state.plan_key, state.legal_menu_digest, action.selection, action.identity,
        deployed.pilot_profile.hash, "different-proof", 4, 0),)

    decision, status = deployed._cached_proof_decision(_Planner(), request)

    assert decision is None
    assert status == "proof_changed"
    assert deployed._proof_suffix == ()
    assert deployed._plan_suffix
