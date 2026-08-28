from __future__ import annotations

import hashlib
from itertools import combinations
import json
import math

from common.ledger.training import parameter_manifest
from train.blunder.correction import is_critical


SCHEMA = "ledger.value-audit"
SCHEMA_VERSION = 1


def _candidate(row, selection):
    wanted = tuple(selection or ())
    return next((candidate for candidate in row.get("candidates", ())
                 if tuple(candidate.get("selection", ())) == wanted), None)


def _complete(candidate) -> bool:
    return bool(candidate) and candidate.get("status") == "complete" \
        and candidate.get("search_value") is not None \
        and all(successor.get("status") == "complete"
                for successor in candidate.get("successors", ()))


def _gaps(candidate) -> tuple[str, ...]:
    return tuple(candidate.get("gaps", ())) + tuple(
        gap for successor in candidate.get("successors", ())
        for gap in successor.get("gaps", ()))


def _components(candidate) -> dict[str, dict]:
    grouped = {}
    for item in candidate.get("components", ()):
        grouped.setdefault(str(item["feature"]), []).append(item)
    return {feature: {
        "feature": feature,
        "activation": math.fsum(float(item.get("activation", 0.0)) for item in items),
        "coefficient": next((item.get("coefficient") for item in items
                             if item.get("coefficient") is not None), None),
        "contribution": math.fsum(
            float(item.get("contribution", 0.0)) for item in items),
        "provenance": sorted({owner for item in items
                              for owner in item.get("provenance", ())}),
    } for feature, items in grouped.items()}


def _component_differences(ruled, committed) -> list[dict]:
    ruled_components = _components(ruled)
    committed_components = _components(committed)
    rows = []
    for feature in sorted(set(ruled_components) | set(committed_components)):
        good = ruled_components.get(feature, {})
        bad = committed_components.get(feature, {})
        activation_delta = float(good.get("activation", 0.0)) - float(
            bad.get("activation", 0.0))
        contribution_delta = float(good.get("contribution", 0.0)) - float(
            bad.get("contribution", 0.0))
        coefficient = good.get("coefficient", bad.get("coefficient"))
        provenance = sorted(set(good.get("provenance", ())) | set(
            bad.get("provenance", ())))
        if activation_delta or contribution_delta:
            rows.append({
                "feature": feature,
                "activation_delta": activation_delta,
                "coefficient": coefficient,
                "contribution_delta": contribution_delta,
                "provenance": provenance,
            })
    return rows


def _cause(gradeable, ruled, committed, differences, margin) -> str:
    gaps = _gaps(ruled) + _gaps(committed)
    if any("coverage" in gap or "unknown card" in gap for gap in gaps):
        return "coverage"
    if not gradeable:
        return "search_completeness"
    if gaps:
        return "transition"
    if not differences:
        return "activation_equation"
    if any("feasible_option_portfolio" in item.get("provenance", ())
           for item in differences):
        return "portfolio_constraint"
    return "coefficient_seed" if margin <= 0 else "resolved"


def _proposal(differences, margin):
    proposal = {"required": margin is not None and margin <= 0,
                "auto_apply": False, "changes": []}
    if margin is None or margin > 0:
        return proposal
    trainable = {item.key for item in parameter_manifest() if item.trainable}
    choices = []
    for item in differences:
        activation = item["activation_delta"]
        coefficient = item["coefficient"]
        if item["feature"] not in trainable or not activation or coefficient is None:
            continue
        boundary = float(coefficient) - margin / activation
        choices.append((abs(boundary - float(coefficient)), {
            "feature": item["feature"],
            "current_coefficient": float(coefficient),
            "break_even_coefficient": boundary,
            "required_direction": "increase" if boundary > coefficient else "decrease",
        }))
    if choices:
        proposal["changes"] = [min(choices, key=lambda item: (item[0], item[1]["feature"]))[1]]
    return proposal


def _audit(row) -> dict:
    committed_selection = list(row.get("recorded_chosen", row.get("chosen", ())))
    acceptable = [list(selection or ()) for selection in row.get(
        "acceptable", (row.get("correct") or (),))]
    satisfied_by_committed = committed_selection in acceptable
    committed = _candidate(row, committed_selection)
    ruled_candidates = tuple(_candidate(row, selection) for selection in acceptable)
    gradeable = _complete(committed) and (satisfied_by_committed or all(
        _complete(candidate) for candidate in ruled_candidates))
    preferences = [] if not gradeable or satisfied_by_committed else [{
        "selection": acceptable[index],
        "margin": float(candidate["search_value"]) - float(committed["search_value"]),
        "contribution_differences": _component_differences(candidate, committed),
    } for index, candidate in enumerate(ruled_candidates)]
    worst = (None if not preferences else min(
        preferences, key=lambda item: (item["margin"], item["selection"])))
    ruled_selection = committed_selection if satisfied_by_committed else (
        list(row.get("correct") or ()) if worst is None else worst["selection"])
    ruled = _candidate(row, ruled_selection)
    atomic_margin = (0.0 if satisfied_by_committed and gradeable else
                     None if worst is None else worst["margin"])
    paths = tuple(successor.get("action_path", ())
                  for candidate in (ruled or {}, committed or {})
                  for successor in candidate.get("successors", ()))
    compound = row.get("context") in {0, None} and any(len(path) > 1 for path in paths)
    differences = [] if worst is None else worst["contribution_differences"]
    cause = _cause(gradeable, ruled or {}, committed or {}, differences,
                   float("-inf") if atomic_margin is None else atomic_margin)
    coefficient_ready = cause == "coefficient_seed"
    proposal = (_proposal(differences, atomic_margin)
                if not satisfied_by_committed and coefficient_ready
                else _proposal([], None))
    return {
        "correction_id": row.get("id"),
        "deck": row.get("deck"),
        "locus": {
            "episode_id": row.get("episode_id"),
            "frame": int(str(row.get("key", "--1")).rsplit("-", 1)[-1]),
            "context": row.get("context"),
            "scope": row.get("scope"),
        },
        "rationale": row.get("rationale", ""),
        "acceptable_selections": acceptable,
        "acceptable_preferences": preferences,
        "satisfied_by_committed": satisfied_by_committed,
        "triage": {
            "severity": ("critical" if is_critical(row.get("rationale")) else "normal"),
            "confidence": None,
            "training_weight": 1.0,
        },
        "current_selection": list(row.get("chosen") or ()),
        "committed": committed,
        "ruled": ruled,
        "gradeable": gradeable,
        "margin": {
            "atomic": atomic_margin,
            "compound": atomic_margin if compound else None,
        },
        "contribution_differences": differences,
        "cause": "resolved" if satisfied_by_committed else cause,
        "calibration_proposal": proposal,
    }


def _conflict_sets(audits) -> list[list[str]]:
    groups = {}
    for audit in audits:
        key = tuple(audit["locus"].get(name) for name in (
            "episode_id", "frame", "context", "scope"))
        groups.setdefault(key, []).append(audit)
    conflicts = []
    for audits_at_locus in groups.values():
        selections = {
            audit["correction_id"]: {
                tuple(value) for value in audit["acceptable_selections"]}
            for audit in audits_at_locus
        }
        ids = tuple(sorted(selections))
        for size in range(2, len(ids) + 1):
            for candidate_ids in combinations(ids, size):
                if any(set(previous).issubset(candidate_ids) for previous in conflicts):
                    continue
                common = set.intersection(*(selections[value]
                                            for value in candidate_ids))
                if not common:
                    conflicts.append(list(candidate_ids))
    return sorted(conflicts)


def _apply_non_regression(audits) -> None:
    for audit in audits:
        changes = audit["calibration_proposal"]["changes"]
        if not changes:
            audit["calibration_proposal"]["preserves_all_preferences"] = None
            audit["calibration_proposal"]["blocked_by"] = []
            continue
        change = changes[0]
        feature = change["feature"]
        shift = change["break_even_coefficient"] - change["current_coefficient"]
        blocked = []
        for constraint in audits:
            if constraint["correction_id"] == audit["correction_id"]:
                continue
            margin = constraint["margin"]["atomic"]
            if margin is None:
                continue
            shifted_margins = []
            for preference in constraint["acceptable_preferences"]:
                if preference["margin"] <= 0:
                    continue
                activation = next((item["activation_delta"]
                                   for item in preference["contribution_differences"]
                                   if item["feature"] == feature), 0.0)
                shifted_margins.append(preference["margin"] + shift * activation)
            if shifted_margins and min(shifted_margins) <= 0:
                blocked.append(constraint["correction_id"])
        audit["calibration_proposal"]["preserves_all_preferences"] = not blocked
        audit["calibration_proposal"]["blocked_by"] = sorted(blocked)


def build_value_audit(rows) -> dict:
    rows = list(rows)
    audits = [_audit(row) for row in rows
              if row.get("grading_exclusion") != "no_ruling"]
    _apply_non_regression(audits)
    conflicts = _conflict_sets(audits)
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "data_identity": hashlib.sha256(encoded).hexdigest(),
        "summary": {
            "audits": len(audits),
            "gradeable": sum(audit["gradeable"] for audit in audits),
            "incomplete": sum(not audit["gradeable"] for audit in audits),
            "violated_preferences": sum(
                audit["gradeable"] and not audit["satisfied_by_committed"]
                and audit["margin"]["atomic"] <= 0
                for audit in audits),
            "conflict_sets": len(conflicts),
        },
        "minimal_conflict_sets": conflicts,
        "audits": audits,
    }


__all__ = ("SCHEMA", "SCHEMA_VERSION", "build_value_audit")
