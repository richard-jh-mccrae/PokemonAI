"""The ONE way a probe reaches `data/corrections/` — `gates.keyed_corrections`, THE Corpus Reader.

Kept separate from `tests/corpus_helpers.py` rather than shared: `tests/` is not importable from
`tools/`, so a probe importing out of the test tree would invert the dependency.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: Agents with a directory under `src/agents/`. An unknown agent replays through `mega_starmie`.
_REPLAYABLE = frozenset({"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"})


def frames():
    """`[((episode_id, frame), Correction)]` for every Correction with a replayable `obs`, by display id."""
    from train.gates import keyed_corrections

    index = {(str(c.episode_id), (c.decision or {}).get("frame")): c
             for _key, c in keyed_corrections(REPO / "data" / "corrections")
             if c.obs and c.agent}
    return sorted(index.items())


def replay_agent(correction) -> str:
    """The agent directory to replay through. The fallback is real: one `SkiChu` record has no directory."""
    agent = getattr(correction, "agent", None) or ""
    return agent if agent in _REPLAYABLE else "mega_starmie"
