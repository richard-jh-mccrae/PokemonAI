"""Build the frozen three-deck Ledger Baseline from offline evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from common.ledger.baseline import (AUTHORITATIVE_DECKS, BLUNDER_POLICY, SCHEMA,
                                    SCHEMA_VERSION, certified_evidence,
                                    validate_baseline, validate_certification)
from train.blunder.store import jsonl_files, load_corrections
from train.corpus import load_episode_bundle
from train.corpus.evidence import audit_correction_records


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _heldout_decisions(decisions: list[dict]) -> list[dict]:
    return [{
        "record_id": record["record_id"], "seat": record["decision"].get("seat"),
        "turn": record["decision"].get("turn"),
        "position_key": record["decision"].get("position_key"),
        "decision_key": record["decision"].get("decision_key"),
    } for record in decisions
        if record.get("record_type") == "decision"
        and (record.get("decision") or {}).get("variant") == "ledger"]


def _report(slots: list[dict]) -> dict:
    tuning = [slot for slot in slots if slot["partition"] == "tuning"]
    return {
        "episodes": len(slots),
        "tuning_episodes": len(tuning),
        "heldout_episodes": len(slots) - len(tuning),
        "wins": sum(slot.get("focal_result") == "win" for slot in slots),
        "losses": sum(slot.get("focal_result") == "loss" for slot in slots),
        "draws": sum(slot.get("focal_result") == "draw" for slot in slots),
        "ledger_decisions": sum(slot["audit"]["ledger_decisions"] for slot in slots),
        "tuning_ledger_decisions": sum(
            slot["audit"]["ledger_decisions"] for slot in tuning),
        "pregame_decisions": sum(slot["audit"]["pregame_decisions"] for slot in slots),
        "forced_unpriced_decisions": sum(
            len(slot["audit"].get("forced_unpriced_decisions", ())) for slot in slots),
        "complete_decisions": sum(slot["audit"]["completeness"]["complete"]
                                  for slot in slots),
        "estimated_decisions": sum(slot["audit"]["completeness"]["estimated"]
                                   for slot in slots),
    }


def _collect_runs(correction_runs) -> dict:
    runs, source, ledger, contestants, identities = [], None, None, {}, {}
    tuning_owners, heldout_episode_ids = {}, set()
    reports, heldout_manifest = {}, {}
    for run_dir in sorted(map(Path, correction_runs), key=lambda value: str(value)):
        path = run_dir / "manifest.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("status") != "complete" or raw.get("totals", {}).get("failed"):
            raise ValueError("Ledger Baseline requires complete Correction Runs")
        if raw.get("source_identity", {}).get("dirty"):
            raise ValueError("Ledger Baseline requires a clean source identity")
        if source is not None and raw.get("source_identity") != source:
            raise ValueError("Ledger Baseline Correction Runs disagree on source identity")
        if ledger is not None and raw.get("ledger") != ledger:
            raise ValueError("Ledger Baseline Correction Runs disagree on Ledger identity")
        source, ledger = raw.get("source_identity"), raw.get("ledger")
        if not isinstance(ledger, dict):
            raise ValueError("Ledger Baseline Correction Run lacks Ledger identity")
        for name, identity in (raw.get("contestants") or {}).items():
            if name in contestants and contestants[name] != identity:
                raise ValueError("Ledger Baseline contestant identity changed between runs")
            contestants[name] = identity
        focal, heldout, tuning, audited = raw.get("focal"), [], [], []
        if focal in reports:
            raise ValueError("Ledger Baseline has duplicate focal Correction Runs")
        heldout_manifest[focal] = []
        for slot in raw.get("slots") or []:
            if slot.get("status") != "complete":
                raise ValueError("Ledger Baseline requires every planned Episode")
            relative = slot.get("bundle_path") or (
                f"bundles/{slot.get('partition')}/{slot.get('bundle_id')}")
            bundle = (run_dir / relative).resolve()
            if run_dir.resolve() not in bundle.parents or not bundle.is_dir():
                raise ValueError("Ledger Baseline Correction Run bundle is missing")
            bundle_manifest, decisions, _receipt, _outcome, replay = load_episode_bundle(bundle)
            if bundle_manifest["bundle_id"] != slot.get("bundle_id") \
                    or str(bundle_manifest["episode_key"]) != str(slot.get("episode_id")) \
                    or str((replay.get("info") or {}).get("EpisodeId")) != str(slot.get("episode_id")):
                raise ValueError("Ledger Baseline Correction Run bundle identity mismatch")
            audit = audit_correction_records(decisions, replay=replay)
            if audit != slot.get("audit"):
                raise ValueError("Ledger Baseline Correction Run audit mismatch")
            evidence = {key: slot.get(key) for key in (
                "index", "episode_id", "opponent", "focal_seat", "partition", "engine_seed",
                "bundle_id", "focal_result")}
            (heldout if slot.get("partition") == "heldout" else tuning).append(evidence)
            audited.append({**slot, "audit": audit})
            episode_id = str(slot.get("episode_id"))
            if episode_id in tuning_owners or episode_id in heldout_episode_ids:
                raise ValueError("Ledger Baseline Episode identity is duplicated")
            if slot.get("partition") == "tuning":
                tuning_owners[episode_id] = focal
            else:
                heldout_episode_ids.add(episode_id)
                heldout_manifest[focal].append({
                    "episode_id": slot.get("episode_id"), "bundle_id": slot.get("bundle_id"),
                    "decisions": _heldout_decisions(decisions),
                })
            for identity in audit["behavior_identities"]:
                identities[_canonical(identity)] = identity
        if not heldout:
            raise ValueError("Ledger Baseline requires held-out Episodes for every focal deck")
        report = _report(audited)
        reports[focal] = report
        runs.append({
            "run_id": raw["run_id"], "focal": focal,
            "manifest_sha256": _sha(path), "seed": raw["seed"], "engine": raw["engine"],
            "tuning": tuning, "heldout": heldout, "report": report,
        })
    focals = sorted(reports)
    if focals != sorted(AUTHORITATIVE_DECKS):
        raise ValueError("Ledger Baseline requires all three authoritative focal decks")
    return {
        "focals": focals, "source": source, "ledger": ledger,
        "contestants": {name: contestants[name] for name in sorted(contestants)},
        "behavior_identities": [identities[key] for key in sorted(identities)],
        "runs": runs, "reports": reports, "heldout_manifest": heldout_manifest,
        "tuning_owners": tuning_owners, "heldout_episode_ids": heldout_episode_ids,
    }


def correction_run_evidence(correction_runs) -> dict:
    data = _collect_runs(correction_runs)
    return certified_evidence({
        "source_identity": data["source"], "ledger": data["ledger"],
        "contestants": data["contestants"],
        "behavior_identities": data["behavior_identities"],
        "correction_runs": data["runs"],
    })


def certification_inventory(correction_runs) -> dict:
    data = _collect_runs(correction_runs)
    evidence = certified_evidence({
        "source_identity": data["source"], "ledger": data["ledger"],
        "contestants": data["contestants"],
        "behavior_identities": data["behavior_identities"],
        "correction_runs": data["runs"],
    })
    return {
        "evidence": evidence,
        "tuning_episode_ids": sorted(data["tuning_owners"]),
        "heldout_episode_ids": sorted(data["heldout_episode_ids"]),
    }


def correction_artifacts(sources) -> tuple[list[dict], list]:
    files = sorted({path for source in sources for path in jsonl_files(source)},
                   key=lambda value: str(value))
    artifacts, records = [], []
    for path in files:
        loaded = load_corrections(path, dedup=False)
        if not loaded or any(record.provenance != "human" for record in loaded):
            raise ValueError(f"invalid manual Correction artifact: {path}")
        artifacts.append({"path": str(path), "sha256": _sha(path), "records": len(loaded)})
        records.extend(loaded)
    return artifacts, records


def build_baseline(*, correction_runs, corrections, certification: Path | str,
                   current_source_identity: dict, known_weaknesses, created_at: str) -> dict:
    data = _collect_runs(correction_runs)
    if data["source"] != current_source_identity or current_source_identity.get("dirty"):
        raise ValueError("Ledger Baseline source identity is not the current clean source")
    artifacts, records = correction_artifacts(corrections)
    if not artifacts:
        raise ValueError("Ledger Baseline requires a manual Correction")
    if any(data["tuning_owners"].get(str(record.episode_id)) != record.agent
           for record in records):
        raise ValueError("manual Correction is not owned by its focal tuning partition")
    certification_path = Path(certification)
    report = validate_certification(json.loads(
        certification_path.read_text(encoding="utf-8")))
    corrections_identity = hashlib.sha256(_canonical(artifacts)).hexdigest()
    if report.get("corrections_identity") != corrections_identity:
        raise ValueError("Ledger Baseline certification used different Corrections")
    reviewed = {str(value) for value in report["manual_review"]["episode_ids"]}
    certified_heldout = {str(value) for value in report["heldout"]["episode_ids"]}
    if reviewed != set(data["tuning_owners"]):
        raise ValueError("Ledger Baseline manual review Episode set is incomplete")
    if certified_heldout != data["heldout_episode_ids"]:
        raise ValueError("Ledger Baseline held-out certification Episode set is incomplete")
    manifest = {
        "schema": SCHEMA, "schema_version": SCHEMA_VERSION, "baseline_id": None,
        "created_at": str(created_at), "focals": data["focals"],
        "source_identity": data["source"], "ledger": data["ledger"],
        "contestants": data["contestants"], "behavior_identities": data["behavior_identities"],
        "correction_runs": data["runs"], "reports": data["reports"],
        "heldout_manifest": data["heldout_manifest"], "corrections": artifacts,
        "corrections_identity": corrections_identity,
        "certification": {"path": str(certification_path),
                          "sha256": _sha(certification_path), "report": report},
        "blunder_policy": BLUNDER_POLICY, "known_weaknesses": list(known_weaknesses),
    }
    if report.get("evidence") != certified_evidence(manifest):
        raise ValueError("Ledger Baseline certification evidence does not match")
    manifest["baseline_id"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    return validate_baseline(manifest)


__all__ = ("build_baseline", "certification_inventory", "correction_artifacts",
           "correction_run_evidence")
