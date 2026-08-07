"""ONE idea of the corrections corpus's on-disk shape, shared by every test that needs one.

Extracted from `tests/train/test_gates.py` (Issue #250) when a second test file needed to write a
`tmp_path` corpus. Two test files independently encoding the record shape is the same defect
**ADR-0087** was written about, one layer down: the gate's private raw-JSONL walk was a second idea
of what a record IS, and it drifted undetectably because nothing compared the two ideas. A helper
that only one file can see invites exactly that.

Lives at `tests/` root, following the suite's shared-helper convention (`pilot_helpers`,
`scouting_helpers`, `lethal_helpers`) — `tests/conftest.py` puts `tests/` on `sys.path`, so
``from corrections_helpers import ...`` resolves from any subdir.
"""
from __future__ import annotations

import json


def correction_record(episode, frame, *, seat=0, scope="decision", subject=None,
                      agent="mega_starmie", agent_build=None, correct=None, obs=True,
                      category="wasted_resource", corr_id=None):
    """One raw corrections.jsonl record, in the on-disk shape. ``seat`` is TOP-LEVEL: the
    ``decision`` snapshot has no ``seat`` field, which is why reading it off there yielded 0."""
    return {"id": corr_id if corr_id is not None else f"{episode}-{frame}", "source": "own",
            "episode_id": episode, "seat": seat,
            "agent": agent, "agent_build": agent_build, "submission_id": None,
            "agent_version": None, "episode_time": None, "tagged_at": "2026-07-31T00:00:00+00:00",
            "decision": {"frame": frame, "turn": 1, "select_context": 0, "select_type": 0,
                         "options": [], "current": {}},
            "chosen": [0], "chosen_label": "", "correct": [1] if correct is None else correct,
            "correct_label": "", "category": category, "attribution": None, "rationale": "",
            "obs": {"select": {"context": 0, "option": []}} if obs else None,
            "scope": scope, "subject": subject if subject is not None else (
                frame if scope == "decision" else (1 if scope == "turn" else None))}


def corrections_store(tmp_path, records, build="mega_starmie_20260101_abc1234"):
    """Write ``records`` as a one-build correction tree under ``tmp_path``; returns the tree ROOT
    (what `load_corrections` / `keyed_corrections` / `--store` all take)."""
    d = tmp_path / build
    d.mkdir(parents=True, exist_ok=True)
    (d / "corrections.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return tmp_path
