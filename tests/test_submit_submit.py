"""`submit` uploads a prior build's *exact* zip — gated and never implicit (ADR-0019)."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from submit.build import build
from submit.history import read_history
from submit.package import REPO, _git_hash
from submit.submit import compose_message, submit

FIXTURE_AGENTS = Path(__file__).resolve().parent / "fixtures" / "agents"


def _ok(name, agents_root):
    return SimpleNamespace(ok=True, failed_stage=None)


def _fail(name, agents_root):
    return SimpleNamespace(ok=False, failed_stage="playability")


def _built(tmp_path, **kw):
    """A tmp bundle dir + build ledger holding one build of the fixture agent."""
    out, builds = tmp_path / "s", tmp_path / "s" / "builds.jsonl"
    row = build("mega_starmie", out=out, builds=builds, agents_root=FIXTURE_AGENTS, **kw)
    return out, builds, row


@pytest.mark.req("REQ-SUB-0010")
def test_compose_message_carries_id_and_state_digest():
    row = {"submission_id": 7, "agent": "mega_starmie", "git_hash": "abc1234", "label": "exp",
           "summary": {"tier": 0, "general_hyps": 10, "deck_hyps": 3, "posture": False, "overrides": 2}}
    msg = compose_message(row)
    assert msg.startswith("#7 mega_starmie @abc1234")
    assert "Tier-0" in msg and "13 hyps" in msg and "posture:off" in msg and "exp" in msg


@pytest.mark.req("REQ-SUB-0010")
def test_submit_uploads_latest_builds_exact_zip_and_records(tmp_path):
    out, builds, built = _built(tmp_path)
    history = tmp_path / "agent_history.jsonl"
    uploads = []

    row = submit(None, out=out, builds=builds, history=history, allow_dirty=True, check_fn=_ok,
                 upload_fn=lambda z, m: uploads.append((z, m)), when=datetime(2026, 6, 25, 14, 30, 5))

    zip_path, msg = uploads[0]
    assert Path(zip_path) == out / f"{built['artifact']}.zip"   # the EXACT prior build, not a re-package
    assert msg == row["message"] and row["submitted_at"].startswith("2026-06-25")
    assert read_history(history)[0]["submission_id"] == built["submission_id"]


@pytest.mark.req("REQ-SUB-0010")
def test_submit_can_target_a_specific_build_id(tmp_path):
    out, builds = tmp_path / "s", tmp_path / "s" / "builds.jsonl"
    build("mega_starmie", out=out, builds=builds, agents_root=FIXTURE_AGENTS)   # #1
    build("mega_starmie", out=out, builds=builds, agents_root=FIXTURE_AGENTS)   # #2 (latest)
    uploads = []

    row = submit(1, out=out, builds=builds, history=tmp_path / "h.jsonl", allow_dirty=True,
                 check_fn=_ok, upload_fn=lambda z, m: uploads.append(z))
    assert row["submission_id"] == 1                            # honored the explicit id, not the latest


@pytest.mark.req("REQ-SUB-0010")
def test_submit_aborts_on_a_failed_check_without_uploading_or_recording(tmp_path):
    out, builds, _ = _built(tmp_path)
    history = tmp_path / "h.jsonl"
    uploads = []
    with pytest.raises(SystemExit):
        submit(None, out=out, builds=builds, history=history, allow_dirty=True, check_fn=_fail,
               upload_fn=lambda z, m: uploads.append(1))
    assert uploads == []                                        # gate fires before upload
    assert read_history(history) == []                          # nothing recorded


@pytest.mark.req("REQ-SUB-0010")
def test_submit_errors_when_there_are_no_builds(tmp_path):
    with pytest.raises(SystemExit):
        submit(None, out=tmp_path / "s", builds=tmp_path / "s" / "builds.jsonl",
               history=tmp_path / "h.jsonl", check_fn=_ok, upload_fn=lambda z, m: None)


@pytest.mark.req("REQ-SUB-0010")
def test_submit_refuses_a_dirty_build_by_default(tmp_path):
    if "-dirty" not in _git_hash(REPO):
        pytest.skip("work tree is clean; the refuse-dirty path isn't exercisable here")
    out, builds, _ = _built(tmp_path)
    uploads = []
    with pytest.raises(SystemExit) as exc:
        submit(None, out=out, builds=builds, history=tmp_path / "h.jsonl",
               check_fn=_ok, upload_fn=lambda z, m: uploads.append(1))
    assert "dirty" in str(exc.value).lower()
    assert uploads == []
