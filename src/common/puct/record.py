from __future__ import annotations

import json
from dataclasses import asdict

from common.observation import ObservationRecord


def decision_record(decision, observation, configuration, *, executed_action=None) -> dict:
    evidence = decision.search.puct
    if evidence is None or configuration.identity != evidence.configuration_identity:
        raise ValueError("PUCT record requires its matching result and configuration")
    candidates = []
    for candidate in decision.roster.candidates:
        statistics = candidate.puct
        candidates.append({
            "action": asdict(candidate.action.identity), "selection": list(candidate.action.selection),
            "prior": candidate.prior, "visits": statistics.visits, "value_sum": statistics.value_sum,
            "mean_value": statistics.mean_value, "inherited_visits": statistics.inherited_visits,
            "status": candidate.status.value, "exclusion": statistics.exclusion,
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
        "stop_reason": decision.search.stop_reason,
        "failure": None if decision.search.failure is None else asdict(decision.search.failure),
        "value_scale": None if decision.baseline is None else asdict(decision.baseline.scale),
        "behavior": None if decision.behavior_identity is None else asdict(decision.behavior_identity),
    }


def dumps_decision(decision, observation, configuration, *, executed_action=None) -> str:
    return json.dumps(decision_record(decision, observation, configuration, executed_action=executed_action),
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
