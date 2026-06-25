"""Packaging assembles a self-contained, prunable submission zip (ADR-0004)."""
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from package_agent import artifact_stem, package

# A self-contained agent fixture (main.py + strategy.py + deck.csv + deck.txt) so these tests don't
# depend on a deletable source agent under src/agents/ (shared common/ + cg/ still come
# from there). Delete src/agents/mega_starmie and these stay green.
FIXTURE_AGENTS = Path(__file__).resolve().parent / "fixtures" / "agents"


@pytest.mark.req("REQ-SCOUT-0007")
def test_package_produces_self_contained_zip(tmp_path):
    zip_path = package("mega_starmie", tmp_path, agents_root=FIXTURE_AGENTS)
    with zipfile.ZipFile(zip_path) as zf:   # close the handle (a leak locks tmp_path on Windows)
        names = zf.namelist()

    assert "main.py" in names and "deck.csv" in names
    assert any(n.startswith("cg/") for n in names)              # shared engine bundled
    assert any(n.startswith("common/scouting/") for n in names)  # shared scouting bundled
    assert not any("__pycache__" in n for n in names)            # pruned
    # the build card now ships as brief.html (ADR-0019); all .md (CONTEXT.md, README.md, …) are pruned
    assert not any(n.endswith(".md") for n in names)
    assert "brief.html" in names


@pytest.mark.req("REQ-SIM-0004")
def test_package_ships_sibling_py_modules_not_the_decklist_txt(tmp_path):
    # the fixture has main.py + strategy.py + deck.csv + deck.txt
    with zipfile.ZipFile(package("mega_starmie", tmp_path, agents_root=FIXTURE_AGENTS)) as zf:
        names = zf.namelist()
    top = {n for n in names if "/" not in n.rstrip("/")}

    assert "main.py" in top
    assert "strategy.py" in top   # sibling module must ship so the bundle imports
    assert "deck.csv" in top
    assert "deck.txt" not in top   # ADR-0019: the decklist now lives in brief.html, not a raw file


def test_fixture_main_mirrors_the_real_agent_hook():
    """REQ-SIM-0004: the packaging fixture's main.py stands in for the deployable agent hook —
    keep them byte-identical so fixture-based tests can't drift from what actually ships (e.g. the
    `overrides`/`functions` wiring). Skips if the real agent was deleted (the fixture is
    deliberately self-contained)."""
    real = Path(__file__).resolve().parents[1] / "src" / "agents" / "mega_starmie" / "main.py"
    if not real.exists():
        pytest.skip("real agent absent (fixture is intentionally standalone)")
    fixture = FIXTURE_AGENTS / "mega_starmie" / "main.py"
    assert fixture.read_text(encoding="utf-8") == real.read_text(encoding="utf-8")


def test_package_ships_tuned_json_when_present(tmp_path):
    """REQ-PKG-0002: machine-tuned weights (tuned.json) ride along in the Bundle so the shipped
    agent applies them (ADR-0018)."""
    with zipfile.ZipFile(package("mega_starmie", tmp_path, agents_root=FIXTURE_AGENTS)) as zf:
        top = {n for n in zf.namelist() if "/" not in n.rstrip("/")}
    assert "tuned.json" in top


@pytest.mark.req("REQ-SIM-0004")
def test_package_accepts_a_path_to_the_agent_dir(tmp_path):
    # a tab-completed path (trailing separator), not just a bare name, should work
    zip_path = package(f"{FIXTURE_AGENTS / 'mega_starmie'}/", tmp_path,
                       agents_root=FIXTURE_AGENTS, stamp=False)  # stable name isolates normalization
    assert zip_path.exists()
    assert zip_path.stem == "mega_starmie"  # normalized to the bare name


@pytest.mark.req("REQ-SIM-0004")
def test_artifact_stem_is_name_date_githash():
    # deterministic stamp: <name>_<YYYYMMDD>_<githash> (date only — time is dropped)
    stem = artifact_stem("mega_starmie", when=datetime(2026, 6, 25, 14, 30, 5), git_hash="623ea73")
    assert stem == "mega_starmie_20260625_623ea73"


@pytest.mark.req("REQ-SIM-0004")
def test_stamped_zip_lands_under_dist_with_date_and_githash(tmp_path):
    # default build (stamp=True) names the deploy artifact by build date + commit (no time)
    zip_path = package("mega_starmie", tmp_path, agents_root=FIXTURE_AGENTS)
    assert zip_path.parent == tmp_path
    assert re.fullmatch(r"mega_starmie_\d{8}_.+\.zip", zip_path.name)


@pytest.mark.req("REQ-SIM-0004")
def test_no_stamp_yields_the_stable_name(tmp_path):
    zip_path = package("mega_starmie", tmp_path, agents_root=FIXTURE_AGENTS, stamp=False)
    assert zip_path.name == "mega_starmie.zip"
