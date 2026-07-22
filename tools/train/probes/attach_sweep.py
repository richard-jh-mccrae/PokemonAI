"""Attach sweep — Round-0 measurement for the energy-attach oracle fold (Phase 2,
`docs/plans/attach-valuation-phase2-handoff.md` §"How to rank the fold order", step 1).

Replays every committed correction through a FRESH shipped Pilot per frame (pilots are stateful —
sharing one pollutes verdicts, the `needs_sweep` lesson) and measures the SHADOW attach oracle
(`Pilot._attach_shadow`) against BOTH the live rungs and the human `correct`. It DECIDES NOTHING and
CHANGES NOTHING — it is the instrument that ranks the fold order before any rung is swapped.

Two reports (the agreed C design):

  * PRIMARY (fires-only) — one row per frame where the oracle fired (`attach_shadow is not None`).
    Every pick is compared by the resolved target SLOT `(area, position)`, NEVER the raw option
    index (duplicate energy-source options and identical-effect target copies otherwise read as
    false disagreements — 82523811-59, 82750161-59). Per frame: the oracle pick + energy, the live
    rung pick, the human `correct`, the slot-based `agree` bit, whether the rung / the oracle match
    `correct`, and the DOMINANT rung-family that drove the live pick (the executable fold map). The
    tail aggregates, PER FAMILY, the 2x2 that ranks the fold:
        rung-correct & agree   -> SAFE       (swap last / never — the oracle reproduces a good rung)
        rung-correct & !agree  -> REGRESSION (a swap would BREAK a correct pick — resolve first)
        !rung-correct & agree  -> SHARED_GAP (the oracle shares the blunder — don't swap)
        !rung-correct & !agree -> FIX        (oracle matches `correct` — the win, swap first)
                               -> DIVERGENT  (oracle disagrees with both — the oracle needs work)

  * AUDIT (the boundary log) — non-firing frames that carry an energy-tagged `_PLAY` option
    (`energy_accel`), e.g. the Crispin frame 85786096-70. These are energy-adjacent decisions made
    at the `_PLAY`/Supporter layer that the oracle CORRECTLY does not price; listing them makes the
    fires-only filter's exclusions visible instead of silent (so nobody mistakes them for coverage
    gaps). NOT a category/keyword filter — a structural one on the card's tag.

    python tools/train/probes/attach_sweep.py            # both reports
    python tools/train/probes/attach_sweep.py --primary  # primary only
    python tools/train/probes/attach_sweep.py --audit    # audit only

Offline and read-only; ~2-4 min for the full corpus (one engine-backed Pilot build per frame).
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

_PLAY, _ATTACH, _CARD, _ATTACH_FROM = 7, 8, 3, 21

# The EXECUTABLE fold map (attach-valuation-phase2-handoff.md §"The rung -> term fold map"): each
# baseline_energy rung id -> the oracle term (family) that SHOULD subsume it. Survivors map to
# "structure" (never folded). Any FIRED attach rung NOT in this map is flagged at the tail — the
# completeness check that we did not forget a rung.
FOLD_MAP = {
    "concentrate-energy-on-wincon": "marginal", "build-active-wincon": "marginal",
    "power-up-attacker": "marginal", "spread-attach-to-the-needy": "marginal",
    "concentrate-accel-on-one-line-body": "marginal",
    "dont-waste-discard-energy": "marginal(burst-veto)",
    "dont-attach-discard-energy-turn1": "marginal(burst-veto)",
    "dont-feed-the-doomed": "doomed-sign", "arm-the-doomed-active": "doomed-sign",
    "dont-overbuild-the-doomed-wincon": "doomed-sign",
    "conserve-burst-when-no-ko": "overkill",
    "dont-fund-the-non-attacking-body": "role-gate", "dont-power-the-draw-engine": "role-gate",
    "dont-waste-off-type-energy": "type-fit",
    "prefer-reusable-over-burst": "resource_cost", "conserve-discard-energy-prefer-basic": "resource_cost",
    "feed-the-firing-accelerator": "accel-routing", "advance-the-accel-pieces": "accel-routing",
    # survivors (structure, never folded)
    "attach-energy-last": "structure", "use-acceleration": "structure",
    "feed-the-line-for-disruptor-lock": "structure", "fuel-the-dormant-ability": "structure",
    "prefer-active-attach-in-setup": "structure",
}


def _names() -> dict:
    out = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for r in csv.reader(f):
            if r and r[0].isdigit():
                out[int(r[0])] = r[1]
    return out


def _energy_tags() -> dict:
    return json.loads((REPO / "src" / "common" / "card_functions.json").read_text(encoding="utf-8"))


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


def _agent(rec) -> str:
    a = rec.get("agent") or ""
    return a if a in {"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"} else "mega_starmie"


def _opt_slot(option: dict, ctx) -> tuple | None:
    """The resolved target SLOT of an option — (area, position) — or None for a non-attach option.
    type-8 ATTACH carries inPlayArea/inPlayIndex; the type-3 ATTACH_FROM recipient carries area/index."""
    t = option.get("type")
    if t == _ATTACH:
        return (option.get("inPlayArea"), option.get("inPlayIndex"))
    if t == _CARD and ctx == _ATTACH_FROM:
        return (option.get("area"), option.get("index"))
    return None


def _slots(indices, options, ctx) -> set:
    out = set()
    for i in indices or []:
        if 0 <= i < len(options):
            s = _opt_slot(options[i], ctx)
            if s is not None:
                out.add(s)
    return out


def _dominant_family(dec, chosen, options, ctx, unmapped: set) -> str:
    """The rung-family that drove the live pick: the max-|weight| FIRED attach rung on the chosen
    attach option(s), mapped through FOLD_MAP. '(no-attach)' when the rung didn't attach. Collects
    any fired id missing from FOLD_MAP into `unmapped` (the completeness check)."""
    best_fam, best_w = None, -1.0
    attached = False
    for i in chosen or []:
        if not (0 <= i < len(options)) or _opt_slot(options[i], ctx) is None:
            continue
        attached = True
        trace = dec.options[i] if i < len(dec.options) else None
        for hyp, w in getattr(trace, "fired", None) or []:
            hid = getattr(hyp, "id", None)
            fam = FOLD_MAP.get(hid)
            if fam is None:
                unmapped.add(hid)
                continue
            if abs(w) > best_w:
                best_fam, best_w = fam, abs(w)
    if not attached:
        return "(no-attach)"
    return best_fam or "(unmapped-only)"


def sweep_primary(tune, frames, names) -> None:
    print("PRIMARY — fires-only, slot-based comparison\n")
    hdr = f"{'id':<14} {'agent':<13} {'scope':<4} {'oracle':<16} {'live-rung':<16} {'correct':<12} {'agr':<4} {'bucket':<11} family"
    print(hdr); print("-" * len(hdr))
    per_family = defaultdict(lambda: defaultdict(int))
    unmapped = set()
    fired = 0
    # Out-of-scope: the oracle FIRED but `correct` is a NON-attach play (Supporter / retreat / evolve)
    # — the "whether to attach AT ALL" question, which is the _PLAY layer's lane, not the oracle's
    # (the 85786096-70 lesson). Counted separately; NEVER mixed into the fold-ranking 2x2.
    oos_total = oos_oracle_declined = 0
    for (ep, fr), rec in frames:
        try:
            dec = tune._build_pilot(_agent(rec))[0].explain(rec["obs"])
        except Exception:
            continue
        s = dec.attach_shadow
        if s is None:
            continue
        fired += 1
        options = rec["obs"]["select"]["option"]
        ctx = (rec["obs"].get("select") or {}).get("context")
        eq = s["eq_pick"]
        eq_slot = _opt_slot(options[eq], ctx) if eq is not None else None
        chosen_slots = _slots(dec.chosen, options, ctx)
        correct = rec.get("correct") or []
        correct_slots = _slots(correct, options, ctx)
        in_scope = bool(correct_slots)                     # `correct` IS an attach -> the oracle's lane
        agree = bool(s["agree"])

        def _show(slot, energy_id=None):
            if slot is None:
                return "abstain" if energy_id is None else "—"
            nm = names.get(energy_id, "") if energy_id is not None else ""
            return f"{slot}{('+' + nm.split(' ')[0]) if nm else ''}"
        eq_energy = next((r["energy"] for r in s["eq"] if r["i"] == eq), None) if eq is not None else None
        oracle_cell = _show(eq_slot, eq_energy)
        rung_cell = _show(next(iter(chosen_slots)) if chosen_slots else None)

        if not in_scope:                                   # out of the oracle's lane — count, don't rank
            oos_total += 1
            oos_oracle_declined += (eq is None)
            print(f"{ep + '-' + str(fr):<14} {rec['agent'][:12]:<13} {'OUT':<4} {oracle_cell:<16} "
                  f"{rung_cell:<16} {'no-attach':<12} {str(agree):<4} {'—':<11} (whether-to-attach)")
            continue

        rung_correct = bool(chosen_slots & correct_slots)
        oracle_correct = eq_slot in correct_slots if eq_slot is not None else False
        if rung_correct and agree:
            bucket = "SAFE"
        elif rung_correct and not agree:
            bucket = "REGRESSION"
        elif not rung_correct and agree:
            bucket = "SHARED_GAP"
        else:
            bucket = "FIX" if oracle_correct else "DIVERGENT"
        # Attribute to the dominant fired attach rung; when the rung made NO attach (it blundered a
        # non-attach on a frame whose correct IS an attach), there is no fired attach rung to blame.
        family = _dominant_family(dec, dec.chosen, options, ctx, unmapped)
        if family == "(no-attach)":
            family = "(rung-silent)"                        # rung missed the attach entirely
        per_family[family][bucket] += 1
        corr_cell = _show(next(iter(correct_slots)))
        print(f"{ep + '-' + str(fr):<14} {rec['agent'][:12]:<13} {'IN':<4} {oracle_cell:<16} {rung_cell:<16} "
              f"{corr_cell:<12} {str(agree):<4} {bucket:<11} {family}")

    print(f"\nfired on {fired} frames  |  IN-SCOPE (correct is an attach): {fired - oos_total}  |  "
          f"OUT-OF-SCOPE (correct is a non-attach play): {oos_total} "
          f"(oracle correctly declined on {oos_oracle_declined})")
    print("  → out-of-scope fires are the _PLAY-layer 'whether to attach at all' question, NOT the "
          "oracle's lane; they do NOT enter the fold-ranking 2x2.\n")
    print("PER-FAMILY 2x2 over IN-SCOPE frames (ranks the fold order):")
    print(f"  {'family':<22} {'SAFE':>5} {'REGRESSION':>11} {'SHARED_GAP':>11} {'FIX':>5} {'DIVERGENT':>10}   reading")
    for fam in sorted(per_family):
        c = per_family[fam]
        safe, reg, gap, fix, div = (c["SAFE"], c["REGRESSION"], c["SHARED_GAP"], c["FIX"], c["DIVERGENT"])
        if reg:
            reading = "REGRESSION RISK — resolve before any swap"
        elif fix and not (gap or div):
            reading = "swap FIRST (oracle fixes the rung)"
        elif safe and not (fix or gap or div):
            reading = "swap LAST / never (oracle reproduces the rung)"
        elif gap or div:
            reading = "oracle gap — do not swap yet"
        else:
            reading = ""
        print(f"  {fam:<22} {safe:>5} {reg:>11} {gap:>11} {fix:>5} {div:>10}   {reading}")
    if unmapped:
        print(f"\n⚠️ FIRED rungs missing from FOLD_MAP (did we forget an attach rung?): {sorted(unmapped)}")


def sweep_audit(tune, frames, names, tags) -> None:
    print("\nAUDIT — non-firing frames carrying an energy-tagged _PLAY option (the _PLAY-layer boundary)\n")
    hdr = f"{'id':<14} {'agent':<13} {'category':<16} {'chosen':<20} {'correct':<20} energy_play"
    print(hdr); print("-" * len(hdr))
    n = 0
    for (ep, fr), rec in frames:
        obs = rec["obs"]
        ctx = (obs.get("select") or {}).get("context")
        options = (obs.get("select") or {}).get("option") or []
        me = (obs.get("current", {}).get("players") or [{}])[obs.get("current", {}).get("yourIndex", 0)]
        hand = me.get("hand") or []
        energy_plays = []
        for o in options:
            if o.get("type") == _PLAY and o.get("index") is not None and o["index"] < len(hand):
                cid = (hand[o["index"]] or {}).get("id")
                if cid is not None and "energy_accel" in (tags.get(str(cid)) or []):
                    energy_plays.append(names.get(cid, str(cid)))
        if not energy_plays:
            continue
        try:
            dec = tune._build_pilot(_agent(rec))[0].explain(obs)
        except Exception:
            continue
        if dec.attach_shadow is not None:
            continue                                       # it fired — belongs in the primary, not here
        n += 1
        print(f"{ep + '-' + str(fr):<14} {rec['agent'][:12]:<13} {(rec.get('category') or '')[:15]:<16} "
              f"{(rec.get('chosen_label') or '')[:19]:<20} {(rec.get('correct_label') or '')[:19]:<20} "
              f"{', '.join(sorted(set(energy_plays)))}")
    print(f"\n{n} non-firing energy-adjacent frames (correctly excluded from the oracle's scope)")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Round-0 measurement of the energy-attach shadow oracle")
    ap.add_argument("--primary", action="store_true", help="primary (fires-only) report only")
    ap.add_argument("--audit", action="store_true", help="audit (boundary) report only")
    args = ap.parse_args(argv)
    tune, frames, names = _tune(), _frames(), _names()
    if not args.audit:
        sweep_primary(tune, frames, names)
    if not args.primary:
        sweep_audit(tune, frames, names, _energy_tags())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
