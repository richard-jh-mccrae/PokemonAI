import json
import math
import os
from pathlib import Path
from statistics import median
from time import perf_counter, perf_counter_ns

import pytest

from cgpy.schema import SelectContext
from common.decision import (ComputeConfiguration, SearchConfiguration,
                             correction_compute_profile)
from common.observation import ObservationStateBuilder
from real_engine_helpers import BodySpec, deck, run_ultra_ball_chain, runtime


RUNS = int(os.environ.get("ULTRA_BALL_BENCH_RUNS", "3"))
FRAME_RUNS = int(os.environ.get("DECISION_FRAME_BENCH_RUNS", "1"))
BENCHMARK_COMPUTE = ComputeConfiguration(search=SearchConfiguration(time_budget_ms=10_000))
BASELINE = json.loads((
    Path(__file__).resolve().parents[2]
    / "data" / "benchmarks" / "ultra_ball_chain_20260827_baseline.json"
).read_text(encoding="utf-8"))
FRAME_BASELINE = json.loads((
    Path(__file__).resolve().parents[2]
    / "data" / "benchmarks" / "decision_frame_20260830_baseline.json"
).read_text(encoding="utf-8"))
EXPECTED_BEHAVIOR = {
    "dragapult_ex": {
        "choices": ((0,), (0, 2), (6,)),
        "discarded_card_ids": (2, 5),
        "fetched_card_id": 120,
    },
    "mega_lucario": {
        "choices": ((0,), (0, 2), (10,)),
        "discarded_card_ids": (6, 674),
        "fetched_card_id": 678,
    },
    "mega_starmie": {
        "choices": ((0,), (0, 2), (5,)),
        "discarded_card_ids": (17, 666),
        "fetched_card_id": 1031,
    },
}
EXPECTED_STRESS_CHOICE = (21,)

CASES = (
    pytest.param(
        "dragapult_ex",
        {
            "me_active": BodySpec((119,)),
            "me_hand": (1121, 2, 5, 121),
            "me_top": (120, 121),
            "them_active": BodySpec((119, 120, 121), energies=(2, 5)),
        },
        id="dragapult-ex",
    ),
    pytest.param(
        "mega_lucario",
        {
            "me_active": BodySpec((677,)),
            "me_hand": (1121, 6, 6, 674),
            "me_top": (678,),
            "them_active": BodySpec((677, 678), energies=(6, 6)),
        },
        id="mega-lucario",
    ),
    pytest.param(
        "mega_starmie",
        {
            "me_active": BodySpec((1030,)),
            "me_hand": (1121, 3, 17, 666),
            "me_top": (1031,),
            "them_active": BodySpec((1030, 1031), energies=(3, 17)),
        },
        id="mega-starmie",
    ),
)


def _board_chain(cards, observations):
    builder = ObservationStateBuilder(cards)
    phases = []
    started = perf_counter_ns()

    phase_started = perf_counter_ns()
    state = builder.root(observations[0])
    phases.append(perf_counter_ns() - phase_started)
    keys = [state.decision_key]
    for current in observations[1:]:
        phase_started = perf_counter_ns()
        state, _delta = builder.advance(state, current)
        phases.append(perf_counter_ns() - phase_started)
        keys.append(state.decision_key)

    return perf_counter_ns() - started, tuple(phases), tuple(keys)


def _milliseconds(values):
    return [value / 1_000_000 for value in values]


def _p95(values):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


@pytest.mark.parametrize(
    ("agent", "scenario_kwargs"),
    CASES,
)
def test_ultra_ball_match_chain_is_exact_repeatable_and_timed(
        agent, scenario_kwargs):
    expected = BASELINE["results"][agent]
    behavior = EXPECTED_BEHAVIOR.get(agent, expected)
    expected_choices = tuple(tuple(choice) for choice in behavior["choices"])
    expected_discards = tuple(behavior["discarded_card_ids"])
    expected_fetch = int(behavior["fetched_card_id"])
    results = tuple(run_ultra_ball_chain(
        agent, compute_configuration=BENCHMARK_COMPUTE, **scenario_kwargs)
        for _ in range(RUNS))

    for result in results:
        assert result.choices[0] == expected_choices[0]
        assert result.choices[-1] == expected_choices[-1]
        assert result.contexts == (
            int(SelectContext.MAIN), int(SelectContext.DISCARD), int(SelectContext.TO_HAND))
        assert result.complete == (True, True, True)
        assert result.stop_reasons == (
            "complete", "cached_continuation", "cached_continuation")
        assert result.played_card_id == 1121
        assert result.discarded_card_ids == expected_discards
        assert result.fetched_card_id == expected_fetch
        assert result.total_ns > 0
        assert len(result.decision_ns) == 3
    expected_observations = results[0].observations
    assert all(result.choices == results[0].choices for result in results)
    assert all(result.observations == expected_observations for result in results)

    board_runs = tuple(_board_chain(deck(agent), result.observations) for result in results)
    expected_keys = board_runs[0][2]
    assert all(keys == expected_keys for _total, _phases, keys in board_runs)

    totals = _milliseconds([result.total_ns for result in results])
    decisions = tuple(
        _milliseconds([result.decision_ns[index] for result in results])
        for index in range(3))
    board_totals = _milliseconds([total for total, _phases, _keys in board_runs])
    board_phases = tuple(
        _milliseconds([phases[index] for _total, phases, _keys in board_runs])
        for index in range(3))
    system_median = median(totals)
    board_median = median(board_totals)
    print("ULTRA_BALL_BENCH " + json.dumps({
        "agent": agent,
        "runs": RUNS,
        "choices": expected_choices,
        "discarded_card_ids": expected_discards,
        "fetched_card_id": expected_fetch,
        "system_total_ms": {"median": system_median, "p95": _p95(totals)},
        "system_median_change_percent": 100 * (
            system_median / expected["system_total_ms"]["median"] - 1),
        "decision_ms_median": [median(values) for values in decisions],
        "board_chain_ms": {"median": board_median, "p95": _p95(board_totals)},
        "board_median_change_percent": 100 * (
            board_median / expected["board_chain_ms"]["median"] - 1),
        "board_phase_ms_median": [median(values) for values in board_phases],
    }, sort_keys=True))


def test_dragapult_portfolio_stress_frame_is_exact_and_timed():
    expected = FRAME_BASELINE["results"]["8109263769592355-117"]
    observation = json.loads((
        Path(__file__).resolve().parents[1]
        / "fixtures" / expected["fixture"]
    ).read_text(encoding="utf-8"))["obs"]
    elapsed_ms = []
    work = []

    for _run in range(FRAME_RUNS):
        agent_runtime = runtime(
            expected["agent"], deck(expected["agent"]),
            provider_factory=None,
            compute_configuration=correction_compute_profile(),
            decision_containment_seconds=expected["maximum_ms"] / 1_000)
        started = perf_counter()
        decision = agent_runtime.decide(observation)
        elapsed_ms.append((perf_counter() - started) * 1_000)

        assert tuple(decision.chosen) == EXPECTED_STRESS_CHOICE
        assert decision.complete is True
        assert decision.diagnostics["search"]["stop_reason"] == "complete"
        search = decision.diagnostics["search"]
        memo = search["portfolio_memo"]
        assert memo["lookups"] == memo["hits"] + memo["misses"]
        assert memo["hits"] > 0
        work.append({
            "nodes_visited": search["nodes_visited"],
            "portfolio_solves": memo["misses"],
            "portfolio_memo_hits": memo["hits"],
        })

    current_median = median(elapsed_ms)
    assert current_median < expected["maximum_ms"]
    print("DECISION_FRAME_BENCH " + json.dumps({
        "frame": "8109263769592355-117",
        "runs": FRAME_RUNS,
        "choice": EXPECTED_STRESS_CHOICE,
        "decision_total_ms": {
            "median": current_median,
            "p95": _p95(elapsed_ms),
        },
        "work": work,
        "median_change_percent": 100 * (
            current_median / expected["decision_total_ms"]["median"] - 1),
    }, sort_keys=True))
