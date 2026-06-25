"""`build`: package an agent and record it to the local build ledger, not Agent History (ADR-0019)."""
from pathlib import Path

import pytest

from submit.build import build
from submit.history import read_history

FIXTURE_AGENTS = Path(__file__).resolve().parent / "fixtures" / "agents"


@pytest.mark.req("REQ-SUB-0009")
def test_build_records_to_the_local_ledger_not_agent_history(tmp_path):
    subs = tmp_path / "submissions"
    builds = subs / "builds.jsonl"
    history = tmp_path / "agent_history.jsonl"

    row = build("mega_starmie", out=subs, builds=builds, agents_root=FIXTURE_AGENTS)

    assert row["agent"] == "mega_starmie"
    assert (subs / f"{row['artifact']}.zip").exists()          # the bundle landed under out/
    assert row["summary"]["deck_size"] == 60
    assert row["manifest_digest"].startswith("sha256:")
    assert [r["submission_id"] for r in read_history(builds)] == [row["submission_id"]]  # ledgered
    assert not history.exists()                                 # but build never touches Agent History


@pytest.mark.req("REQ-SUB-0009")
def test_build_ids_are_monotonic_in_the_ledger(tmp_path):
    subs, builds = tmp_path / "s", tmp_path / "s" / "builds.jsonl"
    one = build("mega_starmie", out=subs, builds=builds, agents_root=FIXTURE_AGENTS)
    two = build("mega_starmie", out=subs, builds=builds, agents_root=FIXTURE_AGENTS)
    assert (one["submission_id"], two["submission_id"]) == (1, 2)


@pytest.mark.req("REQ-SUB-0009")
def test_build_accepts_an_explicit_submission_id_and_label(tmp_path):
    row = build("mega_starmie", out=tmp_path / "s", builds=tmp_path / "s" / "builds.jsonl",
                agents_root=FIXTURE_AGENTS, submission_id=42, label="tier1-experiment")
    assert row["submission_id"] == 42
    assert row["label"] == "tier1-experiment"


@pytest.mark.req("REQ-SUB-0009")
def test_cli_build_records_to_ledger_only(tmp_path):
    from submit_agent import main

    rc = main(["build", "mega_starmie", "--out", str(tmp_path / "s"),
               "--builds", str(tmp_path / "s" / "builds.jsonl"),
               "--agents-root", str(FIXTURE_AGENTS)])
    assert rc == 0
    assert (tmp_path / "s" / "builds.jsonl").exists()          # logged to the local ledger
    assert not (tmp_path / "agent_history.jsonl").exists()      # not to committed Agent History
