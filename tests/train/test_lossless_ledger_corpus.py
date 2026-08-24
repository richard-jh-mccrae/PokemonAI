from __future__ import annotations

import json
import gzip
from pathlib import Path
from dataclasses import dataclass

import pyarrow.parquet as pq
import pytest

from ledger_helpers import printout
from common.api import ActionIdentity
from common.decision import (CandidateDisposition, CandidateRoster, ComputeConfiguration,
                             DecisionDelta, DecisionResult, EvaluationStatus, SearchResult,
                             StateValuation, ValueScale, ValuedCandidate)
from common.ledger import EvaluationModel
from common.observation import ObservationStateBuilder
from common.telemetry import (build_decision_record, build_outcome_record, frame_record,
                              runtime_provenance)
from train.corpus import (build_snapshot, build_training_view, certify_replay, load_snapshot,
                          stage_episode_bundle)


@dataclass(frozen=True)
class _Action:
    identity: ActionIdentity
    selection: tuple[int, ...]


def _episode(tmp_path: Path, *, episode="42") -> tuple[Path, Path]:
    state = ObservationStateBuilder().root(printout())
    action = _Action(ActionIdentity("end_turn"), (0,))
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "fixture-evaluator")
    candidate = ValuedCandidate(action, DecisionDelta(0.0, scale),
                                CandidateDisposition.FORCED, EvaluationStatus.COMPLETE)
    roster = CandidateRoster((candidate,))
    decision = build_decision_record(
        DecisionResult(action, baseline, roster, SearchResult(baseline, roster)), state,
        episode_key=episode, decision_index=0, parent_decision_id=None,
        selection=(0,), evaluation_model=EvaluationModel.build(),
        compute_configuration=ComputeConfiguration(),
        provenance={"agent": "fixture", "artifact": "test", "code": "abc", "data": {}},
        decision_seconds=0.01,
    )
    outcome = build_outcome_record(
        episode_key=episode, decision_records=[decision], winner=0,
        terminal_reason="prizes_taken", public_prizes={0: 0, 1: 2},
        rewards={0: 1.0, 1: -1.0}, duration_seconds=3.5,
        external_episode_id=episode,
    )
    replay = tmp_path / "replay.json"
    replay.write_text(json.dumps({"info": {"EpisodeId": int(episode)}, "steps": []}),
                      encoding="utf-8")
    telemetry = tmp_path / "telemetry.jsonl"
    telemetry.write_text("\n".join((*frame_record(decision), *frame_record(outcome))) + "\n",
                         encoding="utf-8")
    return replay, telemetry


def test_closed_bundle_publishes_snapshot_and_readable_diagnostic_view(tmp_path):
    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    snapshot = build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus")
    manifest, rows = load_snapshot(snapshot)

    assert manifest["decision_count"] == 1
    assert rows[0]["terminal_target"]["seat_reward"] == 1.0
    assert rows[0]["supervision"]["human"] == {
        "accepted_action_ids": [], "annotations": []}
    assert rows[0]["origin"]["source_schema"] == "ledger.telemetry"

    view = build_training_view(snapshot_path=snapshot, output_root=tmp_path / "views")
    table = pq.read_table(view / "part-00000.parquet")
    saved = table.to_pylist()[0]
    assert saved["episode_key"] == "42"
    assert saved["seat_reward"] == 1.0
    assert saved["replay_drift"] is None
    assert saved["policy_inconsistency"] is False
    assert json.loads((view / "manifest.json").read_text())["quality"]["status"] == "not_assessed"


def test_health_is_only_unhealthy_against_a_named_profile_threshold(tmp_path):
    replay, telemetry = _episode(tmp_path)
    bundle = stage_episode_bundle(replay_path=replay, telemetry_path=telemetry,
                                  output_root=tmp_path / "bundles")
    snapshot = build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus")
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
    first = build_snapshot(bundles_root=tmp_path / "bundles", output_root=tmp_path / "corpus")
    before = (first / "decisions-00000.jsonl.gz").read_bytes()
    second = build_snapshot(bundles_root=tmp_path / "bundles", output_root=tmp_path / "corpus")

    assert first_bundle == second_bundle
    assert first == second
    assert (second / "decisions-00000.jsonl.gz").read_bytes() == before
    assert json.loads((tmp_path / "corpus" / "latest.json").read_text())["snapshot_id"] == first.name


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
    (bundle / "replay.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_snapshot(bundles_root=bundle, output_root=tmp_path / "corpus")


def test_offline_replay_certifies_recorded_ledger_evaluation():
    from train.blunder.decisions import iter_decisions
    from train.ledger_corpus import _build_runtime

    replay_path = Path(__file__).resolve().parents[1] / "fixtures" / "episode-82749168-replay.json.gz"
    with gzip.open(replay_path, "rt", encoding="utf-8") as source:
        replay = json.load(source)
    decisions = iter_decisions(replay)
    frame = next(item for item in decisions if item.obs is not None and item.turn > 0)
    decision_index = [item for item in decisions if item.seat == frame.seat].index(frame)
    runtime = _build_runtime("mega_starmie")
    root = runtime.decide(frame.obs)
    record = build_decision_record(
        root.decision_result, runtime.last_state,
        episode_key=str(frame.episode_id), decision_index=decision_index,
        parent_decision_id=None, selection=tuple(root.chosen),
        evaluation_model=runtime.ledger.ctx, compute_configuration=runtime.ledger.compute,
        provenance=runtime_provenance(deck_name="mega_starmie"),
        decision_seconds=0.01, opponent_snapshot=runtime.opponent_snapshot,
    )

    certificate = certify_replay(record, replay)
    assert certificate["mode"] == "offline_replay"
    assert certificate["legal_actions_exact"] is True
    assert certificate["root_exact"] is True
    assert certificate["successors_exact"] is True
