"""The Correction record -- the curated unit of learning (ADR-0009).

A Correction is ``(state, chosen, correct, attribution, rationale)`` plus identity.
``state`` is embedded as a self-contained snapshot of the Decision so the record
survives replay deletion (ADR-0002 amendment). ``correct`` is the better legal
option at the *first divergent* Decision (Tier-1; the rest of the line goes in
``rationale``). See ``tools/train/CONTEXT.md``.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .categories import is_valid_category
from .decisions import Decision

SOURCES = ("own", "peer")

CRITICAL_MARKER = "CRITICAL"                     # uppercase token in rationale = must-fix-first
_CRITICAL_RE = re.compile(rf"\b{CRITICAL_MARKER}\b")


def is_critical(rationale: str | None) -> bool:
    """True when ``rationale`` carries the uppercase ``CRITICAL`` token (word-boundary, case-
    sensitive — so lowercase prose like 'a critical attack' is NOT a marker). The human writes it
    at tag time to flag a blunder that ``/blunder-buster`` must resolve before any other work."""
    return bool(rationale) and _CRITICAL_RE.search(rationale) is not None


def _derive_id(data: dict) -> str:
    """Stable id for a legacy record saved before ids existed (deterministic)."""
    dec = data.get("decision") or {}
    key = f"{data.get('episode_id')}|{dec.get('frame')}|{data.get('seat')}|{data.get('tagged_at')}|{data.get('category')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Correction:
    id: str                     # unique id (edit/remove in review list)
    # identity / provenance
    source: str                 # "own" (our submission) | "peer" (other team's game w/ our deck)
    episode_id: int | None
    seat: int                   # whose Decision this is
    agent: str                  # deck build (own) / archetype label (peer)
    submission_id: int | None   # own ladder games only; None for local self-play
    agent_version: str | None   # build id (e.g. git short-sha) -- timeline key for non-ladder games
    episode_time: str | None    # when match was played
    tagged_at: str              # when this Correction was authored (ISO)
    # the decision -- embedded, self-contained snapshot (state)
    decision: dict              # frame, turn, select_context, select_type, options, current
    # judgment
    chosen: list[int]           # positional indices into options (auto from replay)
    chosen_label: str
    correct: list[int]          # better legal option positions (mandatory)
    correct_label: str
    category: str               # closed human vocab (mandatory)
    attribution: str | None     # learning-surface link (derived by Tuner; ADR-0017)
    rationale: str              # free prose
    obs: dict | None = None     # agent observation (int-enum) so Tuner can replay Pilot
    agent_build: str | None = None  # submission-folder stem of build that played (traceability)
    built_at: str | None = None     # that build's timestamp (ISO), parsed from stem
    live_trace: dict | None = None  # live @T Decision Telemetry record this game emitted (ADR-0019),
                                    # incl. `posture` — who the agent thought it faced (ADR-0041)
    posture_mismatch: bool = False  # human judged the agent's opponent Read/Posture WRONG here
                                    # (ADR-0041): a matchup-doctrine miss to tie to that archetype's
                                    # Brief / recognition, not a generic weight. The believed archetype
                                    # lives in `live_trace["posture"]`; the intended line in `rationale`.

    @property
    def is_critical(self) -> bool:
        """Human flagged this blunder must-fix-first (uppercase CRITICAL in the rationale)."""
        return is_critical(self.rationale)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Correction":
        data = dict(data)
        if not data.get("id"):                 # backfill ids for pre-id records
            data["id"] = _derive_id(data)
        if not data.get("agent") and data.get("agent_build"):
            from .provenance import parse_build_stem   # agent_build is authoritative for deck played
            data["agent"] = parse_build_stem(data["agent_build"]).get("agent") or data.get("agent", "")
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
    obs: dict | None = None,
    agent_build: str | None = None,
    built_at: str | None = None,
    live_trace: dict | None = None,
    posture_mismatch: bool = False,
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

    return Correction(
        id=uuid.uuid4().hex[:12],
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
        obs=obs if obs is not None else getattr(decision, "obs", None),
        agent_build=agent_build,
        built_at=built_at,
        live_trace=live_trace,
        posture_mismatch=bool(posture_mismatch),
    )
