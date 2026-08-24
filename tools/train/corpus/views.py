from __future__ import annotations

from pathlib import Path
import json

from .io import atomic_json, canonical_bytes, digest_bytes, digest_file
from .snapshot import load_snapshot


VIEW_SCHEMA = "ledger.training-view"
DEFAULT_PROFILE = Path(__file__).with_name("profiles") / "integrity-only.json"


def _ledger_diagnostic_row(row: dict) -> dict:
    decision = row["decision"]
    chosen = decision["decision"]["chosen_action_id"]
    candidates = decision["candidates"]
    accepted = []
    if decision["decision"]["variant"] == "ledger":
        policy = decision["configuration"]["compute"]["policy"]
        eligible = [candidate for candidate in candidates
                    if candidate["status"] in policy["accepted_statuses"]]
        scores = [(candidate["search_value"] or candidate["delta"] or {}).get("total")
                  for candidate in eligible]
        scored = [(candidate, score) for candidate, score in zip(eligible, scores)
                  if score is not None]
        if scored:
            best = max(score for _candidate, score in scored)
            accepted = [candidate["action_id"] for candidate, score in scored
                        if score >= best - policy["noise_tolerance"]]
        accepted.extend(candidate["action_id"] for candidate in eligible
                        if candidate["disposition"] == "forced")
    return {
        "corpus_decision_id": row["corpus_decision_id"],
        "episode_key": decision["episode"]["key"],
        "seat": decision["decision"]["seat"],
        "decision_index": decision["decision"]["index"],
        "turn": decision["decision"]["turn"],
        "variant": decision["decision"]["variant"],
        "chosen_action_id": chosen,
        "candidate_count": len(decision["actions"]),
        "completeness": decision["completeness"],
        "decision_seconds": decision["timing"]["decision_seconds"],
        "deadline_hit": decision["timing"]["deadline_hit"],
        "seat_reward": row["terminal_target"]["seat_reward"],
        "winner": row["terminal_target"]["winner"],
        "replay_drift": (None if row["replay_certificate"]["mode"] == "not_replayed"
                         else not all(row["replay_certificate"][field]
                                      for field in ("legal_actions_exact", "root_exact",
                                                    "successors_exact"))),
        "policy_inconsistency": (None if not accepted else chosen not in set(accepted)),
        "full_choice_replayed": row["replay_certificate"]["full_choice_exact"] is not None,
    }


def _rate(rows: list[dict], field: str) -> float | None:
    values = [row[field] for row in rows if row[field] is not None]
    return None if not values else sum(bool(value) for value in values) / len(values)


def _quality(rows: list[dict], profile: dict) -> dict:
    elapsed = sorted(row["decision_seconds"] for row in rows
                     if row["decision_seconds"] is not None)
    metrics = {
        "replay_drift_rate": _rate(rows, "replay_drift"),
        "policy_inconsistency_rate": _rate(rows, "policy_inconsistency"),
        "p95_decision_seconds": (None if not elapsed else
                                 elapsed[max(0, (95 * len(elapsed) + 99) // 100 - 1)]),
    }
    supported = {
        "max_replay_drift_rate": "replay_drift_rate",
        "max_policy_inconsistency_rate": "policy_inconsistency_rate",
        "max_p95_decision_seconds": "p95_decision_seconds",
    }
    unknown = set(profile["thresholds"]) - set(supported)
    if unknown:
        raise ValueError(f"unknown Health Profile threshold: {sorted(unknown)[0]}")
    if not profile["thresholds"]:
        return {"status": "not_assessed", "metrics": metrics, "violations": []}
    missing, violations = [], []
    for threshold, limit in profile["thresholds"].items():
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            raise ValueError(f"invalid Health Profile threshold: {threshold}")
        metric = supported[threshold]
        if metrics[metric] is None:
            missing.append(metric)
        elif metrics[metric] > limit:
            violations.append({"threshold": threshold, "limit": limit,
                               "actual": metrics[metric]})
    status = "insufficient_data" if missing else "unhealthy" if violations else "healthy"
    return {"status": status, "metrics": metrics, "violations": violations,
            "missing": missing}


def build_training_view(*, snapshot_path: Path, output_root: Path,
                        name: str = "ledger_diagnostics",
                        profile_path: Path = DEFAULT_PROFILE) -> Path:
    if name != "ledger_diagnostics":
        raise ValueError(f"unknown Training View: {name}")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("Training Views require the pinned pyarrow dependency") from error
    manifest, corpus_rows = load_snapshot(Path(snapshot_path))
    rows = [_ledger_diagnostic_row(row) for row in corpus_rows]
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    if set(profile) != {"name", "schema_version", "thresholds"} \
            or profile["schema_version"] != 1 or not isinstance(profile["thresholds"], dict):
        raise ValueError("invalid Health Profile")
    quality = _quality(rows, profile)
    identity = digest_bytes(canonical_bytes({"view": name, "schema_version": 1,
                                             "snapshot_id": manifest["snapshot_id"],
                                             "profile": profile}))
    destination = Path(output_root) / name / identity
    parquet_path = destination / "part-00000.parquet"
    if not parquet_path.exists():
        destination.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), parquet_path, compression="zstd")
        atomic_json(destination / "manifest.json", {
            "schema": VIEW_SCHEMA, "schema_version": 1, "view_id": identity,
            "name": name, "snapshot_id": manifest["snapshot_id"],
            "profile": profile,
            "quality": quality,
            "rows": len(rows), "files": [{"path": parquet_path.name,
                                           "sha256": digest_file(parquet_path)}],
        })
    return destination
