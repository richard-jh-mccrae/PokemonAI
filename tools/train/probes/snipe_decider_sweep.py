"""Snipe Relevance sweep — the per-leg DIAGNOSTIC for Issue #188 (ADR-0085). **Not a gate.**

Replays every committed `DAMAGE(15)` correction through a FRESH shipped Pilot per frame (the
`needs_sweep` / `threat_sweep` discipline — stateful pilots, one per frame) and reports, per frame,
what the shipped agent picks, whether that satisfies the corpus ruling, and — under `--legs` — the
`snipe_relevance` term breakdown that produced it. The breakdown is the reason this file still
exists: it is the diagnosis `decider_lab.py` deliberately does not duplicate.

Two frames are RECORDED MISSES and must stay missing (ADR-0085 decision 7): `81905522-75` (the
two-identical-Riolu transposition the design doc's own risk R3 says not to chase) and `82749168-38`
(a `refuted` label). A run that "fixes" either has almost certainly overfitted — the scorer's shape
was selected against these same 19 frames.

Both are now read from the **Ruling Index** (`gates.ruling_index`, ADR-0088 decision 5) rather
than a private ``RECORDED_MISSES`` dict that lived here. That constant was a *fourth store* for
rulings, sitting in a probe where no gate could see it, with free-text values and no disposition
vocabulary — and it is exactly why `81905522-75` was triaged *"never reviewed"* while `82749168-38`,
carrying the same ADR-0085 ruling, was triaged as ruled. The frames themselves now come through
`gates.keyed_corrections`, THE Corpus Reader, so this probe no longer carries the raw-JSONL walk
(and its silent 40-record loss) that ADR-0087 named.

    python tools/train/probes/snipe_decider_sweep.py            # the per-frame reading
    python tools/train/probes/snipe_decider_sweep.py --legs     # ...plus the per-leg breakdown

Offline and read-only. Always exits 0: it reports, it does not gate.

## Why the OFF arm is GONE (ADR-0085 Amendment J, 2026-07-30)

This file used to read every frame TWICE — once with `snipe_relevance` forced OFF, once ON — and
classify the difference `FIX` / `REGRESSION` / `NEUTRAL`. ADR-0072 called that pairing the **Decision
Gate**, and at the swap it was exactly right: OFF *was* the incumbent rung pile, so the diff measured
the new equation against what it replaced.

It stopped being right the moment that pile was DELETED, as tracker directive 1 requires. With the
six additive target rungs gone, OFF is a near-empty scorer whose argmax falls to option index, so the
comparison became "the equation versus nothing" and could only ever report FIX — measured at
**12 FIX, 0 REGRESSION**. Amendment I replaced the gate (it is now
`tools/train/decider_lab.py diff --baseline data/decider_lab/baseline.json`, which diffs against a
RECORDED capture) and left the arm here as a known-dead limb. Amendment J removes it, because a
number that cannot come out any other way is not evidence, and leaving it printed invites someone to
read `12 FIX` as merit.

What is left is the ONE reading that means something: the shipped agent, against the human. The
switch is no longer forced in either direction — `common/runtime.py` is the single deployment
PROFILE (`snipe_relevance: True`, armed 2026-07-30), so this reads what actually ships.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

# One predicate and one corpus, shared with the gate — this probe and the Decision Gate must not form
# two ideas of what a record is, which is the whole of ADR-0087.
from train.gates import (keyed_corrections, ruling_index,  # noqa: E402
                         satisfies_human, voided_frames)

DAMAGE = 15


def _frames():
    """Every replayable `DAMAGE(15)` Correction, paired with its **Frame Key**.

    `gates.keyed_corrections` — THE Corpus Reader (ADR-0087 decision 1). This used to be a private
    raw-JSONL glob with a hand-built ``<ep>-<frame>`` key, which is short the same 40 records every
    other raw reader is and cannot join the **Ruling Index** at all."""
    def keep(c):
        return (bool(c.obs and c.agent)
                and ((c.obs or {}).get("select") or {}).get("context") == DAMAGE)

    return sorted(keyed_corrections(REPO / "data" / "corrections", predicate=keep),
                  key=lambda kc: kc[0])


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _decide(tune, rec):
    """A FRESH pilot per frame — the Pilot is stateful (deck tracker, per-decision caches), so a
    reused one leaks a previous frame's board. The kill-switch is not touched: `common/runtime.py`
    resolves the shipped PROFILE, and reading anything else would report an agent nobody runs."""
    pilot = tune._build_pilot(rec.agent)[0]
    try:
        return pilot.explain(rec.obs).chosen, None
    except Exception as e:                       # a frame the shipped pilot cannot replay
        return None, f"{type(e).__name__}: {e}"


def _legs(tune, rec):
    """Per-option leg breakdown for the shipped reading — the diagnosis half, and the reason this
    probe outlived the gate it used to be."""
    pilot = tune._build_pilot(rec.agent)[0]
    obs, select = rec.obs, rec.obs["select"]
    board = pilot._board(obs, select)
    out = []
    for oi, o in enumerate(select.get("option") or []):
        ctx = pilot._context(obs, select, board, o)
        got = pilot._snipe_relevance_terms(obs, select, board, o, ctx)
        body = pilot._option_pokemon(obs, select, o) or {}
        out.append((oi, body.get("id"), got))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legs", action="store_true", help="print the per-leg breakdown per frame")
    args = ap.parse_args(argv)
    tune = _tune()
    # The recorded misses are RULINGS, so they are read from the one store that holds rulings.
    voided = voided_frames(ruling_index(REPO / "data" / "corrections"))
    frames = _frames()

    agree, miss, unlabelled, unreplayable = [], [], [], []
    print(f"{'frame':<26} {'agent':<14} {'human':<7} {'shipped':<9} reading")
    for key, rec in frames:
        human = rec.correct
        chosen, err = _decide(tune, rec)
        if err:
            unreplayable.append((key, err))
            print(f"{key:<26} {rec.agent:<14} UNREPLAYABLE {err}")
            continue
        if human is None:
            unlabelled.append((key, chosen))
            reading = "unlabelled"
        elif satisfies_human(chosen, human):
            agree.append((key, chosen))
            reading = "agrees"
        else:
            miss.append((key, chosen))
            reading = "MISSES"
        print(f"{key:<26} {rec.agent:<14} {str(human):<7} {str(chosen):<9} {reading}")
        if args.legs:
            for oi, cid, got in _legs(tune, rec):
                if got:
                    print(f"      opt{oi} card{cid:<5} rel={got['relevance']:.4f} "
                          f"plan={got['their_plan']:.3f} route={got['my_route']:.3f} "
                          f"[imm {got['imminence']:.3f} fwd {got['forward']:.3f} "
                          f"forced {got['forced']:.3f} | ko{got['ko_delta']:.2f} "
                          f"reach{got['reach']:.2f} share{got['share']:.2f}]")

    labelled = len(agree) + len(miss)
    total = labelled + len(unlabelled)
    print(f"\n{'=' * 78}\nDIAGNOSTIC — {total} DAMAGE frames through the shipped agent")
    print(f"  agrees         {len(agree)}/{labelled}")
    print(f"  MISSES         {len(miss)}      {[m[0] for m in miss]}")
    print(f"  unlabelled     {len(unlabelled)}      {[u[0] for u in unlabelled]}")
    if unreplayable:
        print(f"  unreplayable   {len(unreplayable)}")

    # The recorded misses, reported explicitly in BOTH directions — the overfitting signal survives
    # the constant's retirement; only where the ruling is READ FROM changed.
    recorded = {k: r for k, r in voided.items() if k in dict(frames)}
    print("\nRECORDED MISSES (Ruling Index — these must STAY missing):")
    for key, ruling in sorted(recorded.items()):
        rec = dict(frames)[key]
        chosen, _e = _decide(tune, rec)
        state = ("!! NOW PASSING — suspect overfitting" if satisfies_human(chosen, rec.correct)
                 else "still missing (expected)")
        print(f"  {key:<26} {state}   ({ruling.disposition}: {ruling.reason})")
    if not recorded:
        print("  (none — no DAMAGE frame carries a voided ruling)")

    unexplained = [m for m in miss if m[0] not in recorded]
    print(f"\nThis probe REPORTS, it does not gate — the Decision Gate is "
          f"`decider_lab.py diff --baseline data/decider_lab/baseline.json` (ADR-0085 Amendment I). "
          f"{len(agree)}/{labelled} agree, {len(unexplained)} miss without a recorded reason.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
