"""The ONE way a probe reaches `data/corrections/` — `gates.keyed_corrections`, THE Corpus Reader.

The sibling of `tests/corpus_helpers.py`, and it exists for the same reason that one does. Issue #243
replaced eleven near-identical private loaders under `tests/` with a single helper; the five routed
probes here had the identical `_frames()` — docstring included — plus the same hardcoded agent
fallback set. Leaving five copies would satisfy the letter of **ADR-0087** while reproducing the
failure it names: *many slightly-different ideas of what the corpus is*. Five copies is five places a
defect can live, and the one that mattered drifted for months before anyone measured it.

Kept separate from the test-side helper rather than shared: `tests/` is not importable from `tools/`
(only the reverse holds, via `conftest.py`'s path inserts), and a probe importing out of the test
tree would invert the dependency. Two files, one idiom each, both one line from `keyed_corrections`.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: Agents with a directory under `src/agents/`. An unknown agent replays through `mega_starmie`.
_REPLAYABLE = frozenset({"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"})


def frames():
    """`[((episode_id, frame), Correction)]` for every Correction carrying a replayable `obs`.

    The private raw-JSONL walk this replaced was short **40** records: a falsy `agent` is
    *recoverable* from `agent_build`, and only `Correction.from_dict` backfills it (ADR-0087,
    Issue #241). Keyed by `(episode, frame)` for the display id these probes print; the derived
    **Frame Key** is discarded rather than hand-rebuilt, which is the half of ADR-0087 that cost the
    Decision Gate 163 keys. A probe that wants a real key takes it from `gates.correction_frame_key`
    — never assembled by hand, because `seat` is not always 0 (the corpus is 201/171).
    """
    from train.gates import keyed_corrections

    index = {(str(c.episode_id), (c.decision or {}).get("frame")): c
             for _key, c in keyed_corrections(REPO / "data" / "corrections")
             if c.obs and c.agent}
    return sorted(index.items())


def replay_agent(correction) -> str:
    """The agent directory to replay a Correction through.

    `Correction.from_dict` backfills `agent` from `agent_build`, so the "record predates the agent
    field" workarounds the raw walkers carried are gone. The fallback itself is NOT cosmetic and was
    measured before being kept: the corpus holds one `SkiChu` record (2026-07-31 — 247 mega_starmie,
    70 mega_lucario, 54 dragapult_ex, 1 SkiChu) with no agent directory, so dropping it would crash
    that replay rather than tidy anything.
    """
    agent = getattr(correction, "agent", None) or ""
    return agent if agent in _REPLAYABLE else "mega_starmie"
