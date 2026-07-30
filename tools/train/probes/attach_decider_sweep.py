"""Attach DECIDER sweep — the batched review's input for the no-shadow swap (#139, ADR-0069 §8).

Runs the corpus through BOTH attach deciders while both still exist and reports every frame where
they disagree, with the new decider's AXES BREAKDOWN on each side of the flip. That report is the
whole point: the swap protocol rules that no decision may flip silently, so the human rules on the
WHY — one sitting, one table — BEFORE the deletion commit retires the rung pile for good.

The two pilots, built fresh per frame (pilots are stateful; sharing one pollutes verdicts — the
`needs_sweep` lesson):

  * NEW — ``attach_value`` ON with the 19 retired ``baseline_energy`` rungs forced to weight 0.
    That is exactly the post-deletion agent: the axes-sum decider alone, plus the three structure
    survivors. Zeroing rather than deleting is what lets this run BEFORE the deletion commit.
  * OLD — ``attach_value`` OFF with every rung at its shipped weight: the pile as it decides today.

Comparison is by the resolved target SLOT ``(area, position)``, never the raw option index —
duplicate energy-source options and identical-effect target copies otherwise read as false flips
(82523811-59, 82750161-59). ``correct`` (the human label, where the frame has one) is shown on both
sides so a flip can be read as a FIX, a REGRESSION, or a no-label judgement call.

    python tools/train/probes/attach_decider_sweep.py            # the flip table + the tally
    python tools/train/probes/attach_decider_sweep.py --all      # every frame, not only the flips

Offline and read-only; ~4-8 min for the full corpus (two engine-backed Pilot builds per frame).
⚠️ **This probe is a DIAGNOSTIC, not the Decision Gate** (since ADR-0085 Amendment I, 2026-07-30).

ADR-0072 named "the phase's `*_decider_sweep.py`" as the Decision Gate, and this one compared the
shipped agent against its own kill-switch turned OFF. That was right at the swap, when OFF *was* the
incumbent rung pile. It stopped being right the moment that pile was DELETED, as tracker directive 1
requires: with no rungs left, OFF is an empty scorer whose argmax falls to option index, so the
comparison became "the equation versus nothing" and could only ever report FIX. A gate that cannot
report a REGRESSION is not a gate. All four sweeps were in this state simultaneously and none said so.

The Decision Gate is now `tools/train/decider_lab.py diff --baseline data/decider_lab/baseline.json`,
which diffs against a RECORDED capture — the property that kept the Discrimination Gate honest all
along. What remains here is still worth running: the per-leg breakdown and the per-frame
classification against the human are diagnosis this lab deliberately does not duplicate.

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

from train.gates import ATTACH_LANE, in_lane, lane_slots, option_slot   # noqa: E402

_ATTACH, _CARD, _ATTACH_FROM = 8, 3, 21

#: The 19 rungs the decider retires (ADR-0069 §7 / the issue's build addendum). Forced to 0 in the
#: NEW pilot so this probe measures the post-deletion agent without needing the deletion first.
RETIRED = (
    # the 8 folded positives
    "concentrate-energy-on-wincon", "build-active-wincon", "power-up-attacker",
    "spread-attach-to-the-needy", "concentrate-accel-on-one-line-body",
    "feed-the-firing-accelerator", "arm-the-doomed-active", "advance-the-accel-pieces",
    # the burst family -> evaporation loss + no-KO cap + resource tie-break
    "dont-waste-discard-energy", "dont-attach-discard-energy-turn1", "conserve-burst-when-no-ko",
    "conserve-discard-energy-prefer-basic", "prefer-reusable-over-burst",
    # the role guards -> the board-evaluated role gate
    "dont-fund-the-non-attacking-body", "dont-power-the-draw-engine",
    # the doom guards -> the survival gate + the evolution-escape
    "dont-feed-the-doomed", "dont-overbuild-the-doomed-wincon",
    # emergent / channel folds
    "dont-waste-off-type-energy", "fuel-the-dormant-ability",
)
#: `attach-energy-last` converts to a decide()-only ordering deferral rather than folding into a
#: term, so it is zeroed too — the NEW pilot must not carry its -5 into the score channel.
ZEROED = RETIRED + ("attach-energy-last",)

_AXES = ("attack_axis", "this_turn", "build", "accel_value", "retreat_equity", "ability_fuel",
         "evaporation_loss")


def _names() -> dict:
    out = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0].isdigit():
                out[int(r[0])] = r[1]
    return out


def _frames():
    index = {}
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return [(k, v) for k, v in sorted(index.items()) if v.get("obs") and v.get("agent")]


def _agent(rec) -> str:
    a = rec.get("agent") or ""
    return a if a in {"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"} else "mega_starmie"


def _strategy_and_deck(agent: str):
    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60] if x.strip()]
    return mod.STRATEGY, deck


def _pilot(agent: str, *, new: bool, seams):
    """A fresh shipped Pilot for ``agent`` in NEW (decider-only) or OLD (rung-only) mode."""
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    params = dict(strategy.params)
    params["attach_value"] = bool(new)
    overrides = {hid: 0 for hid in ZEROED} if new else None
    return build_pilot(strategy, deck, params=params, overrides=overrides, **seams)


def _seams():
    """Build the engine-backed knowledge seams ONCE and inject them into every Pilot — they are
    immutable card knowledge, so sharing them is safe where sharing a Pilot is not."""
    from common.scouting.artifact import load_artifact
    from common.scouting.briefs import load_briefs
    from common.scouting.provider import EngineCardStatProvider
    from common.scouting.scout import Scout
    stats = EngineCardStatProvider()
    stats.warm()
    return {"stats": stats, "scout": Scout(load_artifact(), provider=stats),
            "briefs": load_briefs()}


def _opt_slot(option: dict, ctx) -> tuple | None:
    """The target slot an attach option names. Delegates to the shared resolver so this sweep, the
    evolve sweep and an Axis Claim can never disagree about what a slot is (ADR-0072 decision 3);
    ATTACH_LANE carries this lane's rule as DATA — ATTACH always, CARD only under ATTACH_FROM."""
    if not in_lane(option, ATTACH_LANE, ctx):
        return None
    return option_slot(option)


def _slots(indices, options, ctx) -> set:
    return lane_slots(indices, options, lane=ATTACH_LANE, select_context=ctx)


def _cell(slots, names=None, energy=None) -> str:
    if not slots:
        return "(no-attach)"
    slot = sorted(slots)[0]
    nm = (names or {}).get(energy, "") if energy is not None else ""
    return f"{slot}{('+' + nm.split(' ')[0]) if nm else ''}"


def _axes_line(row, names) -> str:
    terms = " ".join(f"{k}={row[k]}" for k in _AXES if row.get(k))
    gates = " ".join(g for g in ("role_gated", "overkill", "doomed", "evaporates") if row.get(g))
    return (f"      slot={tuple(row['slot'])} energy={names.get(row['energy'], row['energy'])} "
            f"units={row['units']} marginal={row['marginal']} tactical={row['tactical']}"
            f"{('  [' + terms + ']') if terms else ''}{('  <' + gates + '>') if gates else ''}")


def sweep(show_all: bool, scale=None, pref_weight=None, quiet: bool = False) -> None:
    """``scale`` / ``pref_weight`` override the shipped constants for the retune's feasible-region
    search (the constraint-first step of ADR-0069's retune protocol) — the probe is the ONLY place
    they are ever poked, so a shipped constant is never quietly different from the one measured."""
    import common.pilot as pilot_mod
    if scale is not None:
        pilot_mod._ATTACH_VALUE_SCALE = float(scale)
    if pref_weight is not None:
        from common.strategy.baseline import baseline_energy
        for h in baseline_energy.HYPOTHESES:
            if h.id == "prefer-active-attach-in-setup":
                object.__setattr__(h, "weight", float(pref_weight))
    names, frames, seams = _names(), _frames(), _seams()
    hdr = (f"{'id':<14} {'agent':<13} {'NEW pick':<18} {'OLD pick':<18} {'correct':<12} "
           f"{'verdict':<12}")
    if not quiet:
        print("ATTACH DECIDER SWEEP — new (axes-sum, rungs zeroed) vs old (the rung pile)\n")
        print(hdr)
        print("-" * len(hdr))
    tally = defaultdict(int)
    flips = []
    for (ep, fr), rec in frames:
        agent = _agent(rec)
        try:
            dec_new = _pilot(agent, new=True, seams=seams).explain(rec["obs"])
            dec_old = _pilot(agent, new=False, seams=seams).explain(rec["obs"])
        except Exception as exc:                       # a frame the shipped build can't replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} ERROR {exc}")
            continue
        working = dec_new.attach_working
        if working is None:                            # not an attach menu — outside this swap's lane
            continue
        options = rec["obs"]["select"]["option"]
        ctx = (rec["obs"].get("select") or {}).get("context")
        correct = rec.get("correct") or []
        new_slots = _slots(dec_new.chosen, options, ctx)
        old_slots = _slots(dec_old.chosen, options, ctx)
        correct_slots = _slots(correct, options, ctx)
        agree = new_slots == old_slots
        tally["frames"] += 1
        if agree:
            tally["agree"] += 1
            if not show_all:
                continue
            verdict = "agree"
        else:
            tally["flip"] += 1
            # A frame whose `correct` is a NON-attach play still labels this decision: the question
            # it answers is "attach at all?", and matching it means making NO energy attach. Reading
            # only the attach slots would silently score that frame "unlabelled" and hide a real
            # regression (83007714-65: the Ignition onto the doomed Cinderace before the retreat).
            if correct:
                new_hit = (new_slots == correct_slots if correct_slots
                           else not new_slots and set(dec_new.chosen or []) & set(correct))
                old_hit = (old_slots == correct_slots if correct_slots
                           else not old_slots and set(dec_old.chosen or []) & set(correct))
                verdict = ("FIX" if new_hit and not old_hit
                           else "REGRESSION" if old_hit and not new_hit else "DIVERGENT")
            else:
                verdict = "unlabelled"
            tally[verdict] += 1
        new_energy = next((r["energy"] for r in working["eq"]
                           if tuple(r["slot"]) in {tuple(s) for s in new_slots}), None)
        if not quiet:
            print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {_cell(new_slots, names, new_energy):<18} "
                  f"{_cell(old_slots):<18} {_cell(correct_slots):<12} {verdict:<12}")
        if not agree:
            flips.append((ep, fr))
            if not quiet:
                for row in sorted(working["eq"], key=lambda r: -r["tactical"]):
                    print(_axes_line(row, names))
    if quiet:
        print(f"scale={scale} pref={pref_weight} " + " ".join(
            f"{k}={tally[k]}" for k in ("frames", "agree", "flip", "FIX", "REGRESSION",
                                        "DIVERGENT", "unlabelled")))
        return
    print("\nTALLY")
    for k in ("frames", "agree", "flip", "FIX", "REGRESSION", "DIVERGENT", "unlabelled", "error"):
        print(f"  {k:<12} {tally[k]}")
    print(f"\n{len(flips)} frame(s) need a user ruling before the deletion commit: "
          f"{', '.join(f'{e}-{f}' for e, f in flips) or '(none)'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="print every frame, not only the flips")
    ap.add_argument("--scale", type=float, help="override _ATTACH_VALUE_SCALE (retune search)")
    ap.add_argument("--pref", type=float, help="override prefer-active-attach-in-setup's weight")
    ap.add_argument("--quiet", action="store_true", help="tally line only (the retune grid)")
    a = ap.parse_args()
    sweep(a.all, scale=a.scale, pref_weight=a.pref, quiet=a.quiet)
