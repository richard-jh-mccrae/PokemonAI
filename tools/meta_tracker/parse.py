"""Replay JSON -> compact episode extract.

Full decks live in an agent-0-only ``visualize`` field (the agent observation
hides the opponent) — see docs/adr/0001. We keep both 60-card decklists plus the
result and sampling context; the 44-frame play-by-play is discarded (ADR-0002).
"""
from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .archetype import Archetype, classify


@dataclass
class EpisodeRecord:
    episode_id: int
    band: str | None
    created_at: str | None
    end_time: str | None
    team0: str
    team1: str
    winner_index: int | None        # 0, 1, or None for a draw
    sampled_index: int | None       # which player is the sampled submission
    sampled_rating: float | None    # publicScore (~mu) of the sampled submission
    sampled_sub_date: str | None
    sampled_episodes: int | None    # episode count (sigma proxy / settledness)
    deck0: list[int]
    deck1: list[int]
    arch0: str
    arch1: str
    mains0: list[str] = field(default_factory=list)
    mains1: list[str] = field(default_factory=list)
    subs0: list[str] = field(default_factory=list)
    subs1: list[str] = field(default_factory=list)
    energy0: list[str] = field(default_factory=list)
    energy1: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def load_replay(path: str | Path) -> dict:
    """Load a replay from ``.json`` or ``.json.gz``."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _first_full_frame(replay: dict) -> dict:
    """Return the first visualize frame (full-information game state)."""
    for step in replay.get("steps", []):
        for agent in step:
            vis = agent.get("visualize") if isinstance(agent, dict) else None
            if vis:
                return vis[0]["current"]
    raise ValueError("replay has no 'visualize' data (cannot recover decks)")


def extract_decks(replay: dict) -> tuple[list[int], list[int]]:
    """Both players' full 60-card decklists (card ids) from the opening frame."""
    cur = _first_full_frame(replay)
    decks = []
    for p in cur["players"]:
        decks.append([c["id"] for c in p["deck"]])
    return decks[0], decks[1]


def winner_index(replay: dict) -> int | None:
    rewards = replay.get("rewards") or []
    # Kaggle marks a failed/unfinished seat with ``null`` (for example
    # ``[1, null]``). That is not a comparable match result, so leave it
    # unlabelled just like a draw rather than letting collection crash.
    if len(rewards) != 2 or None in rewards or rewards[0] == rewards[1]:
        return None
    return 0 if rewards[0] > rewards[1] else 1


def parse_replay(
    path: str | Path,
    *,
    band: str | None = None,
    sampled_team: str | None = None,
    sampled_rating: float | None = None,
    sampled_sub_date: str | None = None,
    sampled_episodes: int | None = None,
    created_at: str | None = None,
    end_time: str | None = None,
    cards: dict | None = None,
) -> EpisodeRecord:
    replay = load_replay(path)
    info = replay.get("info", {})
    teams = info.get("TeamNames") or [a.get("Name", "?") for a in info.get("Agents", [{}, {}])]
    d0, d1 = extract_decks(replay)
    a0: Archetype = classify(d0, cards)
    a1: Archetype = classify(d1, cards)

    sampled_index = teams.index(sampled_team) if sampled_team in teams else None

    return EpisodeRecord(
        episode_id=int(info.get("EpisodeId", 0)),
        band=band,
        created_at=created_at,
        end_time=end_time,
        team0=teams[0], team1=teams[1],
        winner_index=winner_index(replay),
        sampled_index=sampled_index,
        sampled_rating=sampled_rating,
        sampled_sub_date=sampled_sub_date,
        sampled_episodes=sampled_episodes,
        deck0=d0, deck1=d1,
        arch0=a0.name, arch1=a1.name,
        mains0=a0.main_lines, mains1=a1.main_lines,
        subs0=a0.sub_lines, subs1=a1.sub_lines,
        energy0=a0.energy, energy1=a1.energy,
    )
