"""The Correction record -- the curated unit of learning (ADR-0009). See `tools/train/CONTEXT.md`.

``state`` is embedded as a self-contained snapshot so the record survives replay deletion
(ADR-0002 amendment); ``correct`` names the better option at the FIRST divergent Decision.

**Scope** (ADR-0049) says how many Decisions the record is about — one (``decision``) or a ply
(``turn``). Off ``decision`` scope the record is keyed by its Scope's ``subject``, ``correct`` is
optional, and the ``span`` of covered Decisions rides along.

At ``decision`` scope ``correct`` is mandatory with ONE exception (Issue #229): empty on a PROVABLY
optional select (``minCount == 0``) is a recorded DECLINE. Unprovable means refused.
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
SCOPES = ("decision", "turn")                    # what the Correction is *about* (ADR-0049)

CRITICAL_MARKER = "CRITICAL"                     # uppercase token in rationale = must-fix-first
_CRITICAL_RE = re.compile(rf"\b{CRITICAL_MARKER}\b")


def is_critical(rationale: str | None) -> bool:
    """True when ``rationale`` carries the uppercase ``CRITICAL`` token — case-SENSITIVE, so
    lowercase prose like 'a critical attack' is not a marker."""
    return bool(rationale) and _CRITICAL_RE.search(rationale) is not None


def subject_of(scope: str, decision: dict) -> int | None:
    """What a Correction of ``scope`` is about — the identity it is keyed by (ADR-0049).
    ``decision`` → the Anchor's ``frame``; ``turn`` → its ``turn`` number."""
    if scope == "decision":
        return decision.get("frame")
    if scope == "turn":
        return decision.get("turn")
    return None


def select_min_count(obs: dict | None) -> int | None:
    """The Anchor select's ``minCount``, else ``None`` = UNKNOWN, never collapsed to 0 — this is a
    write, so it fails CLOSED (unlike `gates.records_a_decline_it_cannot_state`, which fails open)."""
    value = ((obs or {}).get("select") or {}).get("minCount")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def identity_key(correction) -> tuple:
    """What makes two Corrections the SAME blunder: the Scope's subject, never the Anchor frame."""
    return (correction.episode_id, correction.seat, correction.scope, correction.subject)


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
    #: OPTIONAL option-index lists the human ruled EQUALLY correct where `correct` over-specifies
    #: (ADR-0086). `correct` is untouched, so only a reader that knows about these widens its verdict.
    correct_alternatives: list | None = None
    alternatives_ruled: str = ""     # ISO date the alternatives were ruled
    alternatives_why: str = ""       # the ruling, verbatim
    provenance: str = "human"   # who TAGGED this: "human" | "machine" (ADR-0053 WP3). Orthogonal to
                                # `source` (whose GAME). On an identity_key collision, human wins.
    obs: dict | None = None     # agent observation (int-enum) so Tuner can replay Pilot
    agent_build: str | None = None  # submission-folder stem of build that played (traceability)
    built_at: str | None = None     # that build's timestamp (ISO), parsed from stem
    live_trace: dict | None = None  # live Decision Telemetry this game emitted (ADR-0019), incl.
                                    # `posture` — who the agent thought it faced (ADR-0041)
    posture_mismatch: bool = False  # human judged the Read/Posture WRONG here (ADR-0041): tie it to
                                    # that archetype's Brief, not to a generic weight.
    # --- Scope (ADR-0049) ---
    scope: str = "decision"         # decision (one Decision) | turn (one ply)
    subject: int | None = None      # THE identity, not `frame`: the Anchor frame (decision scope) or
                                    # the turn number (turn scope).
    span: list[dict] | None = None  # the Decisions the Scope covers; turn scope carries per-Decision
                                    # obs + live_trace so it is re-drivable.
    turn_plan: dict | None = None   # turn scope: the human's ideal-line note, {intended_line,
                                    # expected_end_board}. Sparse — None off turn-plan tags.

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
        scope = data.setdefault("scope", "decision")   # pre-ADR-0049 records are decision-scoped
        if "subject" not in data:                      # ... and their subject is the Anchor frame,
            data["subject"] = subject_of(scope, data.get("decision") or {})   # so identity is unchanged
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
    provenance: str = "human",
    chosen_label: str = "",
    correct_label: str = "",
    obs: dict | None = None,
    agent_build: str | None = None,
    built_at: str | None = None,
    live_trace: dict | None = None,
    posture_mismatch: bool = False,
    scope: str = "decision",
    span: list[dict] | None = None,
    turn_plan: dict | None = None,
) -> Correction:
    """Validate and assemble a Correction from a tagged Decision (the **Anchor**). Raises ValueError
    on an unknown source/scope/category, or a ``correct`` violating the Scope's contract (ADR-0049)."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}, got {scope!r}")
    if not is_valid_category(category):
        raise ValueError(f"unknown category {category!r}")

    # Resolved ONCE, and the same value is stored below: validating against the Anchor's own `obs`
    # while storing an override would admit a record on evidence it does not carry.
    obs = obs if obs is not None else getattr(decision, "obs", None)
    n_options = len(decision.options)
    if not correct:                          # turn scope may simply stay silent; decision must PROVE
        if scope == "decision" and select_min_count(obs) != 0:
            raise ValueError(
                f"correct {correct!r} must index legal options 0..{n_options - 1} — an empty "
                "`correct` is a DECLINE, recordable at decision scope only on a select whose "
                "obs proves it OPTIONAL (minCount 0)")
    else:                                    # named: Anchor-indexed at both decision and turn scope
        if any(not isinstance(i, int) or i < 0 or i >= n_options for i in correct):
            raise ValueError(f"correct {correct!r} must index legal options 0..{n_options - 1}")
        if scope == "turn" and set(correct) == set(decision.chosen):
            raise ValueError(f"correct {correct!r} is what was chosen — a turn-scope prescription "
                             "must name the first DIVERGENT option at the Anchor")

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
        provenance=provenance,
        obs=obs,                            # already resolved above — validated and stored are ONE
        agent_build=agent_build,
        built_at=built_at,
        live_trace=live_trace,
        posture_mismatch=bool(posture_mismatch),
        scope=scope,
        subject=subject_of(scope, decision.snapshot()),
        span=span,
        turn_plan=turn_plan,
    )
