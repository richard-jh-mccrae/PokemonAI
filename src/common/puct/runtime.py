from __future__ import annotations

from common.decision import DecisionCoordinator, PolicyConfiguration, PolicySourceIdentity
from common.ledger import LedgerPolicyModel, UniformPolicyModel
from common.ledger.configuration import BehaviorIdentity
from common.ledger.decision import LedgerValueEvaluator
from common.decision.action_policy import action_policy_for_agent
from .configuration import PuctConfiguration
from .policy import PuctDecisionPolicy
from .search import PuctSearch


def _profile(name: str, agent: str, *, reuse_tree: bool, **limits) -> PuctConfiguration:
    return PuctConfiguration(
        profile=name, action_policy=action_policy_for_agent(agent),
        reuse_tree=reuse_tree, **limits)


def play_profile(agent: str, *, reuse_tree: bool, **limits) -> PuctConfiguration:
    return _profile("play", agent, reuse_tree=reuse_tree, **limits)


def inspection_profile(agent: str, *, reuse_tree: bool, **limits) -> PuctConfiguration:
    return _profile("inspection", agent, reuse_tree=reuse_tree, **limits)


def evaluation_profile(agent: str, *, reuse_tree: bool, **limits) -> PuctConfiguration:
    return _profile("evaluation", agent, reuse_tree=reuse_tree, **limits)


def build_puct_coordinator(evaluation_model, *, baseline_identity: str, baseline_path, calibration_path,
                           prior_mode: str, configuration: PuctConfiguration,
                           provider_identity: str, search: PuctSearch | None = None) -> DecisionCoordinator:
    if prior_mode not in ("uniform", "ledger"):
        raise ValueError("prior_mode must be uniform or ledger")
    evaluator = LedgerValueEvaluator()
    ledger = LedgerPolicyModel.load_calibrated(baseline_identity, baseline_path, calibration_path)
    ledger.validate_source(PolicySourceIdentity(
        baseline_identity, evaluator.identity, evaluation_model.identity, evaluator.value_scale.identity))
    policy = ledger if prior_mode == "ledger" else UniformPolicyModel()
    search = PuctSearch() if search is None else search
    selection = PuctDecisionPolicy()
    identity = BehaviorIdentity(
        evaluator.identity, evaluation_model.identity, search.identity, policy.identity, selection.identity,
        "stop-with-evidence-v1", provider_identity, configuration.identity, evaluation_model.prize_plan.identity)
    return DecisionCoordinator(evaluator, evaluation_model, search, configuration, policy, selection,
                               PolicyConfiguration(), behavior_identity=identity,
                               ledger_baseline_identity=baseline_identity)
