"""Snipe Relevance decider sweep — ADR-0072's **Decision Gate** for Issue #188 (ADR-0083).

Replays every committed `DAMAGE(15)` correction through a FRESH shipped Pilot per frame (the
`needs_sweep` / `threat_sweep` discipline — stateful pilots, one per frame) twice: once as shipped
(`snipe_relevance` OFF, the six additive target rungs deciding) and once with the switch forced ON
(the graded scalar deciding). Every change is classified rather than counted:

    FIX          the repoint moves the pick TOWARD the corpus ruling
    REGRESSION   it moves AWAY from a ruled pick            <- the only class that gates
    NEUTRAL      both readings miss, differently
    unlabelled   the frame carries no `correct`

That framing is ADR-0078 Amendment C's, and it exists because the naive version measures the wrong
thing: several corpus rulings are owned by the KO rung or the Turn Planner rather than by the
instrument under test, so reporting *any* behaviour change as a failure counts frames the swap does
not own. A change toward the human is a FIX, not a regression.

Two frames are RECORDED MISSES and must stay missing (ADR-0083 decision 7): `81905522-75` (the
two-identical-Riolu transposition the design doc's own risk R3 says not to chase) and `82749168-38`
(a `refuted` label). A run that "fixes" either has almost certainly overfitted — the scorer's shape
was selected against these same 19 frames, so the sweep is a **sanity floor, not the merit gate**.
The merit gates are the Discrimination Gate (`leaf_lab.py diff`) and the paired-A/B Tripwire.

    python tools/train/probes/snipe_decider_sweep.py            # the sweep + verdict
    python tools/train/probes/snipe_decider_sweep.py --legs     # ...plus the per-leg breakdown

Offline and read-only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

DAMAGE = 15

#: Frames ADR-0083 decision 7 records as PERMANENT misses, with the reason. Reported separately so a
#: run that starts passing them is visible as the overfitting signal it is, rather than as progress.
RECORDED_MISSES = {
    "81905522-75": "transposition — two identical Riolu, no board signal splits them (design-doc R3)",
    "82749168-38": "refuted label — the correction itself is wrong (reviewed.json)",
}


def _frames():
    index = {}
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return [(f"{k[0]}-{k[1]}", v) for k, v in sorted(index.items())
            if v.get("obs") and v.get("agent")
            and ((v.get("obs") or {}).get("select") or {}).get("context") == DAMAGE]


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _decide(tune, rec, *, armed: bool):
    """A fresh pilot per reading, so no cache or stashed board leaks between the two."""
    pilot = tune._build_pilot(rec["agent"])[0]
    pilot.snipe_relevance = armed
    try:
        return pilot.explain(rec["obs"]).chosen, pilot, None
    except Exception as e:                       # a frame the shipped pilot cannot replay
        return None, pilot, f"{type(e).__name__}: {e}"


def _legs(tune, rec):
    """Per-option leg breakdown for the armed reading — the diagnosis half."""
    pilot = tune._build_pilot(rec["agent"])[0]
    pilot.snipe_relevance = True
    obs, select = rec["obs"], rec["obs"]["select"]
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

    fixes, regressions, neutral, unlabelled, unreplayable = [], [], [], [], []
    same = 0
    print(f"{'frame':<16} {'agent':<14} {'human':<7} {'OFF':<7} {'ON':<7} verdict")
    for key, rec in _frames():
        human = rec.get("correct")
        off, _p, err_off = _decide(tune, rec, armed=False)
        on, _p2, err_on = _decide(tune, rec, armed=True)
        if err_off or err_on:
            unreplayable.append((key, err_off or err_on))
            print(f"{key:<16} {rec['agent']:<14} UNREPLAYABLE {err_off or err_on}")
            continue
        if off == on:
            same += 1
            verdict = "same"
        elif human is None:
            unlabelled.append((key, off, on))
            verdict = "CHANGED (unlabelled)"
        elif on == human:
            fixes.append((key, off, on))
            verdict = "FIX"
        elif off == human:
            regressions.append((key, off, on))
            verdict = "REGRESSION"
        else:
            neutral.append((key, off, on))
            verdict = "neutral (both miss)"
        print(f"{key:<16} {rec['agent']:<14} {str(human):<7} {str(off):<7} {str(on):<7} {verdict}")
        if args.legs:
            for oi, cid, got in _legs(tune, rec):
                if got:
                    print(f"      opt{oi} card{cid:<5} rel={got['relevance']:.4f} "
                          f"plan={got['their_plan']:.3f} route={got['my_route']:.3f} "
                          f"[imm {got['imminence']:.3f} fwd {got['forward']:.3f} "
                          f"forced {got['forced']:.3f} | ko{got['ko_delta']:.2f} "
                          f"reach{got['reach']:.2f} share{got['share']:.2f}]")

    total = same + len(fixes) + len(regressions) + len(neutral) + len(unlabelled)
    print(f"\n{'=' * 78}\nDECISION GATE — {total} DAMAGE frames, shipped vs `snipe_relevance` armed")
    print(f"  unchanged      {same}")
    print(f"  FIX            {len(fixes)}      {[f[0] for f in fixes]}")
    print(f"  REGRESSION     {len(regressions)}      {[f[0] for f in regressions]}")
    print(f"  neutral        {len(neutral)}      {[f[0] for f in neutral]}")
    print(f"  unlabelled     {len(unlabelled)}      {[f[0] for f in unlabelled]}")
    if unreplayable:
        print(f"  unreplayable   {len(unreplayable)}")

    # The recorded misses, reported explicitly in BOTH directions.
    print("\nRECORDED MISSES (ADR-0083 decision 7 — these must STAY missing):")
    for key, why in RECORDED_MISSES.items():
        rec = dict(_frames()).get(key)
        if rec is None:
            print(f"  {key:<16} not in corpus")
            continue
        on, _p, _e = _decide(tune, rec, armed=True)
        state = "still missing (expected)" if on != rec.get("correct") else "!! NOW PASSING — suspect overfitting"
        print(f"  {key:<16} {state}   ({why})")

    gated = [r for r in regressions if r[0] not in RECORDED_MISSES]
    print(f"\nVERDICT — Decision Gate: {'PASS' if not gated else 'FAIL'}. "
          f"{len(fixes)} FIX, {len(gated)} unruled REGRESSION, {len(neutral)} neutral.")
    if gated:
        print("  Every unruled REGRESSION must be ruled with the user BEFORE the deletion commit "
              "(ADR-0069 §8, promoted to a gate by ADR-0072).")
        for key, off, on in gated:
            print(f"    REGRESSION {key}: shipped {off} -> armed {on}")
    return 1 if gated else 0


if __name__ == "__main__":
    raise SystemExit(main())
