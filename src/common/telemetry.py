"""Decision Telemetry: serialise a Pilot Decision to a tagged stderr line (ADR-0019).

The agent emits one tagged record per decision; the grader captures it in the match log's
`stderr`, and `collect` parses it back. Pure + tiny: `to_record` is testable without I/O,
`emit` does the one print. Tag is greppable so non-telemetry stderr is ignored.
"""
from __future__ import annotations

import json
import sys

TAG = "@T"


def to_record(decision, *, tier: int = 0) -> dict | None:
    """The telemetry record for one Decision, or None for the no-option deck-submission step."""
    opts = decision.options
    if not opts:
        return None
    scores = sorted((o.score for o in opts), reverse=True)
    margin = round(scores[0] - scores[1], 3) if len(scores) > 1 else 0.0
    lethal = getattr(decision, "lethal", None)   # Lethal Solver's verdict (ADR-0030), or None
    planned = getattr(decision, "planned", None)  # Turn Planner's committed line (ADR-0031), or None
    return {
        "plan": opts[0].plan.value,
        "tier": tier,
        "chosen": list(decision.chosen),
        "opts": [
            {"i": o.index, "cid": o.card_id, "score": round(o.score, 3),
             "tac": round(o.tactical, 3), "fired": [[h.id, w] for h, w in o.fired]}
            for o in opts
        ],
        # Lethal Solver's verdict rides here so a blunder Correction's live_trace carries it (the
        # SAME record feeds the tuner retest) — always present: None when no guaranteed win locked.
        "lethal": ({"step": list(lethal.next_step), "kind": lethal.kind, "why": lethal.rationale}
                   if lethal else None),
        # Turn Planner's committed line rides alongside lethal verdict — always present (None
        # when Planner didn't commit), so a Correction can filter on it the same way (ADR-0031).
        "planned": ({"step": list(planned.next_step), "goal": planned.goal, "why": planned.rationale}
                    if planned else None),
        "margin": margin,
    }


def emit(decision, *, tier: int = 0, out=None) -> None:
    """Write one `@T <json>` line to stderr for this decision (no-ops the deck-submission step)."""
    rec = to_record(decision, tier=tier)
    if rec is not None:
        print(f"{TAG} " + json.dumps(rec, separators=(",", ":")),
              file=out or sys.stderr, flush=True)
