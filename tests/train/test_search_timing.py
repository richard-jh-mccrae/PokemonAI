import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cgpy.experiment import TeacherSearchConfiguration
from cgpy.experiment.teacher_contracts import TeacherSearchStatistics
from train import search_timing


CORPUS = search_timing.DEFAULT_CORPUS


class _FakeTeacherResult:
    def __init__(self, case, elapsed):
        self.coverage = SimpleNamespace(value="complete")
        self.stop_reason = SimpleNamespace(value="complete")
        self.failure = None
        self.statistics = TeacherSearchStatistics(
            nodes_visited=10, leaf_evaluations=4, elapsed_seconds=elapsed)
        self.evaluator_identity = search_timing.LedgerValueEvaluator.identity
        self.evaluation_model_identity = case.model.evaluation_model_identity
        self.baseline_identity = case.baseline_identity
        self.semantic_identity = f"semantic-{case.case_id}"
        self._state = f"state-{case.case_id.rsplit(':', 1)[0]}"

    def document(self):
        action = {"kind": "end", "parts": []}
        return {
            "root_state_key": self._state,
            "preferred_action": action,
            "selected_policy": [],
            "leaves": [{"state_key": "leaf", "probability": 1.0, "value": 1.0}],
            "best_full_sequence": [action],
        }


class _FakeRunner:
    def run(self, cases, configuration):
        assert configuration.workers == 2
        assert all(case.parity is not None for case in cases)
        items = tuple(SimpleNamespace(
            case_id=case.case_id,
            status=SimpleNamespace(value="completed"),
            stop_reason=SimpleNamespace(value="complete"),
            failure=None,
            result=_FakeTeacherResult(case, index + 0.25),
        ) for index, case in enumerate(cases))
        return SimpleNamespace(items=items, elapsed_seconds=3.0)


def test_declared_roots_cover_each_deck_and_timing_stratum_once():
    specs = search_timing.root_specs()

    assert len(specs) == 9
    assert {(spec.agent, spec.stratum) for spec in specs} == {
        (agent, stratum)
        for agent in search_timing.AGENTS for stratum in search_timing.STRATA}
    assert len({spec.root_id for spec in specs}) == len(specs)
    assert search_timing.default_workers() <= 8


def test_committed_search_timing_corpus_is_complete_and_compatible():
    manifest, parity = search_timing.load_corpus(CORPUS)

    assert manifest["selection"]["held_out_quality_evidence"] is False
    assert len(manifest["cases"]) == 9
    assert parity.identity == manifest["parity"]["identity"]


def test_corpus_rejects_changed_artifact(tmp_path):
    import shutil

    copied = tmp_path / "corpus"
    shutil.copytree(CORPUS, copied)
    artifact = next((copied / "cases").glob("*.json"))
    artifact.write_text(artifact.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact changed"):
        search_timing.load_corpus(copied)


def test_teacher_run_records_repeatable_targets_and_latency_summary(tmp_path):
    output = search_timing.run_teacher(
        CORPUS, output=tmp_path / "run.json", workers=2, repetitions=2,
        roots=("starmie-opening",),
        search_configuration=TeacherSearchConfiguration(time_cap_seconds=1.0),
        root_timeout_seconds=2.0, runner=_FakeRunner())

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["method"] == "teacher_exhaustive"
    assert document["summary"]["requested_roots"] == 2
    assert document["summary"]["median_seconds"] == 0.75
    assert document["summary"]["p95_seconds"] == 1.25
    assert document["summary"]["per_root"][0]["reference_target_stable"] is True
    assert all(row["reference_ready"] for row in document["results"])
    assert all(len(row["reference_target"]["target_id"]) == 64
               for row in document["results"])


def test_cli_exposes_worker_repetition_and_teacher_budgets():
    help_text = search_timing._parser().format_help()
    run_help = search_timing._parser()._subparsers._group_actions[0].choices[
        "run"].format_help()

    assert "capture" in help_text and "verify" in help_text and "run" in help_text
    for option in ("--jobs", "--repetitions", "--time-cap", "--root-timeout",
                   "--node-cap", "--chance-branch-cap"):
        assert option in run_help
