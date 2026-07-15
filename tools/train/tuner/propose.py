"""Propose a new Hypothesis from a `missing_hypothesis` Correction (ADR-0017).

Assisted, *not* automatic: the proposal carries the human rationale, a seed weight in the
normal band (docs/weights.md), and a human-readable trigger *sketch*. A human writes the
executable ``when()`` and commits it to the deck/general Strategy.

A **scoped** Correction (turn/match, ADR-0049) also lands here — it is an *open blunder* for
``/blunder-buster`` to route, not a proposed Hypothesis: it never became a ranking constraint, and
its fix lives in ``planner.py`` / ``objectives.py``, so it carries ``seed_weight = 0``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from train.blunder.correction import is_critical
from train.blunder.reviewed import review_key

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
    critical: bool = False    # rationale carries CRITICAL marker (resolve first; /blunder-buster gate)
    # Live-trace layer flags: pick was driven by a scoring-short-circuit layer -> no weight/when()
    # can fix it; fix lives in planner.py / lethal.py. /blunder-buster routes on these (ADR-0030/0031).
    planner_committed: bool = False   # live_trace.planned non-null (Turn Planner committed a line)
    lethal_locked: bool = False       # live_trace.lethal non-null (Lethal Solver locked a win)
    plan_candidates: list | None = None  # the develop rung's ranked end-boards (Phase 1) — surfaced so a
                                      # sequencing correction sits next to the alternatives it out-scored,
                                      # letting /blunder-buster separate a mis-ranked leaf from a bad pick
    # Posture (ADR-0041): a matchup-doctrine miss routes to the archetype's Brief / recognition, not a
    # generic weight. /blunder-buster surfaces these so a matchup misplay isn't authored as a when().
    posture_mismatch: bool = False    # human flagged the opponent Read WRONG at this decision
    believed_archetype: str | None = None   # who the agent thought it faced (live_trace.posture top)
    # Scope (ADR-0049): what the blunder is ABOUT. A strong routing prior for /blunder-buster (a Turn
    # blunder is prima facie planner-code) but never an auto-route — a Turn whose `planned` is null
    # throughout means the Planner never committed, and the gap is a general Hypothesis after all.
    scope: str = "decision"
    subject: object = None            # the Turn number (turn scope); None for decision/match... see `key`
    seat: object = None
    key: str = ""                     # the ledger/report id — scope-aware (`reviewed.review_key`)
    span_len: int = 0                 # Decisions (turn) / Turns (match) the Span covers
    attribution: str | None = None    # scoped only: the Anchor's fired-Hypothesis diff, as INFORMATION


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def believed_archetype(correction) -> str | None:
    """The archetype the shipped agent believed it faced at this decision — the top posture
    candidate off the live trace (ADR-0041), or None when no posture was captured (no Scout /
    pre-posture replay). Shared by ``io.write_proposals`` and ``tune.py``'s worklist tags so a
    matchup misplay carries its opponent identity."""
    cands = (((correction.live_trace or {}).get("posture") or {}).get("cands")) or []
    return cands[0][0] if cands and cands[0] else None


def _proposal_id(correction) -> str:
    """Stable per-subject id: the frame (decision), the Turn (turn), or the seat (match)."""
    slug, ep = _slug(correction.category), correction.episode_id
    if correction.scope == "turn":
        return f"{slug}-{ep}-t{correction.subject}"
    if correction.scope == "match":
        return f"{slug}-{ep}-m{correction.seat}"
    return f"{slug}-{ep}-{correction.decision.get('frame')}"


def _sketch(correction) -> str:
    """A human-readable trigger sketch. Off `decision` scope it describes the *line the agent
    played* — the thing the blunder is about — rather than a single option preference."""
    dec, span = correction.decision, correction.span or []
    if correction.scope == "turn":
        played = " -> ".join(s.get("chosen_label") or "?" for s in span)
        sketch = (f"turn {correction.subject} (seat {correction.seat}, {len(span)} decisions) "
                  f"played: {played}")
        if correction.correct:
            sketch += (f"; first divergence at frame {dec.get('frame')}: prefer "
                       f"'{correction.correct_label}' over '{correction.chosen_label}'")
        return sketch
    if correction.scope == "match":
        return (f"whole match (seat {correction.seat}, {len(span)} turns): the played line / Game "
                f"Plan was wrong — the intended line is in the rationale")
    return (f"fire at SelectContext={dec.get('select_context')!r} (turn {dec.get('turn')}) to prefer "
            f"'{correction.correct_label}' over '{correction.chosen_label}'")


def propose_hypothesis(correction, *, attribution: str | None = None) -> ProposedHypothesis:
    live = correction.live_trace or {}
    scoped = correction.scope != "decision"
    return ProposedHypothesis(
        id=_proposal_id(correction), rationale=correction.rationale or "",
        seed_weight=0.0 if scoped else _SEED_WEIGHT,   # a plan-layer fix has no weight to seed
        trigger_sketch=_sketch(correction), category=correction.category,
        episode_id=correction.episode_id, frame=correction.decision.get("frame"),
        agent_build=correction.agent_build, built_at=correction.built_at,
        critical=is_critical(correction.rationale),
        planner_committed=live.get("planned") is not None,
        lethal_locked=live.get("lethal") is not None,
        plan_candidates=live.get("plan_candidates"),

        posture_mismatch=bool(getattr(correction, "posture_mismatch", False)),
        believed_archetype=believed_archetype(correction),
        scope=correction.scope, subject=correction.subject, seat=correction.seat,
        key=review_key(correction), span_len=len(correction.span or []),
        attribution=attribution)
