"""Packaging assembles a self-contained, prunable submission zip (ADR-0004)."""
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from package_agent import artifact_stem, package, version_control_md

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
    # the only .md that ships is the build card; common/cg docs (CONTEXT.md, README.md, …) are pruned
    assert [n for n in names if n.endswith(".md")] == ["version_control.md"]


@pytest.mark.req("REQ-SIM-0004")
def test_package_ships_sibling_py_modules_and_the_decklist_txt(tmp_path):
    # the fixture has main.py + strategy.py + deck.csv + deck.txt
    with zipfile.ZipFile(package("mega_starmie", tmp_path, agents_root=FIXTURE_AGENTS)) as zf:
        names = zf.namelist()
    top = {n for n in names if "/" not in n.rstrip("/")}

    assert "main.py" in top
    assert "strategy.py" in top   # sibling module must ship so the bundle imports
    assert "deck.csv" in top
    assert "deck.txt" in top       # human-readable decklist ships alongside deck.csv


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


@pytest.mark.req("REQ-SIM-0004")
def test_version_control_md_renders_agent_date_time_githash():
    md = version_control_md("mega_starmie", datetime(2026, 6, 25, 14, 30, 5), "623ea73-dirty")
    assert "agent: mega_starmie" in md
    assert "date: 2026-06-25" in md
    assert "time: 14:30:05" in md
    assert "git hash: 623ea73-dirty" in md


@pytest.mark.req("REQ-SIM-0004")
def test_package_writes_version_control_card(tmp_path):
    # the build card ships at the bundle root and names the agent it was built for
    with zipfile.ZipFile(package("mega_starmie", tmp_path, agents_root=FIXTURE_AGENTS)) as zf:
        assert "version_control.md" in zf.namelist()
        card = zf.read("version_control.md").decode("utf-8")
    assert "agent: mega_starmie" in card
    assert "git hash:" in card
