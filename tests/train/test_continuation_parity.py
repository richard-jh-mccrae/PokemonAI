"""Seeded continuation provenance — explicit trace bindings, never positional guesses."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from cgpy.verify.trace import Trace


def _frame(n: int, *, choice=None) -> dict:
    return {
        "obs": {
            "select": {"type": 1, "context": 7, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 3, "area": 1, "index": n}]},
            "current": {"yourIndex": 0, "turn": n,
                        "players": [{"deckCount": 10 - n, "prize": [None]},
                                    {"deckCount": 10, "prize": [None]}]},
        },
        "choice": choice,
        "god": None,
    }


def _trace(tmp_path: Path, frames: list[dict]) -> Path:
    path = tmp_path / "native.trace.json.gz"
    Trace(meta={"engine_sha": "native", "decks": [[1] * 60, [2] * 60], "policy": "test",
                "result": {"winner": -1, "steps": len(frames)}}, frames=frames).save(path)
    return path


def _record(trace: Path, frames: list[dict], *, source=0, successor=1) -> dict:
    from train.continuation_parity import (frame_digest, observation_digest, replay_digest,
                                           trace_digest)

    observed = frames[source]["obs"]
    seed_observation = {**observed, "search_begin_input": "native-token"}
    replay = {"schema": "native-select-replay/1",
              "steps": [{"observation": seed_observation, "choice": frames[source]["choice"]}]}
    replay_path = trace.with_suffix(".replay.json")
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    return {
        "id": "to-hand",
        "context": 7,
        "provenance": {
            "trace": trace.name,
            "trace_sha256": trace_digest(trace),
            "frame_sha256": frame_digest(frames[source]),
            "successor_sha256": frame_digest(frames[successor]),
        },
        "replay": {"path": replay_path.name, "sha256": replay_digest(replay_path), "step": 0,
                   "observation_sha256": observation_digest(seed_observation)},
        "seed_observation": seed_observation,
        "selected": frames[source]["choice"],
        "writes": ["select", "current"],
    }


def test_seeded_continuation_binds_by_content_not_frame_ordinal(tmp_path):
    from train.continuation_parity import bind_record

    frames = [_frame(1, choice=[0]), _frame(2, choice=[0]), _frame(3, choice=None)]
    trace = _trace(tmp_path, frames)
    bound = bind_record(_record(trace, frames), trace_root=tmp_path)
    assert bound.reason is None
    assert bound.frame == frames[0]
    assert bound.successor == frames[1]


def test_seeded_continuation_refuses_missing_duplicate_stale_reordered_and_mismatched_provenance(tmp_path):
    from train.continuation_parity import bind_record, replay_digest

    frames = [_frame(1, choice=[0]), _frame(2, choice=[0]), _frame(3, choice=None)]
    trace = _trace(tmp_path, frames)
    record = _record(trace, frames)

    assert bind_record({**record, "replay": {**record["replay"], "path": "gone.json"}},
                       trace_root=tmp_path).reason == "missing-replay"
    assert bind_record({**record, "replay": {**record["replay"], "sha256": "stale"}},
                       trace_root=tmp_path).reason == "stale-replay"
    assert bind_record({**record, "replay": {**record["replay"], "step": 1}},
                       trace_root=tmp_path).reason == "missing-replay-step"
    assert bind_record({**record, "replay": {**record["replay"], "observation_sha256": "stale"}},
                       trace_root=tmp_path).reason == "mismatched-replay-observation"

    replay_path = tmp_path / record["replay"]["path"]
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    neighbour = copy.deepcopy(record["seed_observation"])
    neighbour["current"]["turn"] += 1
    replay["steps"].insert(0, {"observation": neighbour, "choice": record["selected"]})
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    reordered_replay = {**record, "replay": {**record["replay"], "sha256": replay_digest(replay_path)}}
    assert bind_record(reordered_replay, trace_root=tmp_path).reason == "mismatched-replay-observation"

    _record(trace, frames)
    assert bind_record({**record, "provenance": {**record["provenance"], "trace": "gone.gz"}},
                       trace_root=tmp_path).reason == "missing-trace"
    assert bind_record({**record, "provenance": {**record["provenance"], "trace_sha256": "stale"}},
                       trace_root=tmp_path).reason == "stale-trace"

    wrong_seed = {**record, "seed_observation": {**record["seed_observation"],
                                                    "current": {"yourIndex": 1}}}
    assert bind_record(wrong_seed, trace_root=tmp_path).reason == "seed-observation-mismatch"

    reordered = [_frame(1, choice=[0]), _frame(3, choice=None), _frame(2, choice=[0])]
    reordered_trace = _trace(tmp_path, reordered)
    reordered_record = _record(reordered_trace, reordered, source=0, successor=2)
    assert bind_record(reordered_record, trace_root=tmp_path).reason == "reordered-successor"

    duplicate = [_frame(1, choice=[0]), _frame(2, choice=[0]), _frame(1, choice=[0])]
    duplicate_trace = _trace(tmp_path, duplicate)
    duplicate_record = _record(duplicate_trace, duplicate)
    assert bind_record(duplicate_record, trace_root=tmp_path).reason == "duplicate-frame"


def test_committed_seed_pairs_cover_the_nine_contexts_and_bind_exactly():
    from train.continuation_parity import FIXTURES, bind_record, load_records, sweep

    records = load_records()
    assert {record["context"] for record in records} == {1, 2, 3, 4, 7, 15, 17, 21, 22}
    assert all(record["seed_observation"].get("search_begin_input") for record in records)
    assert all(bind_record(record, trace_root=FIXTURES).reason is None for record in records)

    report = sweep(records, trace_root=FIXTURES)
    assert report.population == report.seeded == {context: 1 for context in range(23)
                                                   if context in {1, 2, 3, 4, 7, 15, 17, 21, 22}}
    assert not report.refused and not report.verified and not report.backends


def test_native_seeded_successors_match_only_declared_observables_and_clean_up():
    from cg import api as native
    from train.continuation_parity import FIXTURES, bind_record, load_records, verify_record

    records = {record["context"]: record for record in load_records()}
    supported = {1, 3, 4, 7, 15, 17, 21, 22}
    for context in supported:
        binding = bind_record(records[context], trace_root=FIXTURES)
        assert verify_record(binding, search_api=native, backend="native").reason is None
        assert verify_record(binding, search_api=native, backend="native").reason is None

    setup_bench = bind_record(records[2], trace_root=FIXTURES)
    assert setup_bench.replay and verify_record(setup_bench, search_api=native,
                                                backend="native").reason == "engine-refused"


def test_cgpy_token_equivalent_heal_successor_is_engine_backed():
    from cgpy import alias
    from train.continuation_parity import FIXTURES, bind_record, load_records, verify_record

    record = next(record for record in load_records() if record["context"] == 17)
    alias.install()
    try:
        from cg import api as cgpy
        binding = bind_record(record, trace_root=FIXTURES)
        assert verify_record(binding, search_api=cgpy, backend="cgpy", token="cgpy").reason is None
    finally:
        alias.uninstall()
