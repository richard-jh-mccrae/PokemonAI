"""Snipe Relevance sweep — the per-leg DIAGNOSTIC for Issue #188 (ADR-0085). **Not a gate.**

Replays every committed `DAMAGE(15)` correction through a FRESH shipped Pilot per frame and reports
what the agent picks, whether it satisfies the corpus ruling, and — under `--legs` — the
`snipe_relevance` term breakdown. That breakdown is the diagnosis `decider_lab.py` does not
duplicate, and the reason this probe outlived the gate it used to be (ADR-0085 Amendment J).

Recorded misses come from the **Ruling Index** (ADR-0088 decision 5), never a private dict here, and
the frames from `gates.keyed_corrections` (ADR-0087). A run that "fixes" a recorded miss has almost
certainly overfitted — the scorer's shape was selected against these same frames.

    python tools/train/probes/snipe_decider_sweep.py            # the per-frame reading
    python tools/train/probes/snipe_decider_sweep.py --legs     # ...plus the per-leg breakdown

Offline and read-only. Always exits 0: it reports, it does not gate.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

# One predicate and one corpus, shared with the gate: two ideas of what a record is is ADR-0087.
from train.gates import (keyed_corrections, ruling_index,  # noqa: E402
                         satisfies_human, voided_frames)

DAMAGE = 15


def _frames():
    """Through `gates.keyed_corrections`, THE Corpus Reader (ADR-0087 decision 1): a private key
    cannot join the Ruling Index at all."""
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
    """A FRESH pilot per frame — the Pilot is stateful, so a reused one leaks the previous frame's
    board. The kill-switch is untouched: anything but the shipped PROFILE reports an agent nobody runs."""
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
