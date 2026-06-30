"""Propose a new Hypothesis from a `missing_hypothesis` Correction (ADR-0017).

Assisted, *not* automatic: the proposal carries the human rationale, a seed weight in the
normal band (docs/weights.md), and a human-readable trigger *sketch*. A human writes the
executable ``when()`` and commits it to the deck/general Strategy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from train.blunder.correction import is_critical

_SEED_WEIGHT = 20.0   # normal-preference band (docs/weights.md)


@dataclass
class ProposedHypothesis:
    id: str
    rationale: str
    seed_weight: float
    trigger_sketch: str
    # source provenance (for the durable, build-traceable proposals snapshot — ADR-0018)
    category: str = ""
    episode_id: object = None
    frame: object = None
    agent_build: str | None = None
    built_at: str | None = None
    critical: bool = False    # rationale carries the CRITICAL marker (resolve first; /blunder-buster gate)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def propose_hypothesis(correction) -> ProposedHypothesis:
    dec = correction.decision
    hid = f"{_slug(correction.category)}-{correction.episode_id}-{dec.get('frame')}"
    sketch = (
        f"fire at SelectContext={dec.get('select_context')!r} (turn {dec.get('turn')}) to prefer "
        f"'{correction.correct_label}' over '{correction.chosen_label}'"
    )
    return ProposedHypothesis(
        id=hid, rationale=correction.rationale or "", seed_weight=_SEED_WEIGHT,
        trigger_sketch=sketch, category=correction.category, episode_id=correction.episode_id,
        frame=dec.get("frame"), agent_build=correction.agent_build, built_at=correction.built_at,
        critical=is_critical(correction.rationale))
