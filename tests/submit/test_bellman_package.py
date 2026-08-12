from __future__ import annotations

import json
import zipfile
from pathlib import Path

from submit.brief import build_manifest
from submit.history import summary
from submit.package import package


REPO = Path(__file__).resolve().parents[2]


def test_manifest_describes_declarations_and_bellman_only():
    manifest = build_manifest(REPO / "src" / "agents" / "mega_starmie",
                              git_hash="abc123", cards={})
    assert manifest["system"] == "bellman"
    assert manifest["strategy"]["roles"]["1031"] == ["win_condition", "primary_attacker"]
    assert manifest["strategy"]["prize_plan"]["prizes_to_win"] == 6
    assert summary(manifest)["system"] == "bellman"


def test_package_contains_shared_bellman_and_no_legacy_policy(tmp_path):
    archive = package("mega_starmie", tmp_path, stamp=False)
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "common/runtime.py" in names
        assert "common/planner.py" in names
        assert not any(name.startswith("common/bellman/") for name in names)
        assert "brief.html" in names and "brief.csv" in names
        assert "common/pilot.py" not in names
        assert "common/state_value.py" not in names
        assert "tuned.json" not in names
        manifest_text = bundle.read("brief.html").decode("utf-8")
        assert '"system": "bellman"' in manifest_text
