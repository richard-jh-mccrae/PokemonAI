from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from submit.brief import build_manifest, render_brief, render_brief_csv
from submit.history import summary
from submit.package import package


REPO = Path(__file__).resolve().parents[2]
SHIPPABLE_AGENTS = ("dragapult_ex", "mega_lucario", "mega_starmie")


def test_manifest_describes_declarations_and_ledger_only():
    manifest = build_manifest(REPO / "src" / "agents" / "mega_starmie",
                              git_hash="abc123", cards={})
    assert manifest["system"] == "ledger"
    assert manifest["strategy"]["roles"]["1030"] == ["primary_attacker"]
    assert manifest["strategy"]["roles"]["1031"] == ["primary_attacker"]
    assert manifest["strategy"]["prize_plan"] == {
        "protect": [1031], "offer": [666],
    }
    assert not ({"lines", "partners", "worth_overrides"} & manifest["strategy"].keys())
    assert summary(manifest)["system"] == "ledger"
    configuration = manifest["valuation_configuration"]
    assert configuration["identity"]
    assert configuration["values"]["combat.attack_now"] == 0.35
    assert not any("role." in key for key in configuration["values"])
    assert configuration["deck_overlay"] == {
        "demand.dead": 0.15, "energy.concentration": 0.02,
        "kind.special_energy": 0.05}
    assert manifest["compute_configuration"]["identity"]
    assert manifest["compute_configuration"]["search"]["path_node_budget"] == 128
    assert manifest["compute_configuration"]["search"]["main_depth_budget"] == 0
    assert manifest["compute_configuration"]["search"]["main_continuation_discount"] == 0.8
    assert manifest["compute_configuration"]["search"]["node_budget"] == 4096
    assert manifest["compute_configuration"]["policy"]["tie_seed"] == 1178


@pytest.mark.parametrize("agent_name", SHIPPABLE_AGENTS)
def test_every_shipped_deck_declares_a_prize_plan(agent_name):
    manifest = build_manifest(REPO / "src" / "agents" / agent_name,
                              git_hash="abc123", cards={})
    plan = manifest["strategy"]["prize_plan"]
    assert set(plan) == {"protect", "offer"}


def test_brief_projects_the_same_weights_to_html_and_csv():
    manifest = build_manifest(REPO / "src" / "agents" / "mega_starmie",
                              git_hash="abc123", cards={})
    html = render_brief(manifest)
    csv_text = render_brief_csv(manifest)

    assert "<details><summary>values" in html
    assert manifest["valuation_configuration"]["identity"] in html
    assert "valuation_coefficient" in csv_text
    assert "zone.in_play" in csv_text
    assert "combat.attack_now" in csv_text
    assert "Valuation configuration" in html


def test_package_contains_the_ledger_and_no_bellman_search(tmp_path):
    archive = package("mega_starmie", tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "common/runtime.py" in names
        assert "common/native_engine.py" in names
        assert "common/refresh.py" in names
        assert "common/ledger/decider.py" in names
        assert "common/ledger/configuration.py" in names
        assert "common/ledger/features.py" in names
        assert "common/ledger/activation.py" in names
        assert "common/cards/function_catalog.py" in names
        assert "common/opponent/model.py" in names
        assert "common/scouting/read.py" not in names
        assert "common/scouting/brief.schema.json" not in names
        assert "common/ledger/weights.py" not in names
        assert "common/ledger/seam.py" in names
        assert "common/observation/state.py" in names
        assert "common/observation/record.py" in names
        assert "common/telemetry/__init__.py" in names
        assert "common/telemetry/core.py" in names
        assert "common/telemetry/build_provenance.json" in names
        # The Bellman search stack lives in deprecated/ and must never ship again.
        for retired in ("common/planner.py", "common/solver.py", "common/demand.py",
                        "common/potential.py", "common/value.py", "common/value_equations.py",
                        "common/pilot_profile.py", "common/terminal.py", "common/engine.py",
                        "common/information.py",
                        "common/state.py", "common/cards/functions/damage_context.py"):
            assert retired not in names, retired
        assert not any(
            marker in bundle.read(name)
            for name in names if name.endswith(".py")
            for marker in (b"from deprecated", b"import deprecated"))
        assert any(name.startswith("cg/") for name in names)
        assert "brief.html" in names and "brief.csv" in names
        assert "runtime_config.json" not in names
        assert "common/card_effects.json" not in names   # authoring source; nothing shipped reads it
        manifest_text = bundle.read("brief.html").decode("utf-8")
        assert '"system": "ledger"' in manifest_text
        provenance = __import__("json").loads(
            bundle.read("common/telemetry/build_provenance.json"))
        assert provenance["agent"] == "mega_starmie"
        assert provenance["code"]
        assert provenance["artifact"]
        assert provenance["data"]["valuation"]
        assert provenance["data"]["compute"]


@pytest.mark.parametrize("agent_name", SHIPPABLE_AGENTS)
def test_every_kaggle_bundle_contains_no_cgpy_name_or_content(tmp_path, agent_name):
    archive = package(agent_name, tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            assert "cgpy" not in name.lower(), name
            assert b"cgpy" not in bundle.read(name).lower(), name
