from __future__ import annotations

import dataclasses
from pathlib import Path

from common.observation import ObservationRecord
from common.telemetry import build_decision_record


def _unresolved(decision: dict, reason: str) -> dict:
    action_ids = [action["id"] for action in decision["actions"]]
    return {
        "schema_version": 1, "mode": "not_replayed",
        "recorded_legal_actions_valid": decision["decision"]["chosen_action_id"] in action_ids,
        "recorded_evaluation_valid": decision["decision"]["variant"] != "ledger"
        or decision["root"] is not None,
        "recorded_successors_valid": True,
        "legal_actions_exact": None, "root_exact": None, "successors_exact": None,
        "full_choice_exact": None, "exclusion": reason,
    }


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
        return _unresolved(decision, "pregame_has_no_ledger_evaluation")
    agent = str(decision["provenance"]["agent"])
    repo = Path(__file__).resolve().parents[3]
    if not (repo / "src" / "agents" / agent / "strategy.py").exists():
        return _unresolved(decision, "agent_artifact_unavailable")
    raw = _raw_observation(replay, decision)
    if raw is None:
        return _unresolved(decision, "replay_observation_unavailable")
    from train.ledger_corpus import _build_runtime

    runtime = _build_runtime(agent)
    recorded_behavior = decision["behavior_identity"]
    current_behavior = dataclasses.asdict(runtime.ledger.behavior_identity)
    if recorded_behavior != current_behavior:
        return _unresolved(decision, "behavior_identity_unavailable")
    recorded_model = decision["configuration"]["evaluation_model"]["identity"]
    recorded_compute = decision["configuration"]["compute"]["identity"]
    if runtime.ledger.ctx.identity != recorded_model or runtime.ledger.compute.identity != recorded_compute:
        return _unresolved(decision, "configuration_identity_unavailable")
    state = ObservationRecord(
        decision["observation"]["schema_version"],
        decision["observation"]["payload"],
    ).to_state()
    replayed = runtime.ledger.decide(raw, state=state)
    rebuilt = build_decision_record(
        replayed.decision_result, state,
        episode_key=decision["episode"]["key"],
        decision_index=decision["decision"]["index"],
        parent_decision_id=decision["decision"]["parent_id"],
        selection=tuple(replayed.chosen),
        evaluation_model=runtime.ledger.ctx,
        compute_configuration=runtime.ledger.compute,
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
        and rebuilt["decision"]["policy_reason"] == decision["decision"]["policy_reason"]
        and rebuilt["search"] == decision["search"])
    return {
        "schema_version": 1, "mode": "offline_replay",
        "recorded_legal_actions_valid": True, "recorded_evaluation_valid": True,
        "recorded_successors_valid": True,
        "legal_actions_exact": legal_exact, "root_exact": root_exact,
        "successors_exact": successor_exact, "full_choice_exact": full_exact,
        "exclusion": "time_budgeted_full_choice" if time_limited else None,
    }
