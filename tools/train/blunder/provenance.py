"""Derive the agent **build identity** from a replay's path for traceability (ADR-0018).

Replays live under ``submissions/<agent>_<YYYYMMDD[-HHMMSS]>_<sha>[-dirty]/replays/<id>.json``;
the submission-folder stem encodes which exact build played the game. Best-effort: a path with
no such stem yields a null identity.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePath

_STEM = re.compile(r"^(?P<agent>.+)_(?P<date>\d{8}(?:-\d{6})?)_(?P<sha>.+)$")
_NULL = {"agent_build": None, "agent": None, "agent_version": None, "built_at": None}


def _built_at(date: str) -> str:
    fmt = "%Y%m%d-%H%M%S" if "-" in date else "%Y%m%d"
    return datetime.strptime(date, fmt).isoformat()


def parse_build_stem(stem: str) -> dict:
    """Parse a submission-folder stem into its build-identity parts (or nulls if it doesn't match)."""
    m = _STEM.match(stem)
    if not m:
        return dict(_NULL)
    return {"agent_build": stem, "agent": m["agent"], "agent_version": m["sha"],
            "built_at": _built_at(m["date"])}


def build_identity(replay_path) -> dict:
    """Scan the replay path's parts for a submission stem and return its build identity."""
    for part in PurePath(replay_path).parts:
        info = parse_build_stem(part)
        if info["agent_build"]:
            return info
    return dict(_NULL)
