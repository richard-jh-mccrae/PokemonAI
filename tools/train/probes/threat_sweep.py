"""Threat-Clock unification shadow sweeps (opponent-value-equation-unification.md).

Replays every committed correction through a FRESH shipped Pilot per frame (stateful pilots — one
per frame, the needs_sweep discipline) and reports the three Threat-Clock shadows, DECIDING NOTHING:

  * DOOM     (S1b, `threat_shadow`) — incumbent `active_doomed` vs the `incoming(t=1)`-curve
    re-expression + the agree bit. Disagreements are the adjudication input for the survival swap;
    the split names WHICH direction (curve less/more pessimistic than the worst-case incumbent).
    Post-swap (`doom_matched_relax`, 2026-07-23) the report adds the CHARGED read (`chg`), whether
    the matched relax was consulted (`dec`), and the LIVE decided bit (`final`) — rows print on an
    old-vs-curve disagreement OR a final-vs-worst-case flip (the relax-only behavior changes).
  * RECUR    (S2, `recur_shadow`) — per opponent refueler body, how much the discard fuel moves the
    clock (turns_to_afford) and the incoming to my Active.
  * TARGET   (S3a, `opp_target_shadow`) — the two-term removal value per opponent body (prize +
    phase × survival), the Option-B currency, for eyeballing vs the shipped snipe/gust/deny pick.
SLOTS and RANK were DELETED by Issue #243 (ADR-TEMP-243 decision 1), for opposite reasons:

  * SLOTS was **same-vs-same**. It compared a shipped pilot it described as "both new flags OFF,
    today's default" against `_forced(gust_target_slots=True)` / `_forced(recur_fuel_relax=True)` —
    but the PROFILE has shipped BOTH ON since 2026-07-27 (`runtime.py`, ADR-0076 / Issue #186). So
    both arms were the same pilot and it reported 0 flips BY CONSTRUCTION: a green light with the
    bulb removed. `sweep_rank`, in the same file, forced both sides explicitly and its docstring
    said exactly why ("so it stays an A/B after the PROFILE ships the flag ON") — the mistake was
    made next to its own correction.
  * RANK was ANSWERED. ADR-0083 records 0 decided-pick flips over 331 frames, and the substance is
    covered by `tests/strategy/test_scaled_rank_corpus.py`, which exercises the read on every real
    frame the corpus contains. A ruling is a ruling; carrying it as a probe mode too is the fourth
    Probe Fate this repo keeps having to delete.

    python tools/train/probes/threat_sweep.py            # all three
    python tools/train/probes/threat_sweep.py --doom     # doom only
    python tools/train/probes/threat_sweep.py --recur
    python tools/train/probes/threat_sweep.py --target

Offline and read-only.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def _frames():
    """THE Corpus Reader, via the shared probe helper (ADR-0087 / ADR-TEMP-243)."""
    from train.probes._corpus import frames
    return frames()


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _decide(tune, rec):
    try:
        return tune._build_pilot(rec.agent)[0].explain(rec.obs)
    except Exception as e:                       # a frame the shipped pilot can't replay — skip, note
        return e


def sweep_doom(tune, frames) -> None:
    print(f"{'id':<16} {'agent':<14} {'old':<6} {'curve':<6} {'inc':>5} {'hp':>5} "
          f"{'chg':>5} {'dec':<5} {'final':<6} agree")
    total = agree = old_only = new_only = decided = flipped = 0
    for (ep, fr), rec in frames:
        d = _decide(tune, rec)
        s = getattr(d, "threat_shadow", None) if not isinstance(d, Exception) else None
        if not s:
            continue
        total += 1
        agree += s["agree"]
        old_only += s["doom_old"] and not s["doom_curve"]
        new_only += s["doom_curve"] and not s["doom_old"]
        decided += bool(s.get("decided"))
        flip = s.get("doom_final", s["doom_old"]) != s["doom_old"]
        flipped += flip
        if not s["agree"] or flip:
            chg = s.get("doom_charged")
            print(f"{ep + '-' + str(fr):<16} {rec.agent:<14} {str(s['doom_old']):<6} "
                  f"{str(s['doom_curve']):<6} {s['doom_incoming']:>5} {s['my_hp']:>5} "
                  f"{'-' if chg is None else chg:>5} {str(bool(s.get('decided'))):<5} "
                  f"{str(s.get('doom_final', s['doom_old'])):<6} "
                  f"{'AGREE' if s['agree'] else 'DISAGREE'}{' FLIP' if flip else ''}")
    print(f"\nDOOM: agree {agree}/{total}  |  disagree {total - agree} "
          f"(incumbent-doomed-only={old_only} [curve LESS pessimistic — the affordability gate], "
          f"curve-doomed-only={new_only})  |  matched-relax decided on {decided}, "
          f"final flipped vs worst-case on {flipped}\n")


def sweep_recur(tune, frames) -> None:
    fired = accel = 0
    for (ep, fr), rec in frames:
        d = _decide(tune, rec)
        s = getattr(d, "recur_shadow", None) if not isinstance(d, Exception) else None
        if not s:
            continue
        fired += 1
        for b in s["bodies"]:
            moved = b["ttr_fuel"] < b["ttr_plain"] or b.get("inc_fuel", 0) > b.get("inc_plain", 0)
            accel += bool(moved)
            print(f"{ep + '-' + str(fr):<16} {rec.agent:<14} body {b['id']:<6} fuel {b['fuel']} "
                  f"ttr {b['ttr_plain']}->{b['ttr_fuel']}  inc {b.get('inc_plain')}->{b.get('inc_fuel')}")
    print(f"\nRECUR: frames-with-refueler={fired}  body-reads-where-fuel-moved-the-clock={accel}\n")


def sweep_target(tune, frames) -> None:
    fired = 0
    for (ep, fr), rec in frames:
        d = _decide(tune, rec)
        s = getattr(d, "opp_target_shadow", None) if not isinstance(d, Exception) else None
        if not s:
            continue
        fired += 1
        top = max(s["bodies"], key=lambda b: b["value"])
        print(f"{ep + '-' + str(fr):<16} {rec.agent:<14} phase {s['phase']:<5} "
              f"top-removal id={top['id']} value={top['value']} "
              f"(prize={top['prize']} surv_shift={top['survival_shift']})  "
              f"bodies={len(s['bodies'])}")
    print(f"\nTARGET: frames-with-opp-bodies={fired}\n")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Threat-Clock shadow sweeps over the corrections corpus")
    ap.add_argument("--doom", action="store_true")
    ap.add_argument("--recur", action="store_true")
    ap.add_argument("--target", action="store_true")
    args = ap.parse_args(argv)
    run_all = not (args.doom or args.recur or args.target)
    tune, frames = _tune(), _frames()
    if args.doom or run_all:
        sweep_doom(tune, frames)
    if args.recur or run_all:
        sweep_recur(tune, frames)
    if args.target or run_all:
        sweep_target(tune, frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
