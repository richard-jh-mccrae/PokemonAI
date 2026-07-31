"""Attach decider sweep — the per-axis DIAGNOSTIC for the no-shadow swap (#139, ADR-0069 §8). **Not a gate.**

Runs the corpus through the SHIPPED attach decider and reports, per attach frame, which target it
funds, whether that satisfies the corpus ruling, and the decider's AXES BREAKDOWN behind the call.
The breakdown is why this file outlived the gate it used to be — `decider_lab.py` records the
decision, never the axes that produced it.

Comparison is by the resolved target SLOT ``(area, position)``, never the raw option index —
duplicate energy-source options and identical-effect target copies otherwise read as false flips
(82523811-59, 82750161-59).

    python tools/train/probes/attach_decider_sweep.py            # the miss table + the tally
    python tools/train/probes/attach_decider_sweep.py --all      # every frame, not only the misses
    python tools/train/probes/attach_decider_sweep.py --scale 6 --pref 3 --quiet   # retune grid

Offline and read-only; one engine-backed Pilot build per frame. Always exits 0: it reports, it does
not gate.

## Why the OLD arm is GONE (ADR-0085 Amendment J, 2026-07-30)

This probe used to build TWO pilots per frame — NEW (``attach_value`` ON, the 19 retired rungs forced
to weight 0) and OLD (``attach_value`` OFF, the pile at its shipped weights) — and classify each
disagreement `FIX` / `REGRESSION` / `DIVERGENT`. ADR-0072 called that pairing the **Decision Gate**,
and at the swap it was right: OLD *was* the incumbent pile, so the diff measured the equation against
what it replaced.

The deletion commit ended that, as tracker directive 1 requires. `baseline_energy` holds **3** of its
22 rungs now — `use-acceleration`, `prefer-active-attach-in-setup`,
`feed-the-line-for-disruptor-lock` — so OLD was ``attach_value`` OFF over a near-empty scorer whose
argmax falls to option index. All four sweeps sat in that state simultaneously and none of them said
so; a comparison that cannot produce a REGRESSION is not evidence of not regressing.

Amendment I moved the gate to `tools/train/decider_lab.py diff --baseline
data/decider_lab/baseline.json`, which diffs against a RECORDED capture. Amendment J removes the dead
arm here. What remains is the one reading that means something: the shipped agent, against the human.

The ``--scale`` / ``--pref`` retune search is UNAFFECTED and stays — it overrides shipped constants
to search the feasible region (ADR-0069's retune protocol), and this probe is the only place they are
ever poked, so a shipped constant is never quietly different from the one measured. Note `--pref`
still bites: `prefer-active-attach-in-setup` is one of the three survivors.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import (ATTACH_LANE, in_lane, lane_slots,  # noqa: E402
                         option_slot, satisfies_human)

_ATTACH, _CARD, _ATTACH_FROM = 8, 3, 21

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
    """THE Corpus Reader, via the shared probe helper (ADR-0087 / ADR-0089)."""
    from train.probes._corpus import frames
    return frames()


def _agent(rec) -> str:
    """The shared replay fallback (`_corpus.replay_agent`). It is no longer papering over a missing
    `agent` — `from_dict` backfills that from `agent_build` — but it is not cosmetic either: the
    corpus holds one `SkiChu` record with no agent directory."""
    from train.probes._corpus import replay_agent
    return replay_agent(rec)


def _strategy_and_deck(agent: str):
    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60] if x.strip()]
    return mod.STRATEGY, deck


def _pilot(agent: str, *, seams):
    """A fresh SHIPPED Pilot for ``agent`` — one per frame, because the Pilot is stateful (deck
    tracker, per-decision caches) and sharing one pollutes verdicts (the `needs_sweep` lesson).

    No params are overridden and no rungs are zeroed: `common/runtime.py` resolves the single
    deployment PROFILE, and a probe that reads anything else reports an agent nobody runs."""
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    return build_pilot(strategy, deck, **seams)


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
    hdr = f"{'id':<14} {'agent':<13} {'shipped':<18} {'correct':<12} {'reading':<12}"
    if not quiet:
        print("ATTACH DECIDER SWEEP — the shipped decider, per frame, with its axes breakdown\n")
        print(hdr)
        print("-" * len(hdr))
    tally = defaultdict(int)
    misses = []
    for (ep, fr), rec in frames:
        agent = _agent(rec)
        try:
            dec = _pilot(agent, seams=seams).explain(rec.obs)
        except Exception as exc:                       # a frame the shipped build can't replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} ERROR {exc}")
            continue
        working = dec.attach_working
        if working is None:                            # not an attach menu — outside this swap's lane
            continue
        options = rec.obs["select"]["option"]
        ctx = (rec.obs.get("select") or {}).get("context")
        correct = rec.correct
        chosen_slots = _slots(dec.chosen, options, ctx)
        correct_slots = _slots(correct or [], options, ctx)
        tally["frames"] += 1
        # A frame whose `correct` is a NON-attach play still labels this decision: the question it
        # answers is "attach at all?", and matching it means making NO energy attach. Reading only the
        # attach slots would silently score that frame "unlabelled" and hide a real miss
        # (83007714-65: the Ignition onto the doomed Cinderace before the retreat).
        if correct is None:
            tally["unlabelled"] += 1
            reading = "unlabelled"
        elif (chosen_slots == correct_slots if correct_slots
              else not chosen_slots and satisfies_human(dec.chosen, correct)):
            tally["agree"] += 1
            reading = "agrees"
            if not show_all:
                continue
        else:
            tally["MISS"] += 1
            reading = "MISSES"
            misses.append((ep, fr))
        chosen_energy = next((r["energy"] for r in working["eq"]
                              if tuple(r["slot"]) in {tuple(s) for s in chosen_slots}), None)
        if not quiet:
            print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} "
                  f"{_cell(chosen_slots, names, chosen_energy):<18} "
                  f"{_cell(correct_slots):<12} {reading:<12}")
            if reading != "agrees":
                for row in sorted(working["eq"], key=lambda r: -r["tactical"]):
                    print(_axes_line(row, names))
    if quiet:
        print(f"scale={scale} pref={pref_weight} " + " ".join(
            f"{k}={tally[k]}" for k in ("frames", "agree", "MISS", "unlabelled", "error")))
        return
    print("\nTALLY")
    for k in ("frames", "agree", "MISS", "unlabelled", "error"):
        print(f"  {k:<12} {tally[k]}")
    print(f"\n{len(misses)} frame(s) where the shipped decider misses the ruling: "
          f"{', '.join(f'{e}-{f}' for e, f in misses) or '(none)'}")
    print("\nThis probe REPORTS, it does not gate — the Decision Gate is "
          "`decider_lab.py diff --baseline data/decider_lab/baseline.json` (ADR-0085 Amendment I).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="print every frame, not only the flips")
    ap.add_argument("--scale", type=float, help="override _ATTACH_VALUE_SCALE (retune search)")
    ap.add_argument("--pref", type=float, help="override prefer-active-attach-in-setup's weight")
    ap.add_argument("--quiet", action="store_true", help="tally line only (the retune grid)")
    a = ap.parse_args()
    sweep(a.all, scale=a.scale, pref_weight=a.pref, quiet=a.quiet)
