from __future__ import annotations

import pytest

from deprecated.bellman.pilot_profile import DEFINITIONS, PilotProfile
from deprecated.bellman.runtime import _pilot_overlay
from deprecated.bellman.budget_prototype import DecisionClock


def test_authored_deck_value_overwrites_global_and_learned_layers():
    first = PilotProfile.resolve(
        global_values={"family.tie_margin": 0.2},
        deck_learned={"family.tie_margin": 0.1},
        authored_deck_overrides={"family.tie_margin": 0.05},
    )
    second = PilotProfile.resolve(
        authored_deck_overrides={"family.tie_margin": 0.05},
        deck_learned={"family.tie_margin": 0.1},
        global_values={"family.tie_margin": 0.2},
    )

    assert first.get("family.tie_margin") == pytest.approx(0.05)
    assert first.hash == second.hash
    assert len({definition.name for definition in DEFINITIONS}) == len(DEFINITIONS)


def test_profile_rejects_unknown_and_out_of_bounds_global_values():
    with pytest.raises(ValueError, match="unknown"):
        PilotProfile.resolve(authored_deck_overrides={"missing.parameter": 1.0})
    with pytest.raises(ValueError, match="out of bounds"):
        PilotProfile.resolve(global_values={"family.tie_margin": 99.0})
    with pytest.raises(ValueError, match="authored override"):
        PilotProfile.resolve(authored_deck_overrides={"family.tie_margin": 99.0})


def test_all_value_equations_default_to_disconnected():
    profile = PilotProfile.resolve()

    for family in ("attachment", "deployment", "evolution", "promote_retreat", "snipe"):
        assert profile.get(f"family.{family}_shadow") == 0.0
        assert profile.get(f"family.{family}_ordering") == 0.0
        assert profile.get(f"family.{family}_widening") == 0.0


@pytest.mark.parametrize(("remaining", "expected"), [
    (600, 30), (200, 15), (140, 10), (0, 2), (170, 12.5), (400, 22.5),
])
def test_clock_profile_anchors_and_interpolation(remaining, expected):
    assert PilotProfile.resolve().planning_seconds(remaining) == pytest.approx(expected)


def test_pilot_overlay_reads_experiment_values(tmp_path, monkeypatch):
    path = tmp_path / "exhaustive.json"
    path.write_text('{"pilot":{"search.max_nodes":100000}}', encoding="utf-8")
    monkeypatch.setenv("AGENT_OVERLAY", str(path))

    values, provenance = _pilot_overlay()

    assert values == {"search.max_nodes": 100000.0}
    assert provenance == str(path.resolve())


def test_offline_clock_accepts_an_exhaustive_budget():
    assert PilotProfile.resolve(
        global_values={"clock.remaining_200_seconds": 600}
    ).get("clock.remaining_200_seconds") == 600


def test_completed_candidate_harvest_defaults_are_central_and_tunable():
    definitions = {row.name: row for row in DEFINITIONS}
    profile = PilotProfile.resolve(global_values={
        "search.completed_candidate_target": 5,
        "search.completed_candidate_time_share": 0.35,
    })

    assert definitions["search.completed_candidate_target"].default == 2.0
    assert definitions["search.completed_candidate_time_share"].default == 0.20
    assert profile.get("search.completed_candidate_target") == 5
    assert profile.get("search.completed_candidate_time_share") == pytest.approx(0.35)


def test_anytime_allocation_defaults_are_central_and_bounded():
    profile = PilotProfile.resolve()

    assert profile.get("search.protected_bundle_time_share") == pytest.approx(0.50)
    assert profile.get("search.challenger_time_share") == pytest.approx(0.10)
    assert profile.get("search.challenger_count") == 2
    assert profile.get("search.protected_bundle_count") == 2
    assert profile.get("search.stability_patience_share") == pytest.approx(0.20)
    assert profile.get("search.stability_patience_max_seconds") == pytest.approx(10.0)


def test_sequence_coverage_ships_on_with_a_kill_switch():
    definitions = {row.name: row for row in DEFINITIONS}

    assert definitions["strategy.sequence_coverage_enabled"].default == 1.0
    assert not definitions["strategy.sequence_coverage_enabled"].learnable
    off = PilotProfile.resolve(global_values={"strategy.sequence_coverage_enabled": 0.0})
    assert off.get("strategy.sequence_coverage_enabled") == 0.0


def test_information_partition_ships_on_with_a_kill_switch():
    definitions = {row.name: row for row in DEFINITIONS}

    assert definitions["strategy.information_partition_enabled"].default == 1.0
    assert not definitions["strategy.information_partition_enabled"].learnable
    off = PilotProfile.resolve(global_values={
        "strategy.information_partition_enabled": 0.0})
    assert off.get("strategy.information_partition_enabled") == 0.0


@pytest.mark.parametrize(("external", "tail", "bellman"), [
    (120.0, 5.0, 115.0),
    (15.0, 1.0, 14.0),
    (200.0, 5.0, 195.0),
])
def test_decision_clock_reserves_a_bounded_fallback_tail(external, tail, bellman):
    clock = DecisionClock(external)

    assert clock.fallback_tail_seconds == pytest.approx(tail)
    assert clock.bellman_seconds == pytest.approx(bellman)
