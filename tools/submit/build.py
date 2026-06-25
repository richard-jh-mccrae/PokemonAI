"""`build`: package an agent and record it to the local build ledger (ADR-0019).

First step of the lifecycle: build → [self-play, later] → submit. It never uploads and never
touches the committed Agent History — it appends to `data/submissions/builds.jsonl` (gitignored).
`submit` later promotes a chosen build into the committed `agent_history.jsonl`.
"""
from __future__ import annotations

from pathlib import Path

from submit.brief import build_manifest
from submit.history import append_history, manifest_digest, next_submission_id, summary
from submit.package import REPO, package

DEFAULT_OUT = REPO / "data" / "submissions"
DEFAULT_BUILDS = DEFAULT_OUT / "builds.jsonl"            # local ledger of built artifacts (gitignored)
DEFAULT_HISTORY = REPO / "data" / "agent_history.jsonl"  # committed: agents actually submitted


def build(name: str, *, out: Path | str = DEFAULT_OUT, builds: Path | str = DEFAULT_BUILDS,
          agents_root: Path | None = None, submission_id: int | None = None,
          label: str | None = None) -> dict:
    """Package `name`, append a build record to the local ledger, and return it.

    `submission_id` defaults to the next monotonic id (the `N` you later pass to `submit`);
    `label` names the experiment. The Bundle's `artifact` stem is the join key downstream.
    """
    sid = submission_id if submission_id is not None else next_submission_id(builds)
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
    append_history(builds, row)    # local ledger; submit promotes the chosen one to agent_history
    return row
