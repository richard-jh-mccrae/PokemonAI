"""The ONE way a test reaches `data/corrections/` — `gates.keyed_corrections`, THE Corpus Reader.

**ADR-0087** (Issue #241) made a Corpus Reader *construct* `Correction` objects and *derive* every
**Frame Key**. **ADR-TEMP-243** (Issue #243) found that contract was enforced over `tools/` only, and
by a regex that matched `glob(` — so eleven files under `tests/strategy/` reached the corpus anyway:
nine globbing it (one carrying the identical `d.get("obs") and d.get("agent")` filter, short the same
**40** records) and two naming a build directory outright, which is worse — a renamed build dir
breaks it silently, and no glob pattern can see it.

This module is the fix's other half. Eleven near-identical private loaders became one, so there is
exactly one place a corpus-reading defect can live, which is the whole point of the contract.

**Why the Frame Key is discarded here.** Ten of the eleven callers look up hardcoded
`(episode, frame)` literals and have no use for a key. They still come through
`keyed_corrections` rather than the lower `store.load_corrections` seam — permitted by the contract —
because the failure being closed is *many slightly-different ideas of what the corpus is*, and the
lower seam preserves two idioms at exactly the layer where they diverge. A caller that later wants a
real key takes it from `gates.correction_frame_key`; nothing here may hand-assemble one. Seat is
**not** always 0 (the corpus is 201/171), which is precisely the defect ADR-0087 measured.

Indexing by `(episode_id, decision.frame)` is faithful to what every converted caller did: measured
2026-07-31, all **372** committed records carry a unique `(episode_id, frame)` pair, so first-wins
and last-wins agree and `load_corrections`' dedup makes the index strictly safer than the raw walks
it replaces (those appended per matching line and would double-count a duplicate).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from train.gates import keyed_corrections

REPO = Path(__file__).resolve().parents[1]

#: Agents with a directory under `src/agents/`. Mirrors `tools/train/probes/_corpus._REPLAYABLE`;
#: the two cannot share a definition because `tests/` is not importable from `tools/`, and a probe
#: reaching into the test tree to borrow it would invert the dependency.
_REPLAYABLE = frozenset({"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"})


@lru_cache(maxsize=1)
def corpus_index() -> dict:
    """`{(episode_id, frame): Correction}` for every committed Correction carrying a replayable
    `obs` and an `agent`.

    Cached for the session: `keyed_corrections` walks and constructs the whole corpus, and eleven
    test modules asking independently would pay for it eleven times. **The dict is shared and must be
    treated as read-only** — a caller that mutates it corrupts every later test in the session.
    """
    return {(str(c.episode_id), (c.decision or {}).get("frame")): c
            for _key, c in keyed_corrections(REPO / "data" / "corrections")
            if c.obs and c.agent}


def corpus_record(episode, frame):
    """The one Correction at `(episode, frame)`, or `AssertionError`.

    Raising rather than skipping is deliberate: every caller names a literal frame it asserts real
    behaviour about, so a missing record means the corpus moved under a test that still claims to
    cover it — which must go red, not quietly green. `test_needs_deny_resolver` previously skipped
    here, and a skip that can never be noticed is the same false-clean shape ADR-TEMP-243 exists to
    remove.
    """
    rec = corpus_index().get((str(episode), frame))
    assert rec is not None, f"correction {episode}-{frame} not found in data/corrections/"
    return rec


def corpus_records(pairs):
    """`[Correction]` for an iterable of `(episode, frame)` pairs, in the order given."""
    return [corpus_record(ep, fr) for ep, fr in pairs]


def replay_agent(correction) -> str:
    """The agent directory to replay a Correction through.

    `Correction.from_dict` backfills `agent` from `agent_build`, so the "record predates the agent
    field" workarounds the raw walkers carried are gone. One real fallback survives and is NOT
    cosmetic: the corpus holds a `SkiChu` record (measured 2026-07-31 — 247 mega_starmie, 70
    mega_lucario, 54 dragapult_ex, 1 SkiChu) with no agent directory of its own, so an unknown agent
    replays through `mega_starmie` exactly as the private `_agent` helpers did.
    """
    agent = getattr(correction, "agent", None) or ""
    return agent if agent in _REPLAYABLE else "mega_starmie"
