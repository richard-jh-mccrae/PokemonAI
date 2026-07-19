"""Decision Telemetry: serialise a Pilot Decision to a tagged stderr line (ADR-0019).

The agent emits one tagged record per decision; the grader captures it in the match log's
`stderr`, and `collect` parses it back. Pure + tiny: `to_record` is testable without I/O,
`emit` does the one print. Tag is greppable so non-telemetry stderr is ignored.

Carries the Turn Planner / Lethal Solver verdicts (`planned` / `lethal`) and the Scouting
**posture** (ADR-0041) — what the Read believed about the opponent (archetype candidates, γ,
matched Brief) — so every blunder Correction's `live_trace` records how the agent decided AND who
it thought it was facing. The posture block ties a matchup misplay to a specific archetype.

It also carries the **decide()-only reorder markers** — sparse flags that say when `chosen` did NOT
come from a plain argmax over the emitted `score`s, so a trace reader (`/blunder-buster`, the
inspector) doesn't misread "top-score not chosen" as a scoring bug: per-opt `deferred` (an attack-last
held-back turn-ender, `_finish_turn_last`) / `needy` (the win-condition-Line attach preferred among
EQUAL-score attaches), and top-level `reordered` (attack-last resequenced the menu) / `grabbed` (the
multi-pick came from `_greedy_grab`'s dynamic gap-scoring). All sparse → an un-reordered record stays
byte-identical to the pre-marker era.
"""
from __future__ import annotations

import json
import sys

TAG = "@T"


def _opt_record(o) -> dict:
    """One option's wire record. The decide()-only markers ride only when set, so a plain-argmax
    option stays byte-identical to the pre-marker era — they tell the reader WHY the chosen option
    isn't the top-`score` one: `deferred` = an attack-last held-back turn-ender (`_finish_turn_last`);
    `needy` = the win-condition-Line attach preferred among EQUAL-score attaches (`attach_to_needy_line`)."""
    rec = {"i": o.index, "cid": o.card_id, "score": round(o.score, 3),
           "tac": round(o.tactical, 3), "fired": [[h.id, w] for h, w in o.fired]}
    if getattr(o, "deferred", False):
        rec["deferred"] = True
    if getattr(o, "attach_to_needy_line", False):
        rec["needy"] = True
    if getattr(o, "hand_size_relief", 0.0):        # REPORTING-ONLY hand-size-attacker relief (grill
        rec["hs_relief"] = round(o.hand_size_relief, 1)   # 2026-07-19); signed, never in `score`
    return rec


def to_record(decision, *, tier: int = 0) -> dict | None:
    """The telemetry record for one Decision, or None for the no-option deck-submission step."""
    opts = decision.options
    if not opts:
        return None
    scores = sorted((o.score for o in opts), reverse=True)
    margin = round(scores[0] - scores[1], 3) if len(scores) > 1 else 0.0
    line = getattr(decision, "planned", None)     # the Turn Planner's committed line (ADR-0031/0037)
    # One in-memory type, two wire keys (ADR-0037): a goal=="win" line IS the Lethal Solver's lock
    # and serialises under the historical `lethal` key; any other goal under `planned`. The wire
    # format is byte-identical to the two-field era, so tune/propose/retest and every historical
    # correction's live_trace keep reading unchanged.
    lethal = line if (line is not None and line.goal == "win") else None
    planned = line if (line is not None and line.goal != "win") else None
    rec = {
        "plan": opts[0].plan.value,
        "tier": tier,
        "chosen": list(decision.chosen),
        "opts": [_opt_record(o) for o in opts],
        # Lethal Solver's verdict rides here so a blunder Correction's live_trace carries it (the
        # SAME record feeds the tuner retest) — always present: None when no guaranteed win locked.
        # `verified` = the engine backstop's verdict on the lock (True / None; `lethal_verify`).
        "lethal": ({"step": list(lethal.next_step), "kind": lethal.kind, "why": lethal.rationale,
                    "verified": getattr(lethal, "verified", None)}
                   if lethal else None),
        # Turn Planner's committed heuristic line rides alongside — always present (None when the
        # Planner didn't commit), so a Correction can filter on it the same way (ADR-0031).
        "planned": ({"step": list(planned.next_step), "goal": planned.goal, "why": planned.rationale}
                    if planned else None),
        "margin": margin,
    }
    ranked = getattr(planned, "ranked_by", None) if planned else None
    if ranked is not None:                        # sparse: only when multi-candidate engine ranking
        rec["planned"]["ranked"] = ranked         # ran (`planner_engine_rank`) — how the committed
        rec["planned"]["diverged"] = bool(getattr(planned, "diverged", False))   # line was valued +
                                                  # whether it beat the closed-form pick (A/B signal)
    if planned is not None and planned.goal == "develop":     # develop-rung Phase 1: the pick turns on
        rec["planned"]["value"] = round(planned.value, 3)     # this leaf value — a correction that
                                                  # disagrees is a claim about the LEAF, unreadable without
                                                  # it. Keyed on goal=="develop" so other planned records
                                                  # stay byte-identical.
    plan_candidates = getattr(decision, "plan_candidates", None)
    if plan_candidates is not None:               # sparse: the develop rung's ranked end-boards (top-K,
        rec["plan_candidates"] = plan_candidates  # sorted desc, committed/greedy flagged) — free to emit
                                                  # (the rung already valued every candidate to pick)
    objectives = getattr(decision, "objectives", None)
    if objectives is not None:                    # sparse: the Tier-3 match-objective read (ADR-0040)
        rec["objectives"] = objectives            # — race delta + both cheapest-path turns
    game_plan = getattr(decision, "game_plan", None)
    if game_plan is not None:                     # sparse: the Match Planner's Game Plan (ADR-0045) —
        rec["game_plan"] = game_plan              # mode + confidence + directed goal, blunder-buster-parseable
    win_prob = getattr(decision, "win_prob", None)
    if win_prob is not None:                      # sparse: the Automatic Value Model's P(win) (ADR-0042) —
        rec["win_prob"] = win_prob                # calibration + legibility (None when the model is off)
    refuted = getattr(decision, "lethal_refuted", 0)
    if refuted:                                   # sparse: only when the engine denied a closed-form
        rec["lethal_refuted"] = refuted           # "win" (the lethal_verify divergence signal)
    if getattr(decision, "lethal_lost", False):   # sparse: a locked verified line diverged from the
        rec["lethal_lost"] = True                 # live game and was dropped (`lethal_veto`, ADR-0037)
    if getattr(decision, "reordered", False):     # sparse: `chosen` came from the attack-last
        rec["reordered"] = True                   # resequencer, not argmax(score) — so a reader doesn't
                                                  # misread "top-score not chosen" as a scoring bug
    if getattr(decision, "grabbed", False):       # sparse: `chosen` is a `_greedy_grab` set (dynamic
        rec["grabbed"] = True                     # gap-scoring), not the top-N static scores
    posture = getattr(decision, "posture", None)  # the Read's belief about the opponent at this
    if posture:                                   # decision (ADR-0041): believed archetype(s), γ,
        rec["posture"] = posture                  # matched Brief. Sparse: only when a Scout was wired.
    gamble = getattr(decision, "gamble", None)    # the gamble rung's full working (ADR-0039): outs
    if gamble:                                    # sought, pool, per-option p·EV, det baseline — or
        rec["gamble"] = gamble                    # the stand-down reason. Sparse: only when the rung
    return rec                                    # ran; the blunder shell renders it as a dropdown.                                     # Rides into every Correction's live_trace so the
                                                  # inspector shows it + /blunder-buster ties it to a matchup.


def emit(decision, *, tier: int = 0, out=None) -> None:
    """Write one `@T <json>` line to stderr for this decision (no-ops the deck-submission step)."""
    rec = to_record(decision, tier=tier)
    if rec is not None:
        print(f"{TAG} " + json.dumps(rec, separators=(",", ":")),
              file=out or sys.stderr, flush=True)
