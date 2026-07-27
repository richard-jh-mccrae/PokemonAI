"""FAMINE decider sweep — the Decision Gate for #142 (Phase 1d), on the ADR-0069 §8 protocol.

The sibling of ``promote_retreat_decider_sweep.py`` / ``attach_decider_sweep.py``, same contract:
replay every recorded Correction through BOTH premises while both still exist, and report every
frame where the agent's decision moves, so the human rules the flips in ONE sitting BEFORE the
deletion commit retires the old premise for good.

The two pilots, built fresh per frame (pilots are stateful — sharing one pollutes verdicts, and a
Pilot's ADR-0033 transient tracker is match-scoped while these frames are different matches):

  * **NEW** — ``famine_via_oracle`` ON. **Famine** is ``not reachable_attach(active)`` over the full
    Attach Budget, OR ``attack_blocked`` (Asleep / Paralyzed / first player on turn 1). That is the
    shipped agent.
  * **OLD** — ``famine_via_oracle`` OFF. The retired pair: an UNTYPED count of attached Energy plus
    the best hand attach against ``minAttackCost``, and the flat ``+1`` accel approximation. This
    arm exists only to be compared against; nothing ships reading it.

Why the whole decision and not one lane: the famine premise is not confined to a lane. It feeds the
stall-gust family (PLAY options), `dont-play-damage-boost-when-cant-attack` (a sequencing PLAY), and
mega_lucario's two Lunar-Cycle rules (an ABILITY). A lane comparison would be blind to two thirds of
what the swap touches, which is exactly why the gust corpus alone was ruled insufficient. So the
comparison is the CHOSEN SET, graded against the Correction's recorded ``correct`` — the Decision
Claim shape (ADR-0072).

**One known infidelity, stated rather than hidden.** The OLD arm reproduces the retired PREMISE, and
`gust-for-the-stall`'s guard is re-expressed so ``not active_should_swing`` is byte-identical to the
two clauses it replaced. `gust-to-strand-the-key-attacker` cannot be reproduced that way — it carried
the accel half ALONE, with no famine premise at all — so its new guard shows up here as a flip. That
is the ruling this phase made, surfacing as it should, not an artefact of the harness.

    python tools/train/probes/famine_decider_sweep.py           # the flip table + the tally
    python tools/train/probes/famine_decider_sweep.py --all     # every frame, not only the flips
    python tools/train/probes/famine_decider_sweep.py --quiet   # one line + the gate verdict

Offline and read-only; two engine-backed Pilot builds per frame. Non-zero exit when the Decision
Gate fails (an unruled REGRESSION).
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import (decision_gate_verdict, frame_key_of,  # noqa: E402
                         held_out_frames, print_gate_report)

_AGENTS = {"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"}


def _names() -> dict:
    out = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0].isdigit():
                out.setdefault(int(r[0]), r[1])
    return out


def _frames():
    index = {}
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return [(k, v) for k, v in sorted(index.items()) if v.get("obs") and v.get("agent")]


def _frame_key(rec, ep, fr) -> str:
    """The Correction's `identity_key` — the SAME shape the Leaf Lab and the Held-out Ledger use, so
    one ruling holds a frame out of either gate."""
    scope = rec.get("scope") or "decision"
    subject = rec.get("subject")
    if subject is None:
        subject = fr if scope == "decision" else (rec.get("decision") or {}).get("turn")
    return frame_key_of(ep, rec.get("seat"), scope, subject)


def _agent(rec) -> str:
    a = rec.get("agent") or ""
    return a if a in _AGENTS else "mega_starmie"


def _strategy_and_deck(agent: str):
    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60]
            if x.strip()]
    return mod.STRATEGY, deck


def _pilot(agent: str, *, new: bool, seams):
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    params = dict(strategy.params)
    params["famine_via_oracle"] = bool(new)
    return build_pilot(strategy, deck, params=params, **seams)


def _seams():
    """Engine-backed knowledge seams built ONCE and injected into every Pilot — immutable card
    knowledge, so sharing them is safe where sharing a Pilot is not."""
    from common.scouting.artifact import load_artifact
    from common.scouting.briefs import load_briefs
    from common.scouting.provider import EngineCardStatProvider
    from common.scouting.scout import Scout
    stats = EngineCardStatProvider()
    stats.warm()
    return {"stats": stats, "scout": Scout(load_artifact(), provider=stats),
            "briefs": load_briefs()}


def _budget_line(pilot, label: str) -> str:
    """The realised Attach Budget behind this arm's answer.

    A flip is unrulable without it: "the agent stopped stalling" says nothing, while "the Budget
    holds {R},{P} over two options, so Phantom Dive is reachable" is a ruling. Read through
    ``Budget.size`` and the option palette, never ``len(option)`` — options retain units that may
    not be jointly realisable (ADR-0067)."""
    model = getattr(pilot, "_state_model", None)
    if model is None or model.mine.active is None:
        return f"      {label}: (no Active)"
    budget = model.mine.attach_budget(model.mine.active)
    palette = sorted({t for option in budget.options for u in option for t in (u.types or {None})},
                     key=lambda x: (x is None, x))
    return (f"      {label}: budget.size={budget.size} options={len(budget.options)} "
            f"types={palette} famine={model.mine.active_famine} "
            f"blocked={model.mine.attack_blocked}")


def _cell(chosen) -> str:
    return ",".join(str(i) for i in sorted(chosen or [])) or "(none)"


def sweep(show_all: bool, quiet: bool = False) -> int:
    names, frames, seams = _names(), _frames(), _seams()
    hdr = (f"{'id':<14} {'agent':<13} {'NEW':<10} {'OLD':<10} {'correct':<10} {'verdict':<12}")
    if not quiet:
        print("FAMINE DECIDER SWEEP — new (Reachable Attach + attack_blocked) "
              "vs old (untyped count + flat +1 accel)\n")
        print(hdr)
        print("-" * len(hdr))
    tally = defaultdict(int)
    flips, graded = [], []
    for (ep, fr), rec in frames:
        agent = _agent(rec)
        try:
            p_new = _pilot(agent, new=True, seams=seams)
            p_old = _pilot(agent, new=False, seams=seams)
            dec_new, dec_old = p_new.explain(rec["obs"]), p_old.explain(rec["obs"])
        except Exception as exc:                       # a frame the shipped build cannot replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} ERROR {exc}")
            continue
        new_v, old_v = set(dec_new.chosen or []), set(dec_old.chosen or [])
        correct = set(rec.get("correct") or [])
        labelled = bool(correct)
        agree = new_v == old_v
        tally["frames"] += 1
        if agree:
            tally["agree"] += 1
            if not show_all:
                continue
            verdict = "agree"
        else:
            tally["flip"] += 1
            if labelled:
                new_hit, old_hit = new_v == correct, old_v == correct
                verdict = ("FIX" if new_hit and not old_hit
                           else "REGRESSION" if old_hit and not new_hit else "DIVERGENT")
            else:
                verdict = "unlabelled"
            tally[verdict] += 1
            graded.append({"key": _frame_key(rec, ep, fr), "verdict": verdict,
                           "label": rec.get("correct_label") or ""})
        if not quiet:
            print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {_cell(new_v):<10} "
                  f"{_cell(old_v):<10} {_cell(correct) if labelled else '(none)':<10} "
                  f"{verdict:<12}")
        if not agree:
            flips.append((ep, fr))
            if not quiet:
                lbl = rec.get("correct_label") or ""
                if lbl:
                    print(f"      correct_label: {lbl}")
                print(_budget_line(p_new, "NEW"))
                print(_budget_line(p_old, "OLD"))
                for tag, dec, chosen in (("NEW", dec_new, new_v), ("OLD", dec_old, old_v)):
                    for i in sorted(chosen):
                        if i < len(dec.options):
                            trace = dec.options[i]
                            fired = ",".join(h.id for h, _ in trace.fired) or "(no rule)"
                            body = names.get(trace.card_id, trace.card_id)
                            print(f"      {tag} [{i}] {str(body)[:24]:<24} "
                                  f"score={trace.score} {fired}")
    held_out = held_out_frames()
    passed = decision_gate_verdict(graded, held_out=held_out)
    keys = ("frames", "agree", "flip", "FIX", "REGRESSION", "DIVERGENT", "unlabelled")
    if quiet:
        print(" ".join(f"{k}={tally[k]}" for k in keys) +
              f" gate={'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    print("\nTALLY")
    for k in keys + ("error",):
        print(f"  {k:<16} {tally[k]}")
    print(f"\n{len(flips)} frame(s) need a user ruling before the deletion commit: "
          f"{', '.join(f'{e}-{f}' for e, f in flips) or '(none)'}")

    # DECISION GATE (ADR-0072 decision 2): zero unruled REGRESSION. Held-out frames still RUN and
    # still REPORT — a re-ruling is a state the gate READS, never prose in a review doc.
    regressions = [g for g in graded if g["verdict"] == "REGRESSION"]
    ok = print_gate_report(
        "DECISION GATE (famine premise)",
        gating=[g for g in regressions if g["key"] not in held_out],
        ruled=[g for g in regressions if g["key"] in held_out],
        held_out=held_out, total=tally["frames"],
        rule="zero unruled REGRESSION frames",
        line=lambda g: f"  {g['key']:<34} {g['verdict']:<12} {g['label'][:60]}")
    return 0 if (passed and ok) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="print every frame, not only the flips")
    ap.add_argument("--quiet", action="store_true", help="one summary line and the gate verdict")
    args = ap.parse_args()
    return sweep(args.all, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
