"""Detect which seat is *our* agent in a replay, by team name."""
from __future__ import annotations


def detect_seat(replay: dict, our_team_name: str) -> int | None:
    """``None`` when no seat matches, so the caller picks manually (self-play: both seats are ours)."""
    names = (replay.get("info") or {}).get("TeamNames") or []
    target = (our_team_name or "").strip().lower()
    if not target:
        return None
    for i, name in enumerate(names):
        if isinstance(name, str) and name.strip().lower() == target:
            return i
    return None
