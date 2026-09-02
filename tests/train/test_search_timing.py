import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cgpy.experiment import (
    ExperimentSnapshot, NodeKind, TeacherSearchConfiguration, TeacherStopReason,
    TurnSearchEnvironment, admissible_teacher_actions,
)
from cgpy.experiment.teacher_contracts import TeacherSearchStatistics
from train import search_timing


CORPUS = search_timing.DEFAULT_CORPUS


class _FakeTeacherResult:
    def __init__(self, searcher, seed):
        self.coverage = SimpleNamespace(value="complete")
        self.stop_reason = SimpleNamespace(value="complete")
        self.failure = None
        self.statistics = TeacherSearchStatistics(
            nodes_visited=10, leaf_evaluations=4, elapsed_seconds=0.01)
        self.evaluator_identity = search_timing.LedgerValueEvaluator.identity
        self.evaluation_model_identity = searcher.model.evaluation_model_identity
        self.baseline_identity = searcher.baseline_identity
        self.configuration_identity = searcher.search_configuration.identity
        self.semantic_identity = f"semantic-{seed}"
        self._state = f"state-{seed}"

    def document(self):
        action = {"kind": "end", "parts": []}
        return {
            "root_state_key": self._state,
            "preferred_action": action,
            "selected_policy": [],
            "leaves": [{"state_key": "leaf", "probability": 1.0, "value": 1.0}],
            "best_full_sequence": [action],
        }


class _FakeSearcher:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def search(self, *, engine, perspective_seat, knowledge, experiment_seed, timeout_seconds):
        assert self.workers == 2
        assert engine.select_seat == perspective_seat == 0
        assert knowledge is not None
        assert timeout_seconds == self.root_timeout_seconds
        return SimpleNamespace(result=_FakeTeacherResult(self, experiment_seed))


def test_declared_roots_cover_each_deck_and_timing_stratum_plus_tutor_regression():
    specs = search_timing.root_specs()

    assert len(specs) == 10
    assert len(search_timing.root_specs(1)) == 9
    assert {(spec.agent, spec.stratum) for spec in specs} == {
        (agent, stratum)
        for agent in search_timing.AGENTS for stratum in search_timing.STRATA}
    assert len({spec.root_id for spec in specs}) == len(specs)
    assert search_timing.default_workers() <= 8


@pytest.mark.parametrize("version,count", [(1, 9), (2, 10)])
def test_committed_search_timing_corpus_is_complete_and_compatible(version, count):
    manifest, parity = search_timing.load_corpus(CORPUS.with_name(f"v{version}"))

    assert manifest["selection"]["held_out_quality_evidence"] is False
    assert len(manifest["cases"]) == count
    assert parity.identity == manifest["parity"]["identity"]


def test_corpus_rejects_changed_artifact(tmp_path):
    import shutil

    copied = tmp_path / "corpus"
    shutil.copytree(CORPUS, copied)
    artifact = next((copied / "cases").glob("*.json"))
    artifact.write_text(artifact.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact changed"):
        search_timing.load_corpus(copied)


@pytest.mark.parametrize("card_id,counts", [
    (1086, [(3, 1)]), (1145, [(2, 1)]), (1189, [(2, 1), (1, 1)]),
    (1225, [(3, 1), (3, 2)]),
])
def test_tutor_root_exercises_forced_fetches_without_shuffle_chance(card_id, counts):
    snapshot = ExperimentSnapshot.load(CORPUS / "snapshots/starmie-tutor-chain.snapshot.json.gz")
    engine = snapshot.fork_engine()
    assert engine.gs.turn == 2 and engine.gs.first_player == 1
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    play = next(action for action in environment.legal_actions(environment.root)
                if action.identity.kind == "play" and engine.gs.card_id(engine.gs.players[0].hand[
                    engine.gs.pending.options[action.selection[0]]["index"]]) == card_id)
    node = environment.transition(environment.root, play.identity).node
    for before, after in counts:
        observation = environment.observation(node)
        actions = environment.legal_actions(node)
        pruned = admissible_teacher_actions(
            observation, actions, search_timing.teacher_action_policy_for_agent("mega_starmie"))
        assert (len(actions), len(pruned)) == (before, after)
        assert all(action.selection for action in pruned)
        if card_id == 1086:
            assert len(pruned[0].selection) == 2
        node = environment.transition(node, pruned[0].identity).node
    assert environment.node_kind(node) is NodeKind.PLAYER_DECISION


def test_teacher_run_records_repeatable_targets_and_decision_wall_latency(tmp_path, monkeypatch):
    clock = iter((0, 0, 0.25, 0.25, 1.5, 1.5))
    monkeypatch.setattr(search_timing, "perf_counter", lambda: next(clock))
    monkeypatch.setattr(search_timing, "IsolatedTeacherSearcher", _FakeSearcher)
    output = search_timing.run_teacher(
        CORPUS, output=tmp_path / "run.json", workers=2, repetitions=2,
        roots=("starmie-opening",),
        search_configuration=TeacherSearchConfiguration(time_cap_seconds=1.0),
        root_timeout_seconds=2.0)

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["method"] == "teacher_exhaustive"
    assert document["method_identity"] == search_timing.WithinHorizonTeacher.identity
    assert document["source_identity"]["commit"]
    assert document["summary"]["requested_roots"] == 2
    assert document["summary"]["median_seconds"] == 0.75
    assert document["summary"]["p95_seconds"] == 1.25
    assert document["summary"]["batch_elapsed_seconds"] == 1.5
    assert document["schema_version"] == 2
    assert document["execution"]["parallelism_scope"] == "root_actions"
    assert document["execution"]["roots_in_flight"] == 1
    assert document["execution"]["latency_scope"] == "decision_wall"
    assert document["execution"]["workers"] == 2
    assert document["search_configuration"]["action_policy_by_agent"] == {
        "mega_starmie": "mega_starmie-v1"}
    assert all(row["statistics"]["elapsed_seconds"] == 0.01 for row in document["results"])
    assert document["summary"]["per_root"][0]["reference_target_stable"] is True
    assert all(row["reference_ready"] for row in document["results"])
    assert all(len(row["reference_target"]["target_id"]) == 64
               for row in document["results"])


def test_roots_run_sequentially_with_deck_policies_and_fresh_engines(tmp_path):
    calls = []

    class RecordingSearcher(_FakeSearcher):
        def search(self, **kwargs):
            calls.append((self.search_configuration.action_policy, kwargs["experiment_seed"],
                          kwargs["engine"]))
            return super().search(**kwargs)

    output = search_timing.run_teacher(
        CORPUS, output=tmp_path / "run.json", workers=2, repetitions=2,
        roots=("dragapult-opening", "starmie-opening"),
        search_configuration=TeacherSearchConfiguration(time_cap_seconds=1),
        root_timeout_seconds=2, searcher_factory=RecordingSearcher)

    assert [(policy, seed) for policy, seed, _engine in calls] == [
        ("all_legal-v1", 60901), ("mega_starmie-v1", 60907)] * 2
    assert len({id(engine) for _policy, _seed, engine in calls}) == 4
    document = json.loads(output.read_text(encoding="utf-8"))
    for row in document["results"]:
        assert row["search_configuration"]["action_policy"] == \
            search_timing.teacher_action_policy_for_agent(row["agent"])


@pytest.mark.parametrize("reason", [TeacherStopReason.WORKER_TIMEOUT, TeacherStopReason.WORKER_ERROR])
def test_failed_decisions_retain_latency_and_do_not_become_reference_targets(tmp_path, reason):
    class FailedSearcher(_FakeSearcher):
        def search(self, **kwargs):
            raise search_timing.TeacherSearchUnavailable(reason, "test failure")

    output = search_timing.run_teacher(
        CORPUS, output=tmp_path / "run.json", workers=2, repetitions=2,
        roots=("starmie-opening",), search_configuration=TeacherSearchConfiguration(),
        root_timeout_seconds=2, searcher_factory=FailedSearcher)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert document["summary"]["complete_searches"] == 0
    for row in document["results"]:
        assert row["worker_status"] == "unavailable"
        assert row["stop_reason"] == reason.value
        assert row["failure"] == "test failure"
        assert row["elapsed_seconds"] > 0
        assert row["reference_target"] is None
        assert row["reference_ready"] is False


def test_real_live_search_preserves_result_with_serial_and_branch_workers(tmp_path):
    targets = []
    for workers in (1, 2):
        output = search_timing.run_teacher(
            CORPUS, output=tmp_path / f"run-{workers}.json", workers=workers, repetitions=1,
            roots=("starmie-search",), search_configuration=TeacherSearchConfiguration(),
            root_timeout_seconds=30)
        row = json.loads(output.read_text(encoding="utf-8"))["results"][0]
        assert row["reference_ready"], row
        targets.append(row["reference_target"])

    assert targets[0] == targets[1]


def test_cli_exposes_worker_repetition_and_teacher_budgets():
    help_text = search_timing._parser().format_help()
    run_help = search_timing._parser()._subparsers._group_actions[0].choices[
        "run"].format_help()

    assert "capture" in help_text and "verify" in help_text and "run" in help_text
    for option in ("--jobs", "--repetitions", "--time-cap", "--root-timeout",
                   "--node-cap", "--chance-branch-cap"):
        assert option in run_help
    assert "branches within one decision" in run_help
