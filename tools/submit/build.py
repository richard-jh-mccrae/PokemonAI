"""`build`: stage + zip an agent, write its Brief, and record an Agent History row (ADR-0019).

The first step of the Submission lifecycle (build -> submit -> collect). Safe and silent: it
never uploads. Bundles land under `data/submissions/` (gitignored); the row appends to the
committed `data/agent_history.jsonl`.
"""
from __future__ import annotations

from pathlib import Path

from package_agent import REPO, package

from submit.brief import build_manifest
from submit.history import append_history, manifest_digest, next_submission_id, summary

DEFAULT_OUT = REPO / "data" / "submissions"
DEFAULT_HISTORY = REPO / "data" / "agent_history.jsonl"


def assemble(name: str, *, out: Path | str, history: Path | str, agents_root: Path | None,
             submission_id: int | None, label: str | None):
    """Package `name` and assemble its history row (NOT yet appended). Returns (row, zip_path)."""
    sid = submission_id if submission_id is not None else next_submission_id(history)
    zip_path = package(name, Path(out), agents_root=agents_root)
    manifest = build_manifest(Path(out) / Path(name).name)   # the exact staged bundle that shipped
    prov = manifest["provenance"]
    row = {
        "submission_id": sid,
        "label": label,
        "agent": prov["agent"],
        "artifact": zip_path.stem,
        "git_hash": prov["git_hash"],
        "built_at": prov["built_at"],
        "manifest_digest": manifest_digest(manifest),
        "summary": summary(manifest),
        "submitted_at": None,      # filled by `submit`
        "message": None,           # the `-m` text `submit` sent
        "kaggle_ref": None,        # filled by `collect` once Kaggle assigns it
    }
    return row, zip_path


def build(name: str, *, out: Path | str = DEFAULT_OUT, history: Path | str = DEFAULT_HISTORY,
          agents_root: Path | None = None, submission_id: int | None = None,
          label: str | None = None) -> dict:
    """Package `name`, record its history row, and return the row.

    `submission_id` defaults to the next monotonic id; pass one to override. `label` names the
    experiment. The Bundle's `artifact` stem is the join key to the Performance Log.
    """
    row, _ = assemble(name, out=out, history=history, agents_root=agents_root,
                      submission_id=submission_id, label=label)
    append_history(history, row)
    return row
