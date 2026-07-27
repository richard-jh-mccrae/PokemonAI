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
  * SLOTS    (S3b/S2 live, ADR-0074) — for every frame, replays the SAME decision through a shipped
    pilot (both new flags OFF, today's default) and two forced-ON variants — `gust_target_slots`
    (the generalized `needs.py` slot family) and `recur_fuel_relax` (the quantified doom-relax
    refinement) — and flags any frame where either forced variant's DECIDED pick differs from the
    shipped one. Localizes the disagreements this issue's own charter commits to adjudicating
    before closing (and is the actual corpus evidence backing "swept clean" for BOTH flags, not
    just `gust_target_slots` — a gap the code-review Spec pass on #186 caught).

    python tools/train/probes/threat_sweep.py            # all four
    python tools/train/probes/threat_sweep.py --doom     # doom only
    python tools/train/probes/threat_sweep.py --recur
    python tools/train/probes/threat_sweep.py --target
    python tools/train/probes/threat_sweep.py --slots

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


def _frames():
    index = {}
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return [(k, v) for k, v in sorted(index.items()) if v.get("obs") and v.get("agent")]


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _decide(tune, rec):
    try:
        return tune._build_pilot(rec["agent"])[0].explain(rec["obs"])
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
            print(f"{ep + '-' + str(fr):<16} {rec['agent']:<14} {str(s['doom_old']):<6} "
                  f"{str(s['doom_curve']):<6} {s['doom_incoming']:>5} {s['my_hp']:>5} "
                  f"{'-' if chg is None else chg:>5} {str(bool(s.get('decided'))):<5} "
                  f"{str(s.get('doom_final', s['doom_old'])):<6} "
                  f"{'AGREE' if s['agree'] else 'DISAGREE'}{' FLIP' if flip else ''}")
    print(f"\nDOOM: agree {agree}/{total}  |  disagree {total - agree} "
          f"(incumbent-doomed-only={old_only} [curve LESS pessimistic — affordability/hand-size gate], "
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
            print(f"{ep + '-' + str(fr):<16} {rec['agent']:<14} body {b['id']:<6} fuel {b['fuel']} "
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
        print(f"{ep + '-' + str(fr):<16} {rec['agent']:<14} phase {s['phase']:<5} "
              f"top-removal id={top['id']} value={top['value']} "
              f"(prize={top['prize']} surv_shift={top['survival_shift']})  "
              f"bodies={len(s['bodies'])}")
    print(f"\nTARGET: frames-with-opp-bodies={fired}\n")


def _forced(tune, rec, **flags):
    pilot = tune._build_pilot(rec["agent"])[0]
    for k, v in flags.items():
        setattr(pilot, k, v)
    return pilot.explain(rec["obs"])


def sweep_slots(tune, frames) -> None:
    total = gust_flips = recur_flips = errors = 0
    for (ep, fr), rec in frames:
        d_off = _decide(tune, rec)
        if isinstance(d_off, Exception):
            errors += 1
            continue
        try:
            d_gust = _forced(tune, rec, gust_target_slots=True)
            d_recur = _forced(tune, rec, recur_fuel_relax=True)
        except Exception:
            errors += 1
            continue
        total += 1
        if d_off.chosen != d_gust.chosen:
            gust_flips += 1
            print(f"{ep + '-' + str(fr):<16} {rec['agent']:<14} gust_target_slots "
                  f"off={d_off.chosen} on={d_gust.chosen}  DISAGREE")
        if d_off.chosen != d_recur.chosen:
            recur_flips += 1
            print(f"{ep + '-' + str(fr):<16} {rec['agent']:<14} recur_fuel_relax "
                  f"off={d_off.chosen} on={d_recur.chosen}  DISAGREE")
    print(f"\nSLOTS: frames checked={total}  gust_target_slots flips={gust_flips}  "
          f"recur_fuel_relax flips={recur_flips}  (unreplayable={errors})\n")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Threat-Clock shadow sweeps over the corrections corpus")
    ap.add_argument("--doom", action="store_true")
    ap.add_argument("--recur", action="store_true")
    ap.add_argument("--target", action="store_true")
    ap.add_argument("--slots", action="store_true")
    args = ap.parse_args(argv)
    run_all = not (args.doom or args.recur or args.target or args.slots)
    tune, frames = _tune(), _frames()
    if args.doom or run_all:
        sweep_doom(tune, frames)
    if args.recur or run_all:
        sweep_recur(tune, frames)
    if args.target or run_all:
        sweep_target(tune, frames)
    if args.slots or run_all:
        sweep_slots(tune, frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
