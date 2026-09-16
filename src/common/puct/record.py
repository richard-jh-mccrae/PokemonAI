from __future__ import annotations

import json
from dataclasses import asdict

from common.observation import ObservationRecord
from common.decision.puct import PuctEvidence


def decision_record(decision, observation, configuration, *, executed_action=None) -> dict:
    evidence = decision.search.evidence
    if (not isinstance(evidence, PuctEvidence)
            or configuration.identity != evidence.configuration_identity):
        raise ValueError("PUCT record requires its matching result and configuration")
    root_distribution = evidence.prior_distributions[0].distribution
    priors = root_distribution.priors_for(decision.roster)
    edges = {edge.choice: edge for edge in evidence.root_edges}
    candidates = []
    for action, candidate, prior in zip(
            decision.roster.actions, decision.search.candidates,
            priors):
        edge = edges[candidate.choice]
        statistics = edge.statistics
        candidates.append({
            "action": asdict(action.identity), "selection": list(action.selection),
            "prior": prior, "visits": statistics.visits, "value_sum": statistics.value_sum,
            "mean_value": statistics.mean_value, "inherited_visits": statistics.inherited_visits,
            "status": candidate.delta_status.value, "exclusion": statistics.exclusion,
        })
    wire = asdict(evidence)
    reproduction = wire.pop("reproduction_input")
    wire["prior_distributions"] = [{
        "decision_key": item.decision_key, "preparation_limited": item.preparation_limited,
        "distribution": item.distribution.as_dict()} for item in evidence.prior_distributions]
    return {
        "schema": "puct-decision", "schema_version": 1,
        "input": json.loads(ObservationRecord.from_state(observation).dumps()),
        "provider_input": None if reproduction is None else json.loads(reproduction),
        "configuration": asdict(configuration), "evidence": wire, "candidates": candidates,
        "chosen_action": None if decision.chosen is None else asdict(decision.chosen.identity),
        "executed_action": None if executed_action is None else asdict(executed_action),
        "principal_variation_is_conditional": any(step.chance_slot is not None for step in evidence.principal_variation),
        "principal_variation_is_exhaustive": False,
        "stop_reason": decision.search.outcome.termination.code,
        "failure": (None if decision.search.outcome.failure is None
                    else asdict(decision.search.outcome.failure)),
        "value_scale": None if decision.baseline is None else asdict(decision.baseline.scale),
        "behavior": None if decision.behavior_identity is None else asdict(decision.behavior_identity),
    }


def dumps_decision(decision, observation, configuration, *, executed_action=None) -> str:
    return json.dumps(decision_record(decision, observation, configuration, executed_action=executed_action),
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
