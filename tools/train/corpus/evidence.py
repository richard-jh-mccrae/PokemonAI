"""Strict one-ply Ledger Episode evidence auditing."""
from __future__ import annotations

import json


def _select_context(record: dict):
    observation = record.get("observation") or {}
    if "select_context" in observation:
        return observation["select_context"]
    try:
        from common.observation import ObservationRecord

        state = ObservationRecord(
            int(observation["schema_version"]), observation["payload"]).to_state()
        return None if state.select is None else state.select.context
    except (KeyError, TypeError, ValueError):
        return None


def _replay_choices(replay: dict) -> list[tuple[object, object, list, object]]:
    steps = replay.get("steps") or []
    film = steps[0][0].get("visualize") or [] if steps and steps[0] else []
    choices = []
    for index, frame in enumerate(film):
        select = frame.get("select")
        if not isinstance(select, dict) or not select.get("option"):
            continue
        following = film[index + 1] if index + 1 < len(film) else None
        selected = following.get("selected") if following else None
        if selected is None:
            continue
        current = frame.get("current") or {}
        choices.append((current.get("yourIndex"), current.get("turn"), list(selected),
                        select.get("context")))
    return choices


def audit_correction_records(records: list[dict], *, replay: dict | None = None) -> dict:
    ledger, pregame, identities, selected_chain_caps, incomplete = [], [], {}, [], []
    forced_unpriced = []
    completeness = {"complete": 0, "estimated": 0}
    emitted = [record for record in records if record.get("record_type") == "decision"]
    if replay is not None:
        choices = _replay_choices(replay)
        if len(emitted) != len(choices):
            raise ValueError("telemetry does not cover every replay choice in order")
        for choice, record in zip(choices, emitted):
            seat, turn, selected, context = choice
            decision = record.get("decision") or {}
            if decision.get("seat") != seat:
                raise ValueError("telemetry seat does not match replay choice")
            if decision.get("turn") != turn:
                raise ValueError("telemetry turn does not match replay choice")
            if list(decision.get("selection") or []) != selected:
                raise ValueError("telemetry selection does not match replay choice")
            if _select_context(record) != context:
                raise ValueError("telemetry context does not match replay choice")
    for record in records:
        if record.get("record_type") != "decision":
            continue
        decision = record.get("decision") or {}
        variant = decision.get("variant")
        if variant == "declarative_pregame":
            if not isinstance(decision.get("turn"), int) or decision["turn"] > 0:
                raise ValueError("declarative pregame decision occurred after setup")
            pregame.append(record)
            continue
        if variant != "ledger":
            raise ValueError(f"unknown decision variant: {variant}")
        ledger.append(record)
        reason = str(decision.get("policy_reason") or "")
        if reason.startswith("fail_safe"):
            raise ValueError(f"fail-safe decision entered Correction Run: {reason}")
        state = record.get("completeness")
        if (record.get("search") or {}).get("failure") is not None:
            raise ValueError("unavailable Ledger search failure entered Correction Run")
        if not isinstance(decision.get("turn"), int) or decision["turn"] <= 0:
            raise ValueError("Ledger decision occurred during setup")
        candidates = tuple(record.get("candidates") or ())
        forced = (reason == "forced" and len(candidates) == 1
                  and candidates[0].get("action_id") == decision.get("chosen_action_id")
                  and candidates[0].get("status") == "unavailable")
        if state not in completeness and not (state == "unavailable" and forced):
            raise ValueError(f"unavailable Ledger decision entered Correction Run: {state}")
        if forced:
            forced_unpriced.append(record.get("record_id"))
        else:
            completeness[state] += 1
        if state != "complete":
            if not forced:
                incomplete.append(record.get("record_id"))
        identity = record.get("behavior_identity") or {}
        identities[json.dumps(identity, sort_keys=True, separators=(",", ":"))] = identity
        chosen_id = decision.get("chosen_action_id")
        chosen = next((candidate for candidate in record.get("candidates") or ()
                       if candidate.get("action_id") == chosen_id), None)
        if chosen and any("chain capped" in str(gap) for gap in chosen.get("gaps") or ()):
            selected_chain_caps.append(record.get("record_id"))
    if not ledger:
        raise ValueError("Correction Run episode contains no Ledger decisions")
    return {
        "ledger_decisions": len(ledger), "pregame_decisions": len(pregame),
        "forced_unpriced_decisions": forced_unpriced,
        "completeness": completeness, "incomplete_decisions": incomplete,
        "selected_chain_caps": selected_chain_caps,
        "behavior_identities": [identities[key] for key in sorted(identities)],
    }


__all__ = ("audit_correction_records",)
