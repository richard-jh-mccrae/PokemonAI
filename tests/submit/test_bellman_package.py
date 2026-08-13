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


def test_brief_projects_the_same_profile_to_html_and_csv():
    manifest = build_manifest(REPO / "src" / "agents" / "mega_starmie",
                              git_hash="abc123", cards={})
    html = render_brief(manifest)
    csv_text = render_brief_csv(manifest)

    assert "<details><summary>planning_clock" in html
    assert manifest["pilot_profile"]["hash"] in html
    assert "pilot_parameter" in csv_text
    assert "clock.remaining_600_seconds" in csv_text


def test_package_contains_shared_bellman_and_no_legacy_policy(tmp_path):
    archive = package("mega_starmie", tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "common/runtime.py" in names
        assert "common/planner.py" in names
        assert "common/native_engine.py" in names
        assert "common/needs.py" in names
        assert "common/refresh.py" in names
        assert "common/engine.py" not in names
        assert any(name.startswith("cg/") for name in names)
        assert not any(name.startswith("common/bellman/") for name in names)
        assert "brief.html" in names and "brief.csv" in names
        assert "common/pilot.py" not in names
        assert "common/state_value.py" not in names
        assert "tuned.json" not in names
        manifest_text = bundle.read("brief.html").decode("utf-8")
        assert '"system": "bellman"' in manifest_text


@pytest.mark.parametrize("agent_name", SHIPPABLE_AGENTS)
def test_every_kaggle_bundle_contains_no_cgpy_name_or_content(tmp_path, agent_name):
    archive = package(agent_name, tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            assert "cgpy" not in name.lower(), name
            assert b"cgpy" not in bundle.read(name).lower(), name
