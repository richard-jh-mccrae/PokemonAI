import json
import pytest

from train import search_timing, search_timing_report


def _run_document():
    return {
        "schema": "search-timing-run",
        "schema_version": 1,
        "run_id": "a" * 64,
        "title": "PUCT <baseline>",
        "generated_at": "2026-09-06T12:34:56+02:00",
        "timezone": "Europe/Oslo",
        "source": {"branch": "codex/bench", "commit": "b" * 40, "dirty": True},
        "suite": {"name": "core9", "roots": 1},
        "configuration": {"repetitions": 3, "artifacts": ["timing", "tree"]},
        "cards": {"119": "Dreepy"},
        "results": [{
            "root_id": "dragapult-opening",
            "agent": "dragapult_ex",
            "frame_class": "opening",
            "method": "puct_uniform",
            "backend": "native-cg",
            "semantic_gate": "comparable",
            "decision_gate": "matching",
            "timing": {
                "median_seconds": 0.125,
                "p95_seconds": 0.15,
                "first_seconds": 0.15,
                "repeat_median_seconds": 0.1,
                "simulations_per_second": 32.0,
            },
            "metrics": {
                "simulations": 4,
                "work": {"transitions": 3, "evaluations": 4, "chances": 0},
                "timing": {"prior_seconds": 0.01, "search_seconds": 0.1,
                           "overhead_seconds": 0.015},
                "transport": {"request_bytes": 80, "response_bytes": 120},
                "tree_nodes": 2,
                "cache_entries": 7,
                "stop_reason": "simulation_limit",
            },
            "profile": None,
            "tree": {
                "root_node_id": 0,
                "nodes": [{
                    "node_id": 0, "state_key": "0" * 64, "decision_key": "root",
                    "observation": json.dumps({"schema_version": 1, "payload": {}}),
                    "kind": "player_decision", "actor_seat": 0,
                    "boundary_reason": None, "depth": 0, "visits": 4,
                    "outgoing_visits": 4, "selections": 0,
                    "valuation": {"total": 1.5, "status": "complete",
                                                    "components": [], "gaps": []},
                }],
                "edges": [],
                "schema_version": 2,
            },
            "tree_evidence": {"timing_gate": "matching", "metrics": {}},
        }],
    }


def test_html_report_is_a_deterministic_view_of_the_json(tmp_path):
    document = _run_document()

    first = search_timing_report.render_report(document)
    second = search_timing_report.render_report(json.loads(json.dumps(document)))
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(document), encoding="utf-8")
    output = search_timing_report.write_report(run_path)

    assert first == second == output.read_text(encoding="utf-8")
    assert "PUCT &lt;baseline&gt;" in first
    assert "2026-09-06T12:34:56+02:00" in first
    assert "codex/bench" in first and ("b" * 40) in first
    assert "dragapult-opening" in first
    assert "Tree traversal" in first
    assert "const RUN =" in first
    assert ".join('\\n       ')" in first


def test_html_report_rejects_unknown_json_schema():
    with pytest.raises(ValueError, match="unsupported Search Timing Run schema"):
        search_timing_report.render_report({"schema": "teacher-timing", "schema_version": 1})


def test_timing_summary_never_prices_failed_attempts_as_fast_searches():
    summary = search_timing._timing([
        {"elapsed_seconds": 0.01, "failure": {"type": "Boom"}, "metrics": None},
        {"elapsed_seconds": 2.0, "failure": None,
         "metrics": {"simulations": 10}},
    ])

    assert summary["attempts"] == 2
    assert summary["completed"] == 1
    assert summary["failed"] == 1
    assert summary["median_seconds"] == 2.0
    assert summary["simulations_per_second"] == 5.0


def test_backend_timing_is_not_comparable_when_search_values_diverge():
    results = [{
        "root_id": "root", "method": "puct_uniform", "backend": backend,
        "samples": [{"decision_signature_id": "same", "signature_id": value}],
    } for backend, value in (("native-cg", "native-value"), ("cgpy", "cgpy-value"))]

    search_timing._semantic_gates(results)

    assert all(row["decision_gate"] == "matching" for row in results)
    assert all(row["value_gate"] == "diverged" for row in results)
    assert all(row["semantic_gate"] == "not_comparable" for row in results)


def test_diagnostic_passes_are_linked_to_their_timing_decision():
    timing = [{"failure": None, "signature_id": "value-a",
               "decision_signature_id": "decision-a"}]

    assert search_timing._artifact_timing_gate({
        "failure": None, "signature_id": "value-a",
        "decision_signature_id": "decision-a"}, timing) == "matching"
    assert search_timing._artifact_timing_gate({
        "failure": None, "signature_id": "value-b",
        "decision_signature_id": "decision-a"}, timing) == "value_diverged"
    assert search_timing._artifact_timing_gate({
        "failure": None, "signature_id": "value-b",
        "decision_signature_id": "decision-b"}, timing) == "diverged"


def test_runtime_uses_the_recorded_episode_deck_for_both_backends(monkeypatch):
    captured = []
    sentinel = object()

    def build(_strategy, cards, **_kwargs):
        captured.append(tuple(cards))
        return sentinel

    monkeypatch.setattr(search_timing, "build_runtime", build)

    result = search_timing._agent_runtime(
        "dragapult_ex", (9, 8, 7), "ledger_one_ply", "native-cg",
        search_timing.BenchmarkConfiguration())

    assert result is sentinel
    assert captured == [(9, 8, 7)]


def test_cli_has_one_entry_point_for_run_and_render():
    parser = search_timing.build_parser()
    help_text = parser.format_help()
    run_help = parser._subparsers._group_actions[0].choices["run"].format_help()

    assert "run" in help_text and "render" in help_text
    for option in ("--suite", "--methods", "--backends", "--artifacts",
                   "--artifact-root", "--repetitions", "--simulations",
                   "--workers", "--batch-size"):
        assert option in run_help


def test_core9_has_three_declared_roots_per_deck():
    specs = search_timing.root_specs("core9")

    assert len(specs) == 9
    assert {spec.agent for spec in specs} == {
        "dragapult_ex", "mega_lucario", "mega_starmie"}
    assert {(spec.agent, spec.frame_class) for spec in specs} == {
        (agent, frame_class)
        for agent in ("dragapult_ex", "mega_lucario", "mega_starmie")
        for frame_class in ("opening", "search", "tactical")}
    assert len({spec.root_id for spec in specs}) == 9
    assert all("game" not in spec.description.lower() for spec in specs)


def test_core9_roots_resolve_to_committed_native_main_observations():
    cache = {}
    sources = {}
    for spec in search_timing.root_specs("core9"):
        if spec.replay_path not in cache:
            cache[spec.replay_path] = search_timing.load_saved_episode(spec.replay_path)
        raw, source = search_timing._root_observation(spec, cache[spec.replay_path])
        assert raw["search_begin_input"]
        assert raw["select"]["context"] == 0
        assert len(raw["select"]["option"]) > 1
        sources[spec.agent] = source

    assert sources["dragapult_ex"]["deck_overlap_cards"] == 59
    assert sources["dragapult_ex"]["deck_matches_current"] is False
    assert sources["mega_lucario"]["deck_matches_current"] is True
    assert sources["mega_starmie"]["deck_matches_current"] is True


def test_run_command_compares_ledger_backends_profiles_and_writes_both_views(tmp_path):
    assert search_timing.main([
        "run", "--root", "dragapult-opening",
        "--methods", "ledger_one_ply", "--backends", "native-cg,cgpy",
        "--artifacts", "timing,profile", "--repetitions", "1",
        "--title", "One-root integration", "--out", str(tmp_path),
    ]) == 0

    run_paths = list(tmp_path.glob("*/run.json"))
    assert len(run_paths) == 1
    document = json.loads(run_paths[0].read_text(encoding="utf-8"))
    assert document["title"] == "One-root integration"
    assert document["suite"] == {"name": "core9", "roots": 1}
    assert document["source"]["commit"]
    root_source = document["results"][0]["root_source"]
    assert root_source["replay"].endswith("episode-85046764-replay.json.gz")
    assert len(root_source["replay_sha256"]) == 64
    assert len(root_source["observation_sha256"]) == 64
    assert root_source["observation_bytes"] > 0
    assert root_source["deck_overlap_cards"] == 59
    assert root_source["runtime_deck"] == "recorded_episode"
    assert {row["backend"] for row in document["results"]} == {"native-cg", "cgpy"}
    for row in document["results"]:
        assert row["method"] == "ledger_one_ply"
        assert row["timing"]["median_seconds"] > 0
        expected = ("comparable" if row["decision_gate"] == row["value_gate"] == "matching"
                    else "not_comparable")
        assert row["semantic_gate"] == expected
        profile = row["profile"]
        assert profile["timing_gate"] in {"matching", "value_diverged", "diverged"}
        assert profile["parent"]["top_functions"]
        assert (run_paths[0].parent / profile["parent"]["pstats"]).is_file()
        assert profile["memory"]["peak_bytes"] > 0
        assert profile["memory"]["top_allocations"]
    assert run_paths[0].with_name("report.html").is_file()


def test_run_command_compares_both_puct_backends_and_captures_safe_trees(tmp_path):
    assert search_timing.main([
        "run", "--root", "dragapult-opening",
        "--methods", "puct_uniform", "--backends", "native-cg,cgpy",
        "--artifacts", "timing,profile,tree", "--repetitions", "1",
        "--simulations", "2", "--time-limit", "20",
        "--title", "PUCT parity integration", "--out", str(tmp_path),
    ]) == 0

    run_path = next(tmp_path.glob("*/run.json"))
    document = json.loads(run_path.read_text(encoding="utf-8"))
    assert {row["backend"] for row in document["results"]} == {"native-cg", "cgpy"}
    for row in document["results"]:
        expected = ("comparable" if row["decision_gate"] == row["value_gate"] == "matching"
                    else "not_comparable")
        assert row["semantic_gate"] == expected
        assert row["metrics"]["simulations"] == 2
        assert row["metrics"]["transport"]["request_bytes"] > 0
        assert row["profile"]["workers"]["top_functions"]
        assert all((run_path.parent / path).is_file()
                   for path in row["profile"]["workers"]["pstats"])
        assert row["tree"]["nodes"]
        assert row["tree_evidence"]["metrics"]["simulations"] == 2
        assert row["tree_evidence"]["timing_gate"] in {
            "matching", "value_diverged", "diverged"}
        encoded = json.dumps(row["tree"])
        assert "search_begin_input" not in encoded
        assert "provider_input" not in encoded


def test_timing_passes_finish_before_profile_and_tree_passes(monkeypatch, tmp_path):
    calls = []
    spec = search_timing.root_specs()[0]
    prepared = [(spec, {}, (1,), {})]
    config = search_timing.BenchmarkConfiguration(
        methods=("ledger_one_ply", "puct_uniform"),
        backends=("native-cg", "cgpy"), artifacts=("timing", "profile", "tree"),
        repetitions=1)

    def timed(_spec, _raw, _cards, method, backend, _config):
        calls.append(("timing", method, backend))
        return {"elapsed_seconds": 1.0, "failure": None, "signature_id": "same",
                "decision_signature_id": "same", "metrics": {"simulations": 1}}

    def profiled(_spec, _raw, _cards, method, backend, _config, *_paths):
        calls.append(("profile", method, backend))
        return {"failure": None, "signature_id": "same",
                "decision_signature_id": "same"}

    def treed(_spec, _raw, _cards, method, backend, _config):
        calls.append(("tree", method, backend))
        return {"tree": {"nodes": [], "edges": []}, "failure": None,
                "signature_id": "same", "decision_signature_id": "same",
                "metrics": {}}

    monkeypatch.setattr(search_timing, "_timed_sample", timed)
    monkeypatch.setattr(search_timing, "_profile_sample", profiled)
    monkeypatch.setattr(search_timing, "_tree_sample", treed)

    search_timing._collect_results(config, prepared, tmp_path)

    assert [kind for kind, _method, _backend in calls[:4]] == ["timing"] * 4
    assert calls[:4] == [
        ("timing", "ledger_one_ply", "native-cg"),
        ("timing", "ledger_one_ply", "cgpy"),
        ("timing", "puct_uniform", "cgpy"),
        ("timing", "puct_uniform", "native-cg"),
    ]
    assert all(kind == "profile" for kind, _method, _backend in calls[4:8])
    assert all(kind == "tree" for kind, _method, _backend in calls[8:])


def test_backend_repetitions_are_counterbalanced_and_order_is_recorded(monkeypatch, tmp_path):
    calls = []
    spec = search_timing.root_specs()[0]
    config = search_timing.BenchmarkConfiguration(
        methods=("ledger_one_ply",), backends=("native-cg", "cgpy"),
        artifacts=("timing",), repetitions=2)

    def timed(_spec, _raw, _cards, _method, backend, _config):
        calls.append(backend)
        return {"elapsed_seconds": 1.0, "failure": None, "signature_id": "same",
                "decision_signature_id": "same", "metrics": {"simulations": 1}}

    monkeypatch.setattr(search_timing, "_timed_sample", timed)

    results, _elapsed = search_timing._collect_results(
        config, [(spec, {}, (1,), {})], tmp_path)

    assert calls == ["native-cg", "cgpy", "cgpy", "native-cg"]
    native = next(row for row in results if row["backend"] == "native-cg")
    cgpy = next(row for row in results if row["backend"] == "cgpy")
    assert [(sample["repetition"], sample["execution_order"])
            for sample in native["samples"]] == [(0, 0), (1, 3)]
    assert [(sample["repetition"], sample["execution_order"])
            for sample in cgpy["samples"]] == [(0, 1), (1, 2)]


def test_atomic_publication_retries_a_transient_windows_file_lock(monkeypatch, tmp_path):
    stage = tmp_path / "stage"
    target = tmp_path / "target"
    stage.mkdir()
    original = type(stage).rename
    attempts = []

    def flaky(path, destination):
        attempts.append(destination)
        if len(attempts) == 1:
            raise PermissionError("transient scanner lock")
        return original(path, destination)

    monkeypatch.setattr(type(stage), "rename", flaky)
    monkeypatch.setattr(search_timing, "sleep", lambda _seconds: None)

    search_timing._publish_stage(stage, target)

    assert target.is_dir()
    assert len(attempts) == 2
