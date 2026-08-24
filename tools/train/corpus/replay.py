from __future__ import annotations

import dataclasses
from pathlib import Path

from common.observation import ObservationRecord
from common.telemetry import build_decision_record


class CorpusRejection(ValueError):
    def __init__(self, decision: dict, reason: str):
        self.decision_id = str(decision.get("record_id", "unknown"))
        self.reason = reason
        super().__init__(f"{self.decision_id}: {reason}")


def _reject(decision: dict, reason: str):
    raise CorpusRejection(decision, reason)


def _raw_observation(replay: dict, decision: dict) -> dict | None:
    from train.blunder.decisions import iter_decisions

    seat = decision["decision"]["seat"]
    index = decision["decision"]["index"]
    matches = [item for item in iter_decisions(replay) if item.seat == seat]
    if index >= len(matches):
        return None
    return matches[index].obs


def certify_replay(decision: dict, replay: dict) -> dict:
    """Re-evaluate one Ledger record when its exact local behavior identity resolves."""

    if decision["decision"]["variant"] != "ledger":
        return _reject(decision, "pregame_has_no_ledger_evaluation")
    agent = str(decision["provenance"]["agent"])
    repo = Path(__file__).resolve().parents[3]
    if not (repo / "src" / "agents" / agent / "strategy.py").exists():
        return _reject(decision, "agent_artifact_unavailable")
    raw = _raw_observation(replay, decision)
    if raw is None:
        return _reject(decision, "replay_observation_unavailable")
    recorded_provider = decision["configuration"]["provider"]
    state = ObservationRecord(
        decision["observation"]["schema_version"],
        decision["observation"]["payload"],
    ).to_state()
    from train.ledger_corpus import _build_replay_ledger

    try:
        ledger = _build_replay_ledger(
            agent, decision["configuration"], provider_backend=recorded_provider["backend"],
            deck=state.decklist)
    except (ImportError, RuntimeError, ValueError) as error:
        reason = ("configuration_identity_unavailable"
                  if str(error).startswith("recorded ")
                  else "provider_identity_unavailable")
        return _reject(decision, f"{reason}:{type(error).__name__}")
    if ledger.provider_configuration != recorded_provider:
        return _reject(decision, "provider_substitution")
    recorded_behavior = decision["behavior_identity"]
    current_behavior = dataclasses.asdict(ledger.behavior_identity)
    if recorded_behavior != current_behavior:
        return _reject(decision, "behavior_identity_unavailable")
    recorded_model = decision["configuration"]["evaluation_model"]["identity"]
    recorded_compute = decision["configuration"]["compute"]["identity"]
    if ledger.ctx.identity != recorded_model or ledger.compute.identity != recorded_compute:
        return _reject(decision, "configuration_identity_unavailable")
    replayed = ledger.decide(raw, state=state)
    rebuilt = build_decision_record(
        replayed.decision_result, state,
        episode_key=decision["episode"]["key"],
        decision_index=decision["decision"]["index"],
        parent_decision_id=decision["decision"]["parent_id"],
        selection=tuple(replayed.chosen),
        evaluation_model=ledger.ctx,
        compute_configuration=ledger.compute,
        provider_configuration=ledger.provider_configuration,
        provenance=decision["provenance"],
        decision_seconds=decision["timing"]["decision_seconds"],
        decision_limit_seconds=decision["timing"]["decision_limit_seconds"],
        deadline_hit=decision["timing"]["deadline_hit"],
    )
    legal_exact = rebuilt["actions"] == decision["actions"]
    root_exact = rebuilt["root"] == decision["root"]
    successor_exact = rebuilt["candidates"] == decision["candidates"]
    time_limited = (decision["search"]["stop_reason"] == "time_budget"
                    or decision["timing"]["deadline_hit"] is True)
    full_exact = None if time_limited else (
        rebuilt["decision"]["chosen_action_id"] == decision["decision"]["chosen_action_id"]
        and rebuilt["decision"]["selection"] == decision["decision"]["selection"]
        and rebuilt["decision"]["policy_reason"] == decision["decision"]["policy_reason"]
        and rebuilt["search"] == decision["search"])
    if not legal_exact:
        return _reject(decision, "legal_actions_drift")
    if not root_exact:
        return _reject(decision, "root_valuation_drift")
    if not successor_exact:
        return _reject(decision, "successor_evaluation_drift")
    if full_exact is False:
        return _reject(decision, "full_choice_drift")
    return {
        "schema_version": 2, "mode": "offline_replay",
        "recorded_legal_actions_valid": True, "recorded_evaluation_valid": True,
        "recorded_successors_valid": True,
        "legal_actions_exact": legal_exact, "root_exact": root_exact,
        "successors_exact": successor_exact, "full_choice_exact": full_exact,
        "exclusion": "time_budgeted_full_choice" if time_limited else None,
    }


__all__ = ("CorpusRejection", "certify_replay")
