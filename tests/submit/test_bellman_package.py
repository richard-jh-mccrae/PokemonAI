from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from submit.brief import build_manifest, render_brief, render_brief_csv
from submit.history import summary
from submit.package import package


REPO = Path(__file__).resolve().parents[2]
SHIPPABLE_AGENTS = ("dragapult_ex", "mega_lucario", "mega_starmie")


def test_manifest_describes_declarations_and_bellman_only():
    manifest = build_manifest(REPO / "src" / "agents" / "mega_starmie",
                              git_hash="abc123", cards={})
    assert manifest["system"] == "bellman"
    assert manifest["strategy"]["roles"]["1031"] == ["win_condition", "primary_attacker"]
    assert manifest["strategy"]["prize_plan"]["prizes_to_win"] == 6
    assert summary(manifest)["system"] == "bellman"
    assert manifest["pilot_profile"]["hash"]
    assert "planning_clock" in manifest["pilot_profile"]["groups"]
    needs = manifest["needs_strategy"]
    assert needs["resolved"]["content_hash"]
    assert needs["enabled"] is True
    assert needs["odds_enabled"] is True
    assert needs["resolved"]["effective"]
    assert any(row["identifier"] == "mega_starmie.evolve_benched_staryu"
               for row in needs["resolved"]["deck"])


def test_brief_projects_the_same_profile_to_html_and_csv():
    manifest = build_manifest(REPO / "src" / "agents" / "mega_starmie",
                              git_hash="abc123", cards={})
    html = render_brief(manifest)
    csv_text = render_brief_csv(manifest)

    assert "<details><summary>planning_clock" in html
    assert manifest["pilot_profile"]["hash"] in html
    assert "pilot_parameter" in csv_text
    assert "clock.remaining_600_seconds" in csv_text
    assert "family.snipe_shadow" in csv_text
    assert "promote_retreat.resource_cost_weight" in csv_text
    assert "Needs strategy beam" in html
    assert manifest["needs_strategy"]["resolved"]["content_hash"] in html
    assert "own.active" in html


def test_needs_off_manifest_keeps_odds_and_the_same_resolved_strategy_catalog():
    enabled = build_manifest(REPO / "src" / "agents" / "mega_starmie",
                             git_hash="abc123", cards={})
    disabled = build_manifest(
        REPO / "src" / "agents" / "mega_starmie",
        git_hash="abc123", cards={},
        pilot_values={"needs.focus_enabled": 0.0},
    )

    assert enabled["needs_strategy"]["enabled"] is True
    assert disabled["needs_strategy"]["enabled"] is False
    assert disabled["needs_strategy"]["odds_enabled"] is True
    assert (enabled["needs_strategy"]["resolved"]["content_hash"]
            == disabled["needs_strategy"]["resolved"]["content_hash"])


def test_package_contains_shared_bellman_and_no_legacy_policy(tmp_path):
    archive = package("mega_starmie", tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "common/runtime.py" in names
        assert "common/planner.py" in names
        assert "common/native_engine.py" in names
        assert "common/needs.py" in names
        assert "common/refresh.py" in names
        assert "common/value_equations.py" in names
        assert "common/engine.py" not in names
        assert any(name.startswith("cg/") for name in names)
        assert not any(name.startswith("common/bellman/") for name in names)
        assert "brief.html" in names and "brief.csv" in names
        assert "common/pilot.py" not in names
        assert "common/state_value.py" not in names
        assert "tuned.json" not in names
        manifest_text = bundle.read("brief.html").decode("utf-8")
        assert '"system": "bellman"' in manifest_text


def test_package_bakes_needs_toggle_into_runtime_config(tmp_path):
    archive = package("mega_starmie", tmp_path, stamp=False, needs_enabled=False)
    with zipfile.ZipFile(archive) as bundle:
        config = json.loads(bundle.read("runtime_config.json"))
    assert config == {"pilot": {"needs.focus_enabled": 0.0}}


@pytest.mark.parametrize("agent_name", SHIPPABLE_AGENTS)
def test_every_kaggle_bundle_contains_no_cgpy_name_or_content(tmp_path, agent_name):
    archive = package(agent_name, tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            assert "cgpy" not in name.lower(), name
            assert b"cgpy" not in bundle.read(name).lower(), name
