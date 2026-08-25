import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
FOCALS = ("dragapult_ex", "mega_lucario", "mega_starmie")
SOURCE = {"commit": "abc", "dirty": False}
LEDGER = {"evaluator": "ledger-linear-v1", "feature_schema_version": 1,
          "global_configuration_sha256": "a" * 64}


def _bundle(run: Path, partition: str, episode: int) -> Path:
    from common.api import ActionIdentity
    from common.decision import (CandidateDisposition, CandidateRoster, ComputeConfiguration,
                                 DecisionDelta, DecisionResult, EvaluationStatus, SearchResult,
                                 StateValuation, ValueScale, ValuedCandidate)
    from common.ledger import EvaluationModel
    from common.observation import ObservationStateBuilder
    from common.options import LegalAction
    from common.telemetry import (build_decision_record, build_episode_receipt,
                                  build_outcome_record, frame_record)
    from ledger_helpers import printout
    from train.corpus import stage_episode_bundle

    state = ObservationStateBuilder().root(printout())
    action = LegalAction(ActionIdentity("end_turn"), (0,), ((0,),), ())
    state = replace(state, legal_actions=(action,))
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "fixture")
    candidate = ValuedCandidate(action, DecisionDelta(0.0, scale),
                                CandidateDisposition.FORCED, EvaluationStatus.COMPLETE)
    roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))
    decision = build_decision_record(
        DecisionResult(action, baseline, roster, SearchResult(baseline, roster)), state,
        episode_key=str(episode), decision_index=0, parent_decision_id=None, selection=(0,),
        evaluation_model=EvaluationModel.build(), compute_configuration=ComputeConfiguration(),
        provider_configuration={
            "identity": "fixture-provider", "backend": "fixture",
            "factory": "tests.FixtureProvider", "version": 2,
            "kwargs": {}, "factory_kwargs": {},
        },
        provenance={"agent": "fixture", "artifact": "test", "code": "abc", "data": {}},
        decision_seconds=0.01)
    receipt = build_episode_receipt(episode_key=str(episode), reservations=[{
        "record_id": decision["record_id"], "seat": decision["decision"]["seat"],
        "index": decision["decision"]["index"], "status": "delivered", "error_type": None,
    }])
    outcome = build_outcome_record(
        episode_key=str(episode), decision_records=[decision], telemetry_receipt=receipt, winner=0,
        terminal_reason="prizes_taken", public_prizes={0: 0, 1: 2},
        rewards={0: 1.0, 1: -1.0}, duration_seconds=1.0,
        external_episode_id=str(episode))
    source = run / f"source-{episode}"
    source.mkdir(parents=True)
    replay = source / "replay.json"
    choice = decision["decision"]
    replay.write_text(json.dumps({
        "info": {"EpisodeId": episode},
        "steps": [[{"visualize": [
            {"current": {"yourIndex": choice["seat"], "turn": choice["turn"]},
             "select": {"option": [{}], "context": None, "type": "Main"}},
            {"selected": [0]},
        ]}]],
    }), encoding="utf-8")
    telemetry = source / "telemetry.jsonl"
    telemetry.write_text("\n".join((*frame_record(decision), *frame_record(receipt),
                                     *frame_record(outcome))) + "\n",
                         encoding="utf-8")
    return stage_episode_bundle(
        replay_path=replay, telemetry_path=telemetry,
        output_root=run / "bundles" / partition)


def _run(tmp_path, focal: str, offset: int, *, status="complete", heldout=True, dirty=False):
    from train.corpus import load_episode_bundle
    from train.corpus.evidence import audit_correction_records

    run = tmp_path / f"run-{focal}"
    run.mkdir(parents=True)
    tuning = _bundle(run, "tuning", offset)
    heldout_bundle = _bundle(run, "heldout", offset + 1) if heldout else None

    def audit(bundle):
        _manifest, decisions, _receipt, _outcome, replay = load_episode_bundle(bundle)
        return audit_correction_records(decisions, replay=replay)

    slots = [{
        "index": 0, "episode_id": offset, "partition": "tuning", "status": "complete",
        "opponent": focal, "focal_seat": 0, "focal_result": "win", "engine_seed": offset,
        "bundle_id": tuning.name, "bundle_path": f"bundles/tuning/{tuning.name}",
        "audit": audit(tuning),
    }]
    if heldout_bundle is not None:
        slots.append({
            "index": 1, "episode_id": offset + 1, "partition": "heldout",
            "status": "complete", "opponent": focal, "focal_seat": 1,
            "focal_result": "loss", "engine_seed": offset + 1,
            "bundle_id": heldout_bundle.name,
            "bundle_path": f"bundles/heldout/{heldout_bundle.name}",
            "audit": audit(heldout_bundle),
        })
    manifest = {
        "schema": "ledger.correction-run", "schema_version": 1,
        "run_id": f"run-{focal}", "status": status, "focal": focal,
        "seed": offset, "engine": {"kind": "cgpy", "seeded": True},
        "ledger": LEDGER, "source_identity": {"commit": "abc", "dirty": dirty},
        "contestants": {focal: {"deck_sha256": focal, "ledger_overlay_sha256": "b" * 64}},
        "slots": slots,
        "totals": {"planned": len(slots), "complete": len(slots),
                   "failed": 0, "bytes": 100},
    }
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run


def _runs(tmp_path):
    return [_run(tmp_path, focal, 10 + index * 10) for index, focal in enumerate(FOCALS)]


def _corrections(tmp_path):
    from train.blunder.correction import build_correction
    from train.blunder.decisions import Decision

    path = tmp_path / "corrections.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for index, focal in enumerate(FOCALS):
        episode = 10 + index * 10
        decision = Decision(episode, 1, 0, 1, "Main", "Main", [{}, {}], [0], {})
        records.append(build_correction(
            decision, source="own", agent=focal, correct=[1], category="other",
            rationale="Prefer the better line.").to_dict())
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n",
                    encoding="utf-8")
    return path


def _certification(tmp_path, runs, corrections):
    import hashlib
    from train.baseline import certification_inventory, correction_artifacts

    inventory = certification_inventory(runs)
    artifacts, _records = correction_artifacts([corrections])
    corrections_identity = hashlib.sha256(json.dumps(
        artifacts, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    path = tmp_path / "certification.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    gates = [{"name": name, "passed": True, "command": "pytest",
              "output_sha256": "c" * 64} for name in (
        "historical_corrections", "cross_deck_regressions",
        "native_full_games", "twin_full_games")]
    path.write_text(json.dumps({
        "passed": True, "gates": gates,
        "manual_review": {"completed": True,
                          "reviewed_decisions": inventory["evidence"]["tuning_ledger_decisions"],
                          "episode_ids": inventory["tuning_episode_ids"]},
        "heldout": {"passed": True, "episode_ids": inventory["heldout_episode_ids"]},
        "tuning_target": {"name": "agreement", "before": 0.5, "after": 0.6},
        "regressions": {"passed": True, "unreported": []},
        "corrections_identity": corrections_identity,
        "evidence": inventory["evidence"],
    }), encoding="utf-8")
    return path


def _build(tmp_path, **overrides):
    from train.baseline import build_baseline

    runs = overrides.pop("correction_runs", None)
    runs = _runs(tmp_path) if runs is None else runs
    corrections = overrides.pop("corrections", None)
    corrections = _corrections(tmp_path) if corrections is None else corrections
    certification = overrides.pop("certification", None)
    certification = (_certification(tmp_path, runs, corrections)
                     if certification is None else certification)
    return build_baseline(
        correction_runs=runs, corrections=[corrections], certification=certification,
        current_source_identity=overrides.pop("current_source_identity", SOURCE),
        known_weaknesses=overrides.pop("known_weaknesses", ["one-ply only"]),
        created_at="2026-08-25T00:00:00+00:00", **overrides)


def test_three_deck_baseline_freeze_is_complete(tmp_path):
    from common.ledger.baseline import validate_baseline

    baseline = _build(tmp_path)
    assert baseline["focals"] == list(FOCALS)
    assert set(baseline["reports"]) == set(FOCALS)
    assert all(baseline["heldout_manifest"][focal][0]["decisions"] for focal in FOCALS)
    assert baseline["ledger"] == LEDGER
    assert baseline["corrections_identity"]
    assert validate_baseline(baseline) == baseline


def test_ledger_baseline_identity_mismatch_fails_loud(tmp_path):
    from common.ledger.baseline import require_baseline

    baseline = _build(tmp_path)
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    assert require_baseline(baseline["baseline_id"], path)["baseline_id"] == baseline["baseline_id"]
    with pytest.raises(ValueError, match="baseline identity mismatch"):
        require_baseline("wrong", path)


def test_ledger_baseline_requires_all_authoritative_decks(tmp_path):
    runs = _runs(tmp_path)
    corrections = _corrections(tmp_path)
    with pytest.raises(ValueError, match="all three"):
        _build(tmp_path / "build", correction_runs=runs[:2],
               corrections=corrections,
               certification=_certification(tmp_path, runs[:2], corrections))


def test_ledger_baseline_reaudits_bundles_and_requires_current_source(tmp_path):
    runs = _runs(tmp_path)
    corrections = _corrections(tmp_path)
    certification = _certification(tmp_path, runs, corrections)
    manifest_path = runs[0] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["slots"][0]["audit"]["ledger_decisions"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="audit mismatch"):
        _build(tmp_path / "build", correction_runs=runs, certification=certification,
               corrections=corrections)

    source_root = tmp_path / "source"
    runs = _runs(source_root)
    corrections = _corrections(source_root)
    with pytest.raises(ValueError, match="current clean source"):
        _build(source_root / "build", correction_runs=runs,
               certification=_certification(source_root, runs, corrections),
               corrections=corrections,
               current_source_identity={"commit": "new", "dirty": False})


def test_certification_binds_exact_evidence_and_all_reviewed_decisions(tmp_path):
    runs = _runs(tmp_path)
    corrections = _corrections(tmp_path)
    certification = _certification(tmp_path, runs, corrections)
    report = json.loads(certification.read_text(encoding="utf-8"))
    report["evidence"]["heldout_bundle_ids"] = ["substituted"]
    certification.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="certification evidence"):
        _build(tmp_path / "build", correction_runs=runs, certification=certification,
               corrections=corrections)

    certification = _certification(tmp_path, runs, corrections)
    report = json.loads(certification.read_text(encoding="utf-8"))
    report["manual_review"]["reviewed_decisions"] -= 1
    certification.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="decision count"):
        _build(tmp_path / "build-2", correction_runs=runs, certification=certification,
               corrections=corrections)


def test_certification_binds_the_exact_correction_artifacts(tmp_path):
    runs = _runs(tmp_path)
    certified = _corrections(tmp_path / "certified")
    certification = _certification(tmp_path, runs, certified)
    substituted = _corrections(tmp_path / "substituted")

    with pytest.raises(ValueError, match="different Corrections"):
        _build(tmp_path / "build", correction_runs=runs, certification=certification,
               corrections=substituted)


def test_ledger_baseline_and_certification_clis_expose_the_contract():
    baseline = subprocess.run(
        [sys.executable, str(REPO / "tools" / "train" / "ledger_baseline.py"), "--help"],
        cwd=REPO, capture_output=True, text=True, check=False)
    certify = subprocess.run(
        [sys.executable, str(REPO / "tools" / "train" / "ledger_certify.py"), "--help"],
        cwd=REPO, capture_output=True, text=True, check=False)
    assert baseline.returncode == certify.returncode == 0
    assert "--run" in baseline.stdout and "--certification" in baseline.stdout
    assert "--reviewed-decisions" in certify.stdout
    assert "--corrections" in certify.stdout
    assert "--before-report" in certify.stdout
    assert "--evidence-dir" in certify.stdout


def test_certification_builder_runs_all_fixed_gates_and_binds_evidence(tmp_path):
    from types import SimpleNamespace
    from train.baseline import certification_inventory
    from train.ledger_certify import build_certification

    runs = _runs(tmp_path)
    corrections = _corrections(tmp_path)
    inventory = certification_inventory(runs)
    before = tmp_path / "before.json"
    before.write_text(json.dumps({
        "schema": 1, "git_rev": "before-revision", "rows": [{"id": "one"}],
        "generality_floor": 0.5,
    }), encoding="utf-8")
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        if "--output" in command:
            artifact = Path(command[command.index("--output") + 1])
            artifact.write_text(json.dumps({
                "schema": 1, "git_rev": "after-revision", "rows": [{"id": "one"}],
                "generality_floor": 0.6, "baseline_git_rev": "before-revision",
                "baseline_generality_floor": 0.5, "unexplained_regressions": [],
                "generality_floor_retained": True,
            }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    report = build_certification(
        correction_runs=runs,
        reviewed_decisions=inventory["evidence"]["tuning_ledger_decisions"],
        corrections=[corrections],
        before_report=before, evidence_dir=tmp_path / "evidence", runner=runner)

    assert report["passed"] is True
    assert len(commands) == 4
    assert report["evidence"] == inventory["evidence"]
    assert report["tuning_target"] == {
        "name": "generality_floor", "before": 0.5, "after": 0.6,
    }
