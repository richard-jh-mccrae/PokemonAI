"""`submit` is gated and never implicit (ADR-0019). Kaggle upload + Agent Check are injected."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from package_agent import REPO, _git_hash
from submit.history import read_history
from submit.submit import compose_message, submit

FIXTURE_AGENTS = Path(__file__).resolve().parent / "fixtures" / "agents"


def _ok(name, agents_root):
    return SimpleNamespace(ok=True, failed_stage=None)


def _fail(name, agents_root):
    return SimpleNamespace(ok=False, failed_stage="playability")


@pytest.mark.req("REQ-SUB-0010")
def test_compose_message_carries_id_and_state_digest():
    row = {"submission_id": 7, "agent": "mega_starmie", "git_hash": "abc1234", "label": "exp",
           "summary": {"tier": 0, "general_hyps": 10, "deck_hyps": 3, "posture": False, "overrides": 2}}
    msg = compose_message(row)
    assert msg.startswith("#7 mega_starmie @abc1234")
    assert "Tier-0" in msg and "13 hyps" in msg and "posture:off" in msg and "exp" in msg


@pytest.mark.req("REQ-SUB-0010")
def test_submit_gates_then_uploads_and_records(tmp_path):
    uploads = []
    row = submit("mega_starmie", out=tmp_path / "s", history=tmp_path / "h.jsonl",
                 agents_root=FIXTURE_AGENTS, allow_dirty=True, check_fn=_ok,
                 upload_fn=lambda z, m: uploads.append((z, m)),
                 when=datetime(2026, 6, 25, 14, 30, 5))

    assert len(uploads) == 1
    zip_path, msg = uploads[0]
    assert Path(zip_path).exists() and msg == row["message"]   # the staged zip + the -m text
    assert row["submitted_at"].startswith("2026-06-25")
    assert read_history(tmp_path / "h.jsonl")[0]["message"] == msg


@pytest.mark.req("REQ-SUB-0010")
def test_submit_aborts_on_a_failed_check_without_uploading_or_recording(tmp_path):
    uploads = []
    with pytest.raises(SystemExit):
        submit("mega_starmie", out=tmp_path / "s", history=tmp_path / "h.jsonl",
               agents_root=FIXTURE_AGENTS, allow_dirty=True, check_fn=_fail,
               upload_fn=lambda z, m: uploads.append(1))
    assert uploads == []                                  # gate fires before the upload
    assert read_history(tmp_path / "h.jsonl") == []       # and nothing is recorded


@pytest.mark.req("REQ-SUB-0010")
def test_submit_refuses_a_dirty_work_tree_by_default(tmp_path):
    if "-dirty" not in _git_hash(REPO):
        pytest.skip("work tree is clean; the refuse-dirty path isn't exercisable here")
    uploads = []
    with pytest.raises(SystemExit) as exc:
        submit("mega_starmie", out=tmp_path / "s", history=tmp_path / "h.jsonl",
               agents_root=FIXTURE_AGENTS, check_fn=_ok, upload_fn=lambda z, m: uploads.append(1))
    assert "dirty" in str(exc.value).lower()
    assert uploads == []
