from datetime import datetime
import json

import pytest

from sim.check_agent import Report, StageResult
from submit.history import read_history
from submit.submit import submit


def test_successful_check_always_reaches_upload_then_records_history(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    artifact = "mega_starmie_test"
    (out / f"{artifact}.zip").write_bytes(b"zip")
    builds = tmp_path / "builds.jsonl"
    builds.write_text(json.dumps({
        "submission_id": 69,
        "agent": "mega_starmie",
        "artifact": artifact,
        "git_hash": "36d885f2",
        "summary": {"roles": 2, "prize_selectors": 2, "scouting": False},
    }) + "\n")
    history = tmp_path / "agent_history.jsonl"
    checked, uploaded = [], []

    def check(agent, agents_root):
        checked.append((agent, agents_root))
        return Report(agent, [StageResult(True, "deployability")])

    def upload(zip_path, message):
        uploaded.append((zip_path.name, message))

    row = submit(
        out=out, builds=builds, history=history,
        check_fn=check, upload_fn=upload,
        when=datetime(2026, 8, 12, 20, 0, 0),
    )

    assert checked == [("mega_starmie", None)]
    assert uploaded == [(f"{artifact}.zip", row["message"])]
    assert read_history(history) == [row]


def test_failed_check_reports_stage_reason_and_upload_status(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "failed.zip").write_bytes(b"zip")
    builds = tmp_path / "builds.jsonl"
    builds.write_text(json.dumps({
        "submission_id": 70,
        "agent": "mega_starmie",
        "artifact": "failed",
        "git_hash": "clean",
        "summary": {"roles": 2, "prize_selectors": 2, "scouting": False},
    }) + "\n")

    def failed_check(agent, agents_root):
        return Report(agent, [StageResult(
            False, "deployability",
            "exact bundle mirror timed out after 600s",
        )])

    with pytest.raises(SystemExit) as raised:
        submit(out=out, builds=builds, history=tmp_path / "history.jsonl",
               check_fn=failed_check, upload_fn=lambda *_: pytest.fail("upload ran"))

    message = str(raised.value)
    assert message.splitlines() == [
        "SUBMISSION BLOCKED [deployability]",
        "Reason: exact bundle mirror timed out after 600s",
        "Upload: not attempted",
    ]
