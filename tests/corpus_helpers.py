"""The ONE way a test reaches `data/corrections/` — `gates.keyed_corrections`, THE Corpus Reader.

ADR-0087 made a Corpus Reader construct `Correction` objects and DERIVE every Frame Key; ADR-0089
found that contract enforced over `tools/` only. Eleven near-identical private loaders became this
one, so there is exactly one place a corpus-reading defect can live.

A caller that wants a real key takes it from `gates.correction_frame_key`; nothing here may
hand-assemble one. Seat is NOT always 0, which is precisely the defect ADR-0087 measured.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from train.gates import keyed_corrections

REPO = Path(__file__).resolve().parents[1]

#: Agents with a directory under `src/agents/`. Mirrors `tools/train/probes/_corpus._REPLAYABLE`;
#: the two cannot share a definition, because `tests/` is not importable from `tools/`.
_REPLAYABLE = frozenset({"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"})


@lru_cache(maxsize=1)
def corpus_index() -> dict:
    """`{(episode_id, frame): Correction}`, cached for the session. **The dict is shared and must be
    treated as read-only** — a caller that mutates it corrupts every later test in the session."""
    return {(str(c.episode_id), (c.decision or {}).get("frame")): c
            for _key, c in keyed_corrections(REPO / "data" / "corrections")
            if c.obs and c.agent}


def corpus_record(episode, frame):
    """The one Correction at `(episode, frame)`, or `AssertionError`. Raising rather than skipping:
    a missing record means the corpus moved under a test that still claims to cover it."""
    rec = corpus_index().get((str(episode), frame))
    assert rec is not None, f"correction {episode}-{frame} not found in data/corrections/"
    return rec


def corpus_records(pairs):
    """`[Correction]` for an iterable of `(episode, frame)` pairs, in the order given."""
    return [corpus_record(ep, fr) for ep, fr in pairs]


def replay_agent(correction) -> str:
    """The agent directory to replay a Correction through: the corpus holds records for agents with
    no directory of their own, so an unknown agent replays through `mega_starmie`."""
    agent = getattr(correction, "agent", None) or ""
    return agent if agent in _REPLAYABLE else "mega_starmie"


def opponent_active_ids(expectation) -> set[int]:
    ids = set()
    for outcome in expectation.classes:
        current = outcome.model.source_obs.get("current") or {}
        players = current.get("players") or []
        my_index = int(current.get("yourIndex") or 0)
        their_index = 1 - my_index
        theirs = players[their_index] if 0 <= their_index < len(players) else {}
        ids.update(body.get("id") for body in (theirs.get("active") or []) if body)
    return ids
