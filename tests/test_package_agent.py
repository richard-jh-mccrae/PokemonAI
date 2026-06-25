"""Packaging assembles a self-contained, prunable submission zip (ADR-0004)."""
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from package_agent import package

# A self-contained agent fixture (main.py + strategy.py + deck.csv + deck.txt) so these tests don't
# depend on a deletable source agent under my_submissions/agents/ (shared common/ + cg/ still come
# from there). Delete my_submissions/agents/mega_starmie and these stay green.
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
    assert not any(n.endswith(".md") for n in names)             # docs pruned (CONTEXT.md, README.md, …)


@pytest.mark.req("REQ-SIM-0004")
def test_package_ships_sibling_py_modules_not_the_decklist_txt(tmp_path):
    # the fixture has main.py + strategy.py + deck.csv + deck.txt
    with zipfile.ZipFile(package("mega_starmie", tmp_path, agents_root=FIXTURE_AGENTS)) as zf:
        names = zf.namelist()
    top = {n for n in names if "/" not in n.rstrip("/")}

    assert "main.py" in top
    assert "strategy.py" in top   # sibling module must ship so the bundle imports
    assert "deck.csv" in top
    assert "deck.txt" not in top  # human-readable decklist must not ship


@pytest.mark.req("REQ-SIM-0004")
def test_package_accepts_a_path_to_the_agent_dir(tmp_path):
    # a tab-completed path (trailing separator), not just a bare name, should work
    zip_path = package(f"{FIXTURE_AGENTS / 'mega_starmie'}/", tmp_path, agents_root=FIXTURE_AGENTS)
    assert zip_path.exists()
    assert zip_path.stem == "mega_starmie"  # normalized to the bare name
