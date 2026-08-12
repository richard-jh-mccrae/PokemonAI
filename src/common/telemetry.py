"""Decision Telemetry: serialise a Pilot Decision to a tagged stderr line (ADR-0019).

One `@T <json>` record per decision, captured in the match log's `stderr` and parsed back by
`collect`. Legacy pilots use :func:`to_record`; Bellman-enabled pilots use :func:`to_native_record`
so they never emit synthetic score/OptionTrace fields from the retired strategic stack.
"""
from __future__ import annotations

import json
import sys

TAG = "@T"


def _wire_value(value):
    """Return the JSON-stable shape ``emit`` writes, while keeping ``to_record`` pure.

    Composer diagnostics contain tuples for immutable in-memory counters (notably per-depth
    statistics).  A telemetry record is already a wire object, so exposing those tuples here made
    ``to_record(decision)`` differ from the very record ``emit(decision)`` writes and collectors
    read back.
    """
    if isinstance(value, dict):
        return {key: _wire_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire_value(item) for item in value]
    return value


def _opt_record(o) -> dict:
    """One option's wire record. `deferred` = an attack-last held-back turn-ender; `needy` = the
    win-condition-Line attach preferred among EQUAL-score attaches. Both sparse."""
    rec = {"i": o.index, "cid": o.card_id, "score": round(o.score, 3),
           "tac": round(o.tactical, 3), "fired": [[h.id, w] for h, w in o.fired]}
    if getattr(o, "deferred", False):
        rec["deferred"] = True
    if getattr(o, "attach_to_needy_line", False):
        rec["needy"] = True
    # `hs_relief` RETIRED (ADR-0102): the hand-size relief now arrives inside `tac`
    return rec


def to_native_record(decision, *, tier: int = 0) -> dict | None:
    """Compact telemetry for a Bellman-enabled pilot; no legacy score/planner fields."""
    bellman = getattr(decision, "bellman", None)
    if bellman is not None:
        return {
            "schema": "bellman",
            "tier": tier,
            "chosen": list(decision.chosen),
            **_wire_value(bellman),
        }
    if not decision.options:                       # deck-submission handshake
        return None
    # Set-Up remains engine-owned rather than Bellman-searched, but it still uses the native wire
    # envelope. Its old per-option scores are implementation debris, not useful planner evidence.
    return {"schema": "setup", "tier": tier, "chosen": list(decision.chosen)}


def to_record(decision, *, tier: int = 0) -> dict | None:
    """The telemetry record for one Decision, or None for the no-option deck-submission step."""
    opts = decision.options
    if not opts:
        return None
    scores = sorted((o.score for o in opts), reverse=True)
    margin = round(scores[0] - scores[1], 3) if len(scores) > 1 else 0.0
    line = getattr(decision, "planned", None)     # the Turn Planner's committed line (ADR-0031/0037)
    # One in-memory type, two wire keys (ADR-0037): a goal=="win" line serialises under the historical
    # `lethal` key, any other goal under `planned`.
    lethal = line if (line is not None and line.goal == "win") else None
    planned = line if (line is not None and line.goal != "win") else None
    rec = {
        "plan": opts[0].plan.value,
        "tier": tier,
        "chosen": list(decision.chosen),
        "opts": [_opt_record(o) for o in opts],
        # always present: None when no guaranteed win locked. `verified` is the engine backstop's
        # verdict on the lock (True / None) — never False, since a refuted candidate is dropped.
        "lethal": ({"step": list(lethal.next_step), "kind": lethal.kind, "why": lethal.rationale,
                    "verified": getattr(lethal, "verified", None)}
                   if lethal else None),
        # Turn Planner's committed heuristic line rides alongside — always present (None when the
        # Planner didn't commit), so a Correction can filter on it the same way (ADR-0031).
        "planned": ({"step": list(planned.next_step), "goal": planned.goal, "why": planned.rationale,
                     "value": round(planned.value, 3), "kind": planned.kind}
                    if planned else None),
        "margin": margin,
    }
    ranked = getattr(planned, "ranked_by", None) if planned else None
    if ranked is not None:                        # sparse: how the committed heuristic line was VALUED
        rec["planned"]["ranked"] = ranked         # ("composer" since POC-T4/5; the retired runtime
        rec["planned"]["diverged"] = bool(getattr(planned, "diverged", False))   # rollout's "engine" is
                                                  # gone). `diverged` is now always False for pool lines.
    composer = getattr(decision, "composer", None)
    if composer is not None:                      # sparse: margin telemetry, run stats and coverage-gap
        rec["composer"] = _wire_value(composer)   # reasons — emitted whenever the composer RAN, INCLUDING
                                                  # when it declined; a decline's reason is worth reading
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
    attach_working = getattr(decision, "attach_working", None)  # the ENERGY-ATTACH DECIDER's legible
    if attach_working:                            # working (ADR-0069 §9): the per-option AXES rows —
        rec["attach_working"] = attach_working    # attack_axis/channels/gates + the tactical each scored
    gamble = getattr(decision, "gamble", None)    # the gamble rung's full working (ADR-0039): outs
    if gamble:                                    # sought, pool, per-option p·EV, det baseline — or
        rec["gamble"] = gamble                    # the stand-down reason. Sparse: only when it ran.
    return rec


def emit(decision, *, tier: int = 0, out=None) -> None:
    """Write one `@T <json>` line to stderr for this decision (no-ops the deck-submission step)."""
    rec = to_record(decision, tier=tier)
    if rec is not None:
        print(f"{TAG} " + json.dumps(rec, separators=(",", ":")),
              file=out or sys.stderr, flush=True)


def emit_native(decision, *, tier: int = 0, out=None) -> None:
    """Write Bellman/setup telemetry without the legacy Pilot record shape."""
    rec = to_native_record(decision, tier=tier)
    if rec is not None:
        print(f"{TAG} " + json.dumps(rec, separators=(",", ":")),
              file=out or sys.stderr, flush=True)
