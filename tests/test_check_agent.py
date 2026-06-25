"""Agent Check harness (tools/sim): contents -> legality -> playability -> deployability."""
from pathlib import Path

import pytest

from sim.check_agent import check_contents, check_legality

from conftest import require_kaggle_environments

REPO = Path(__file__).resolve().parents[1]
# Self-contained agent fixtures (so tests don't depend on a deletable source agent under
# src/agents/). `mega_starmie` is a complete, legal, shippable agent copied here.
FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
LEGAL_DECK = FIXTURE_AGENTS / "mega_starmie" / "deck.csv"


@pytest.mark.req("REQ-SIM-0001")
def test_contents_fails_naming_the_missing_file(tmp_path):
    (tmp_path / "deck.csv").write_text("3\n")  # deck present, main.py missing
    result = check_contents(tmp_path)
    assert not result.ok
    assert "main.py" in result.detail


@pytest.mark.req("REQ-SIM-0001")
def test_contents_passes_when_main_and_deck_present(tmp_path):
    (tmp_path / "main.py").write_text("")
    (tmp_path / "deck.csv").write_text("3\n")
    assert check_contents(tmp_path).ok


@pytest.mark.req("REQ-SIM-0004")
def test_contents_bundle_requires_engine_and_common(tmp_path):
    (tmp_path / "main.py").write_text("")
    (tmp_path / "deck.csv").write_text("3\n")
    # the extracted Bundle must also carry the shared cg/ and common/ packages
    result = check_contents(tmp_path, required=("main.py", "deck.csv", "cg", "common"))
    assert not result.ok
    assert "cg" in result.detail and "common" in result.detail


@pytest.mark.req("REQ-SIM-0002")
def test_legality_fails_when_not_60_rows(tmp_path):
    deck = tmp_path / "deck.csv"
    deck.write_text("\n".join(["3"] * 59) + "\n")  # 59 rows, not 60
    result = check_legality(deck)
    assert not result.ok
    assert "60" in result.detail


@pytest.mark.req("REQ-SIM-0002")
def test_legality_passes_for_the_shipped_legal_deck():
    assert check_legality(LEGAL_DECK).ok, "the fixture agent's deck should be legal"


@pytest.mark.req("REQ-SIM-0002")
def test_legality_fails_with_the_specific_rule(tmp_path):
    deck = tmp_path / "deck.csv"
    deck.write_text("\n".join(["3"] * 60) + "\n")  # 60 basic Energy => no Basic Pokemon
    result = check_legality(deck)
    assert not result.ok
    assert "Basic" in result.detail  # decoded errorType 3, not a generic message


@pytest.mark.req("REQ-SIM-0003")
def test_playability_fixture_self_play_is_clean():
    require_kaggle_environments()
    from sim.check_agent import check_playability

    agent_dir = FIXTURE_AGENTS / "mega_starmie"   # shared common/cg resolve via src on sys.path
    result = check_playability(agent_dir, syspath_roots=[REPO / "src"], matches=2)
    assert result.ok, result.detail


@pytest.mark.req("REQ-SIM-0003")
def test_playability_loads_sibling_modules_from_agent_dir():
    require_kaggle_environments()
    from sim.check_agent import check_playability

    # main.py does `from helper import OK` — only resolvable if the agent dir is on sys.path
    agent_dir = REPO / "tests" / "fixtures" / "agents" / "sibling"
    result = check_playability(agent_dir, syspath_roots=[], matches=1)
    assert result.ok, result.detail


@pytest.mark.req("REQ-SIM-0003")
def test_playability_detects_a_crash_and_saves_replay(tmp_path):
    require_kaggle_environments()
    from sim.check_agent import check_playability

    crasher = REPO / "tests" / "fixtures" / "agents" / "crasher"
    reports = tmp_path / "reports"
    result = check_playability(crasher, syspath_roots=[], matches=1, reports_dir=reports)
    assert not result.ok
    assert "ERROR" in result.detail
    assert list(reports.glob("*.json")), "expected a replay artifact on failure"


@pytest.mark.req("REQ-SIM-0004")
def test_deployability_packages_extracts_and_runs(tmp_path):
    require_kaggle_environments()
    from sim.check_agent import check_deployability

    result = check_deployability("mega_starmie", work_dir=tmp_path, agents_root=FIXTURE_AGENTS)
    assert result.ok, result.detail


@pytest.mark.req("REQ-SIM-0005")
def test_check_agent_stops_at_first_failed_stage():
    from sim.check_agent import check_agent

    report = check_agent(
        "illegal_deck", agents_root=REPO / "tests" / "fixtures" / "agents", deployability=False
    )
    assert not report.ok
    assert report.failed_stage == "legality"
    assert [s.stage for s in report.stages] == ["contents", "legality"]  # heavy stages not reached


@pytest.mark.req("REQ-SIM-0005")
def test_cli_exits_nonzero_for_a_missing_agent():
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "sim" / "check_agent.py"), "__nonexistent__"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "contents" in (proc.stdout + proc.stderr).lower()


@pytest.mark.req("REQ-SIM-0005")
def test_agent_name_accepts_a_path_or_bare_name():
    from sim.check_agent import _agent_name

    assert _agent_name("mega_starmie") == "mega_starmie"
    assert _agent_name("tests/fixtures/agents/crasher") == "crasher"
    assert _agent_name(".\\tests\\fixtures\\agents\\mega_starmie\\") == "mega_starmie"


@pytest.mark.req("REQ-SIM-0005")
def test_cli_runs_a_real_agent_through_playability():
    require_kaggle_environments()
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "sim" / "check_agent.py"),
         "mega_starmie", "--agents-root", str(FIXTURE_AGENTS), "--no-deployability", "--matches", "1"],
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "[PASS] playability" in out
    assert "OpenSpiel exception" not in out        # noisy kaggle_environments import is muted
    assert "Successfully loaded OpenSpiel" not in out
    assert "Logging error" not in out              # and the import doesn't break logging
