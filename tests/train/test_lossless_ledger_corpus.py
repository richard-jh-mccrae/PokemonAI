from __future__ import annotations

import json
import gzip
from pathlib import Path
from dataclasses import replace

import pyarrow.parquet as pq
import pytest

from ledger_helpers import printout
from common.api import ActionIdentity, RootDecision
from common.decision import (CandidateDisposition, CandidateRoster, ComputeConfiguration,
                             DecisionDelta, DecisionResult, EvaluationStatus, SearchResult,
                             StateValuation, ValueScale, ValuedCandidate)
from common.ledger import BehaviorIdentity, EvaluationModel
from common.observation import ObservationStateBuilder
from common.options import LegalAction
from common.telemetry import (build_decision_record, build_episode_receipt, build_pregame_record,
                              build_outcome_record, frame_record, runtime_provenance)
from train.corpus import (CorpusIntegrityError, CorpusRejection, build_snapshot, build_training_view,
                          certify_replay, load_episode_bundle, load_snapshot,
                          stage_episode_bundle)
from train.blunder.batch import discover_replays, load_game, load_replay_for_viewer


def _Action(identity, selection):
    return LegalAction(identity, selection, (selection,), ())


def _fixture_certificate(_decision: dict, _replay: dict) -> dict:
    return {
        "schema_version": 2, "mode": "offline_replay",
        "recorded_legal_actions_valid": True, "recorded_evaluation_valid": True,
        "recorded_successors_valid": True, "legal_actions_exact": True,
        "root_exact": True, "successors_exact": True, "full_choice_exact": True,
        "exclusion": None,
    }


def _fixture_provider_configuration() -> dict:
    return {
        "identity": "fixture-provider", "backend": "fixture",
        "factory": "tests.FixtureProvider", "version": 2,
        "kwargs": {}, "factory_kwargs": {},
    }


def _episode(tmp_path: Path, *, episode="42", include_pregame=False) -> tuple[Path, Path]:
    records = []
    parent_id = None
    if include_pregame:
        pregame_state = ObservationStateBuilder().root(printout(turn=0, select={
            "context": 0, "minCount": 1, "maxCount": 1, "option": [{"type": 14}],
        }))
        legal = pregame_state.legal_actions[0]
        pregame = build_pregame_record(
            RootDecision(legal.selection, legal.identity, 0.0, True, {}), pregame_state,
            episode_key=episode, decision_index=0, parent_decision_id=None,
            provenance={"agent": "fixture", "artifact": "test", "code": "abc", "data": {}},
            decision_seconds=0.001,
        )
        records.append(pregame)
        parent_id = pregame["record_id"]
    state = ObservationStateBuilder().root(printout())
    action = _Action(ActionIdentity("end_turn"), (0,))
    state = replace(state, legal_actions=(action,))
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "fixture-evaluator")
    candidate = ValuedCandidate(action, DecisionDelta(0.0, scale),
                                CandidateDisposition.FORCED, EvaluationStatus.COMPLETE)
    roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))
    behavior = BehaviorIdentity(
        "fixture-evaluator", "fixture-model", "fixture-search", "fixture-prior",
        "fixture-policy", "fixture-fail-safe", "fixture-provider", "fixture-compute",
        "fixture-prize-plan")
    decision = build_decision_record(
        DecisionResult(action, baseline, roster, SearchResult(baseline, roster),
                       behavior_identity=behavior), state,
        episode_key=episode, decision_index=int(include_pregame), parent_decision_id=parent_id,
        selection=(0,), evaluation_model=EvaluationModel.build(),
        compute_configuration=ComputeConfiguration(),
        provider_configuration=_fixture_provider_configuration(),
        provenance={"agent": "fixture", "artifact": "test", "code": "abc", "data": {}},
        decision_seconds=0.01,
    )
    records.append(decision)
    receipt = build_episode_receipt(episode_key=episode, reservations=[{
        "record_id": record["record_id"], "seat": record["decision"]["seat"],
        "index": record["decision"]["index"], "status": "delivered", "error_type": None,
    } for record in records])
    outcome = build_outcome_record(
        episode_key=episode, decision_records=records, telemetry_receipt=receipt, winner=0,
        terminal_reason="prizes_taken", public_prizes={0: 0, 1: 2},
        rewards={0: 1.0, 1: -1.0}, duration_seconds=3.5,
        external_episode_id=episode,
    )
    replay = tmp_path / "replay.json"
    replay.write_text(json.dumps({"info": {"EpisodeId": int(episode)}, "steps": []}),
                      encoding="utf-8")
    telemetry = tmp_path / "telemetry.jsonl"
    telemetry.write_text("\n".join((*(line for record in records for line in frame_record(record)),
                                    *frame_record(receipt),
                                    *frame_record(outcome))) + "\n",
                         encoding="utf-8")
    return replay, telemetry


def test_closed_bundle_publishes_snapshot_and_readable_diagnostic_view(tmp_path):
    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    snapshot = build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus",
                              replay_certifier=_fixture_certificate)
    manifest, rows = load_snapshot(snapshot)

    assert manifest["decision_count"] == 1
    assert rows[0]["terminal_target"]["seat_reward"] == 1.0
    assert rows[0]["supervision"]["human"] == {
        "accepted_action_ids": [], "annotations": []}
    assert rows[0]["origin"]["source_schema"] == "ledger.telemetry"
    assert rows[0]["origin"]["telemetry_receipt_id"]
    assert set(manifest["identities"]) == {
        "code", "data", "schema", "evaluator", "configuration", "provider", "behavior"}

    view = build_training_view(snapshot_path=snapshot, output_root=tmp_path / "views")
    table = pq.read_table(view / "part-00000.parquet")
    saved = table.to_pylist()[0]
    assert saved["episode_key"] == "42"
    assert saved["seat_reward"] == 1.0
    assert saved["replay_drift"] is False
    assert saved["policy_inconsistency"] is False
    assert json.loads((view / "manifest.json").read_text())["quality"]["status"] == "not_assessed"


def test_pregame_is_receipt_certified_and_explicitly_excluded_from_training(tmp_path):
    replay, telemetry = _episode(tmp_path, include_pregame=True)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    snapshot = build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus",
                              replay_certifier=_fixture_certificate)
    manifest, rows = load_snapshot(snapshot)

    assert len(rows) == 2
    excluded = next(row for row in rows if row.get("exclusion"))
    ledger = next(row for row in rows if not row.get("exclusion"))
    assert excluded["exclusion"] == {"reason": "pregame_not_ledger"}
    assert excluded["decision"]["decision"]["variant"] == "declarative_pregame"
    assert manifest["training_exclusions"] == [{
        "decision_id": manifest["training_exclusions"][0]["decision_id"],
        "bundle_id": manifest["bundle_ids"][0],
        "telemetry_receipt_id": ledger["origin"]["telemetry_receipt_id"],
        "reason": "pregame_not_ledger", "receipt_certified": True,
    }]


def test_health_is_only_unhealthy_against_a_named_profile_threshold(tmp_path):
    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    snapshot = build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus",
                              replay_certifier=_fixture_certificate)
    profile = tmp_path / "strict.json"
    profile.write_text(json.dumps({
        "name": "latency-test", "schema_version": 1,
        "thresholds": {"max_p95_decision_seconds": 0.001},
    }), encoding="utf-8")

    view = build_training_view(snapshot_path=snapshot, output_root=tmp_path / "views",
                               profile_path=profile)
    quality = json.loads((view / "manifest.json").read_text())["quality"]
    assert quality["status"] == "unhealthy"
    assert quality["violations"][0]["actual"] == 0.01


def test_publication_is_deterministic_and_reuses_content_addressed_artifacts(tmp_path):
    replay, telemetry = _episode(tmp_path)
    first_bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                        output_root=tmp_path / "bundles")
    second_bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                         output_root=tmp_path / "bundles")
    first = build_snapshot(bundles_root=tmp_path / "bundles", output_root=tmp_path / "corpus",
                           replay_certifier=_fixture_certificate)
    before = (first / "decisions-00000.jsonl.gz").read_bytes()
    second = build_snapshot(bundles_root=tmp_path / "bundles", output_root=tmp_path / "corpus",
                            replay_certifier=_fixture_certificate)

    assert first_bundle == second_bundle
    assert first == second
    assert (second / "decisions-00000.jsonl.gz").read_bytes() == before
    assert json.loads((tmp_path / "corpus" / "latest.json").read_text())["snapshot_id"] == first.name


def test_episode_bundle_v3_compresses_replay_and_telemetry_without_losing_records(tmp_path):
    replay, telemetry = _episode(tmp_path)

    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    loaded_manifest, decisions, receipt, outcome, loaded_replay = load_episode_bundle(bundle)

    assert manifest["schema_version"] == 3
    assert set(manifest["files"]) == {"replay.json.gz", "telemetry.jsonl.gz"}
    assert loaded_manifest == manifest
    assert len(decisions) == 1 and receipt["certified"] and outcome["record_type"] == "outcome"
    assert loaded_replay["info"]["EpisodeId"] == 42


def test_correction_viewer_loads_the_replay_without_waiting_on_bundle_telemetry(tmp_path):
    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    (bundle / "telemetry.jsonl.gz").unlink()

    viewed = load_replay_for_viewer(bundle)

    assert viewed["info"]["EpisodeId"] == 42


def test_episode_bundle_reader_keeps_v2_compatibility(tmp_path):
    from train.corpus.io import digest_file

    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] == 3:
        import gzip

        (bundle / "replay.json").write_bytes(gzip.decompress((bundle / "replay.json.gz").read_bytes()))
        (bundle / "telemetry.jsonl").write_bytes(
            gzip.decompress((bundle / "telemetry.jsonl.gz").read_bytes()))
        (bundle / "replay.json.gz").unlink()
        (bundle / "telemetry.jsonl.gz").unlink()
    manifest["schema_version"] = 2
    manifest["files"] = {
        "replay.json": digest_file(bundle / "replay.json"),
        "telemetry.jsonl": digest_file(bundle / "telemetry.jsonl"),
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    loaded_manifest, decisions, receipt, outcome, loaded_replay = load_episode_bundle(bundle)

    assert loaded_manifest["schema_version"] == 2
    assert len(decisions) == 1 and receipt["certified"] and outcome["record_type"] == "outcome"
    assert loaded_replay["info"]["EpisodeId"] == 42


def test_correction_loader_reads_tuning_bundles_and_hides_heldout(tmp_path):
    replay, telemetry = _episode(tmp_path)
    run_dir = tmp_path / "run"
    tuning = stage_episode_bundle(
        replay_path=replay, telemetry_path=telemetry,
        output_root=run_dir / "bundles" / "tuning")
    heldout = stage_episode_bundle(
        replay_path=replay, telemetry_path=telemetry,
        output_root=run_dir / "bundles" / "heldout")
    (run_dir / "manifest.json").write_text(json.dumps({
        "schema": "ledger.correction-run", "run_id": "run-1", "focal": "mega_starmie",
        "source_identity": {"commit": "abc123"},
        "slots": [
            {"bundle_id": tuning.name, "partition": "tuning", "focal_seat": 0},
            {"bundle_id": heldout.name, "partition": "heldout", "focal_seat": 1},
        ],
    }), encoding="utf-8")

    games = discover_replays(run_dir)
    game = load_game(games[0])

    assert games == [tuning]
    assert game["replay"]["info"]["EpisodeId"] == 42
    assert game["live_seat"] == 0
    assert len(game["live_records_by_seat"][0]) == 1
    assert game["agent"] == "mega_starmie"
    assert game["agent_build"] == "run-1"
    assert game["agent_version"] == "abc123"
    with pytest.raises(ValueError, match="held-out"):
        discover_replays(heldout)
    with pytest.raises(ValueError, match="held-out"):
        load_game(heldout)
    with pytest.raises(ValueError, match="held-out"):
        load_replay_for_viewer(heldout)


def test_partial_corrupt_unknown_and_legacy_evidence_never_publish(tmp_path):
    replay, telemetry = _episode(tmp_path)
    lines = telemetry.read_text(encoding="utf-8").splitlines()

    telemetry.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                             output_root=tmp_path / "partial")

    telemetry.write_text('@T {"bellman":true,"chosen":[0]}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                             output_root=tmp_path / "legacy")


def test_bundle_hash_tampering_blocks_snapshot_publication(tmp_path):
    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    replay_name = next(name for name in manifest["files"] if name.startswith("replay."))
    (bundle / replay_name).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus",
                       replay_certifier=_fixture_certificate)


def test_integrity_gate_collects_replay_rejections_without_advancing_latest(tmp_path):
    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")

    def reject(decision, _replay):
        raise ValueError(f"cannot resolve {decision['record_id']}")

    with pytest.raises(CorpusIntegrityError) as caught:
        build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus",
                       replay_certifier=reject)

    assert len(caught.value.rejections) == 1
    assert not (tmp_path / "corpus" / "latest.json").exists()


def test_unjustified_full_choice_omission_is_a_corpus_rejection(tmp_path):
    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")

    def omitted(_decision, _replay):
        return {**_fixture_certificate({}, {}), "full_choice_exact": None}

    with pytest.raises(CorpusIntegrityError, match="full_choice_exact"):
        build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus",
                       replay_certifier=omitted)
    assert not (tmp_path / "corpus" / "latest.json").exists()


@pytest.fixture(scope="module")
def replay_evidence():
    from train.blunder.decisions import iter_decisions
    from train.ledger_corpus import _build_runtime

    replay_path = Path(__file__).resolve().parents[1] / "fixtures" / "episode-82749168-replay.json.gz"
    with gzip.open(replay_path, "rt", encoding="utf-8") as source:
        replay = json.load(source)
    decisions = iter_decisions(replay)
    frame = next(item for item in decisions if item.obs is not None and item.turn > 0)
    decision_index = [item for item in decisions if item.seat == frame.seat].index(frame)
    runtime = _build_runtime("mega_starmie", weight_overrides={"zone.in_hand": 7.0})
    root = runtime.decide(frame.obs)
    record = build_decision_record(
        root.decision_result, runtime.last_state,
        episode_key=str(frame.episode_id), decision_index=decision_index,
        parent_decision_id=None, selection=tuple(root.chosen),
        evaluation_model=runtime.ledger.ctx, compute_configuration=runtime.ledger.compute,
        provider_configuration=runtime.ledger.provider_configuration,
        provenance=runtime_provenance(deck_name="mega_starmie"),
        decision_seconds=0.01, opponent_snapshot=runtime.opponent_snapshot,
    )
    return record, replay


def test_offline_replay_certifies_recorded_ledger_evaluation(replay_evidence):
    record, replay = replay_evidence

    certificate = certify_replay(record, replay)
    assert certificate["mode"] == "offline_replay"
    assert certificate["legal_actions_exact"] is True
    assert certificate["root_exact"] is True
    assert certificate["successors_exact"] is True


def test_unresolved_identity_and_provider_substitution_reject_before_publication(replay_evidence):
    record, replay = replay_evidence
    unresolved = json.loads(json.dumps(record))
    unresolved["provenance"]["agent"] = "missing-agent"
    with pytest.raises(CorpusRejection, match="agent_artifact_unavailable"):
        certify_replay(unresolved, replay)

    substituted = json.loads(json.dumps(record))
    substituted["configuration"]["provider"]["backend"] = "native-cg-ledger"
    with pytest.raises(CorpusRejection, match="provider_substitution"):
        certify_replay(substituted, replay)


@pytest.mark.parametrize(("mutation", "reason"), [
    (lambda row: row["actions"].reverse(), "legal_actions_drift"),
    (lambda row: row["root"].__setitem__("total", row["root"]["total"] + 1.0),
     "root_valuation_drift"),
    (lambda row: row["root"]["components"][0].__setitem__(
        "activation", row["root"]["components"][0]["activation"] + 1.0),
     "root_valuation_drift"),
    (lambda row: row["root"]["components"][0].__setitem__(
        "value", row["root"]["components"][0]["value"] + 1.0),
     "root_valuation_drift"),
    (lambda row: row["candidates"][0]["delta"].__setitem__(
        "total", row["candidates"][0]["delta"]["total"] + 1.0),
     "successor_evaluation_drift"),
])
def test_exact_replay_rejects_legal_root_activation_contribution_and_successor_drift(
        replay_evidence, mutation, reason):
    record, replay = replay_evidence
    changed = json.loads(json.dumps(record))
    mutation(changed)
    with pytest.raises(CorpusRejection, match=reason):
        certify_replay(changed, replay)
