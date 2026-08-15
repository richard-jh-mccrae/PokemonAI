from __future__ import annotations

import pytest

from common.pilot_profile import DEFINITIONS, PilotProfile
from common.runtime import _pilot_overlay


def test_profile_layers_clamp_and_hash_stably():
    first = PilotProfile.resolve(
        global_values={"family.tie_margin": 0.2},
        deck_learned={"family.tie_margin": 0.1},
        authored_deck={"family.tie_margin": -0.05},
    )
    second = PilotProfile.resolve(
        authored_deck={"family.tie_margin": -0.05},
        deck_learned={"family.tie_margin": 0.1},
        global_values={"family.tie_margin": 0.2},
    )

    assert first.get("family.tie_margin") == pytest.approx(0.25)
    assert first.hash == second.hash
    assert len({definition.name for definition in DEFINITIONS}) == len(DEFINITIONS)


def test_profile_rejects_unknown_and_out_of_bounds_global_values():
    with pytest.raises(ValueError, match="unknown"):
        PilotProfile.resolve(authored_deck={"missing.parameter": 1.0})
    with pytest.raises(ValueError, match="out of bounds"):
        PilotProfile.resolve(global_values={"family.tie_margin": 99.0})


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


def test_pilot_overlay_reads_packaged_runtime_config(tmp_path, monkeypatch):
    import common.runtime as runtime_module
    common_dir = tmp_path / "common"
    common_dir.mkdir()
    (tmp_path / "runtime_config.json").write_text(
        '{"pilot":{"strategy.focus_enabled":0}}', encoding="utf-8")
    monkeypatch.setattr(runtime_module, "__file__", str(common_dir / "runtime.py"))
    monkeypatch.delenv("AGENT_OVERLAY", raising=False)
    monkeypatch.delenv("AGENT_STRATEGY_ENABLED", raising=False)
    values, provenance = runtime_module._pilot_overlay()
    assert values == {"strategy.focus_enabled": 0.0}
    assert provenance.endswith("runtime_config.json")


def test_offline_clock_accepts_an_exhaustive_budget():
    assert PilotProfile.resolve(
        global_values={"clock.remaining_200_seconds": 600}
    ).get("clock.remaining_200_seconds") == 600
