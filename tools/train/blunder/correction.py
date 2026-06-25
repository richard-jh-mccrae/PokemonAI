"""The Correction record -- the curated unit of learning (ADR-0009).

A Correction is ``(state, chosen, correct, attribution, rationale)`` plus identity.
``state`` is embedded as a self-contained snapshot of the Decision so the record
survives replay deletion (ADR-0002 amendment). ``correct`` is the better legal
option at the *first divergent* Decision (Tier-1; the rest of the line goes in
``rationale``). See ``tools/train/CONTEXT.md``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .categories import is_valid_category
from .decisions import Decision

SOURCES = ("own", "peer")


@dataclass(frozen=True)
class Correction:
    # identity / provenance
    source: str                 # "own" (our submission) | "peer" (another team's game of our deck)
    episode_id: int | None
    seat: int                   # whose Decision this is
    agent: str                  # deck build (own) / archetype label (peer)
    submission_id: int | None   # own ladder games only; None for local self-play
    agent_version: str | None   # build id (e.g. git short-sha) -- timeline key for non-ladder games
    episode_time: str | None    # when the match was played
    tagged_at: str              # when this Correction was authored (ISO)
    # the decision -- embedded, self-contained snapshot (state)
    decision: dict              # frame, turn, select_context, select_type, options, current
    # judgment
    chosen: list[int]           # positional indices into options (auto from replay)
    chosen_label: str
    correct: list[int]          # the better legal option positions (mandatory)
    correct_label: str
    category: str               # closed human vocab (mandatory)
    attribution: str | None     # learning-surface link (optional in v1)
    rationale: str              # free prose

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Correction":
        return cls(**data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_correction(
    decision: Decision,
    *,
    source: str,
    agent: str,
    correct: list[int],
    category: str,
    rationale: str,
    submission_id: int | None = None,
    agent_version: str | None = None,
    episode_time: str | None = None,
    tagged_at: str | None = None,
    attribution: str | None = None,
    chosen_label: str = "",
    correct_label: str = "",
) -> Correction:
    """Validate and assemble a Correction from a tagged Decision.

    Raises ValueError if ``source`` is unknown, ``category`` is not in the closed
    vocabulary, or ``correct`` is not a set of legal option positions distinct
    from ``chosen``.
    """
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
    if not is_valid_category(category):
        raise ValueError(f"unknown category {category!r}")

    n_options = len(decision.options)
    if not correct or any(not isinstance(i, int) or i < 0 or i >= n_options for i in correct):
        raise ValueError(f"correct {correct!r} must index legal options 0..{n_options - 1}")
    if list(correct) == list(decision.chosen):
        raise ValueError("correct must differ from chosen (otherwise it is not a blunder)")

    return Correction(
        source=source,
        episode_id=decision.episode_id,
        seat=decision.seat,
        agent=agent,
        submission_id=submission_id,
        agent_version=agent_version,
        episode_time=episode_time,
        tagged_at=tagged_at or _now_iso(),
        decision=decision.snapshot(),
        chosen=list(decision.chosen),
        chosen_label=chosen_label,
        correct=list(correct),
        correct_label=correct_label,
        category=category,
        attribution=attribution,
        rationale=rationale,
    )
