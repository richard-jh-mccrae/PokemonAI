"""`build`: package an agent and record an immutable Agent History row (ADR-0019)."""
from pathlib import Path

import pytest

from submit.build import build
from submit.history import read_history

FIXTURE_AGENTS = Path(__file__).resolve().parent / "fixtures" / "agents"


@pytest.mark.req("REQ-SUB-0009")
def test_build_packages_and_appends_an_immutable_history_row(tmp_path):
    hist = tmp_path / "agent_history.jsonl"
    subs = tmp_path / "submissions"

    row = build("mega_starmie", out=subs, history=hist, agents_root=FIXTURE_AGENTS)

    assert row["submission_id"] == 1
    assert row["agent"] == "mega_starmie"
    assert (subs / f"{row['artifact']}.zip").exists()          # the bundle landed under out/
    assert row["summary"]["deck_size"] == 60                   # state summary for quick diffing
    assert row["manifest_digest"].startswith("sha256:")

    # a second build is a fresh, monotonic submission — history is append-only
    row2 = build("mega_starmie", out=subs, history=hist, agents_root=FIXTURE_AGENTS)
    assert row2["submission_id"] == 2
    assert [r["submission_id"] for r in read_history(hist)] == [1, 2]


@pytest.mark.req("REQ-SUB-0009")
def test_build_accepts_an_explicit_submission_id_and_label(tmp_path):
    row = build("mega_starmie", out=tmp_path / "s", history=tmp_path / "h.jsonl",
                agents_root=FIXTURE_AGENTS, submission_id=42, label="tier1-experiment")
    assert row["submission_id"] == 42
    assert row["label"] == "tier1-experiment"


@pytest.mark.req("REQ-SUB-0009")
def test_cli_build_subcommand_records_history(tmp_path):
    from submit_agent import main

    rc = main(["build", "mega_starmie", "--out", str(tmp_path / "s"),
               "--history", str(tmp_path / "h.jsonl"), "--agents-root", str(FIXTURE_AGENTS),
               "--label", "v1"])
    assert rc == 0
    rows = read_history(tmp_path / "h.jsonl")
    assert len(rows) == 1 and rows[0]["label"] == "v1"
