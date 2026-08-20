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
    assert manifest["strategy"]["prize_plan"]["prizes_to_win"] == 6
    assert summary(manifest)["system"] == "ledger"
    weights = manifest["ledger_weights"]
    assert weights["identity"]
    assert weights["scalars"]["zone_in_play"] == 1.0
    assert "primary_attacker" in weights["roles"]
    # Deck overrides must land in the resolved vector, not just be echoed back.
    for name, value in weights["deck_overrides"].items():
        group, _, key = name.partition(".")
        resolved = {"role": weights["roles"], "tag": weights["tags"], "kind": weights["kinds"],
                    "card": weights["card_worth"]}.get(group)
        if resolved is None:
            assert weights["scalars"][name] == value
        else:
            assert resolved[key] == value


def test_brief_projects_the_same_weights_to_html_and_csv():
    manifest = build_manifest(REPO / "src" / "agents" / "mega_starmie",
                              git_hash="abc123", cards={})
    html = render_brief(manifest)
    csv_text = render_brief_csv(manifest)

    assert "<details><summary>scalars" in html
    assert manifest["ledger_weights"]["identity"] in html
    assert "ledger_weight" in csv_text
    assert "scalars.zone_in_play" in csv_text
    assert "roles.primary_attacker" in csv_text
    assert "Ledger weights" in html


def test_package_contains_the_ledger_and_no_bellman_search(tmp_path):
    archive = package("mega_starmie", tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "common/runtime.py" in names
        assert "common/native_engine.py" in names
        assert "common/refresh.py" in names
        assert "common/ledger/decider.py" in names
        assert "common/ledger/seam.py" in names
        assert "common/board/state.py" in names
        # The Bellman search stack lives in deprecated/ and must never ship again.
        for retired in ("common/planner.py", "common/solver.py", "common/demand.py",
                        "common/potential.py", "common/value.py", "common/value_equations.py",
                        "common/pilot_profile.py", "common/terminal.py", "common/engine.py"):
            assert retired not in names, retired
        assert any(name.startswith("cg/") for name in names)
        assert "brief.html" in names and "brief.csv" in names
        assert "runtime_config.json" not in names
        manifest_text = bundle.read("brief.html").decode("utf-8")
        assert '"system": "ledger"' in manifest_text


@pytest.mark.parametrize("agent_name", SHIPPABLE_AGENTS)
def test_every_kaggle_bundle_contains_no_cgpy_name_or_content(tmp_path, agent_name):
    archive = package(agent_name, tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            assert "cgpy" not in name.lower(), name
            assert b"cgpy" not in bundle.read(name).lower(), name
