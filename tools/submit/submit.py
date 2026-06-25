"""`submit`: gated upload of a Submission to the Simulation competition (ADR-0019).

Never implicit. Refuses a `-dirty` work tree (so every leaderboard point maps to a commit),
gates on the Agent Check (Deployability/Playability), composes the `-m` message from the
Manifest summary, then uploads. Kaggle's ref + score are filled in later by `collect`.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from submit.build import DEFAULT_HISTORY, DEFAULT_OUT, assemble
from submit.history import append_history

COMPETITION = "pokemon-tcg-ai-battle"   # the Simulation track — the agent's graded slug (ADR-0019)


def compose_message(row: dict) -> str:
    """The `-m` message: the join key (submission id) + a readable state digest."""
    s = row["summary"]
    msg = (f"#{row['submission_id']} {row['agent']} @{row['git_hash']} · "
           f"Tier-{s['tier']} · {s['general_hyps'] + s['deck_hyps']} hyps · "
           f"posture:{'on' if s['posture'] else 'off'} · overrides:{s['overrides']}")
    return msg + (f" · {row['label']}" if row.get("label") else "")


def _default_check(name, agents_root):
    from sim.check_agent import check_agent
    return check_agent(name, agents_root=agents_root, matches=2)


def _default_upload(zip_path: Path, message: str) -> None:
    import subprocess
    subprocess.run(["kaggle", "competitions", "submit", COMPETITION,
                    "-f", str(zip_path), "-m", message], check=True)


def submit(name: str, *, out=DEFAULT_OUT, history=DEFAULT_HISTORY, agents_root=None,
           submission_id=None, label=None, allow_dirty=False, when=None,
           check_fn=None, upload_fn=None) -> dict:
    """Build, gate, upload, and record. Raises SystemExit *before* uploading on any gate failure."""
    row, zip_path = assemble(name, out=out, history=history, agents_root=agents_root,
                             submission_id=submission_id, label=label)
    if "-dirty" in row["git_hash"] and not allow_dirty:
        raise SystemExit(f"refusing to submit a dirty work tree ({row['git_hash']}); "
                         "commit first, or pass allow_dirty=True")
    report = (check_fn or _default_check)(name, agents_root)
    if not report.ok:
        raise SystemExit(f"Agent Check failed at stage '{report.failed_stage}'; not submitting")
    row["message"] = compose_message(row)
    (upload_fn or _default_upload)(zip_path, row["message"])
    row["submitted_at"] = (when or datetime.now()).isoformat(timespec="seconds")
    append_history(history, row)
    return row
