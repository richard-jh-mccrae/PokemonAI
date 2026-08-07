"""Opponent-target discrimination sweep. **Not a gate.**

Measures how much the opponent-target ranking (`pilot._opponent_target_rows`) can actually tell
its candidates apart, and what each candidate leg adds over a MEANINGLESS leg of the same size.

## What this probe found, and the correction it carries

It was written to measure one thing and found another. The original reading — *"adding
`state_value`'s denial credit moves the top target on 46 of 314 frames"* — was wrong twice:

1. **Mis-scoped.** `gust_target_slot` is BENCH-ONLY (the opponent's Active is never a legal gust
   target), and ranking Active+Bench together lets the Active dominate the argmax. Bench-only is
   69/241, not 46/314.
2. **Not evidence.** A deliberately meaningless leg of the same magnitude (`cid % 7`) moves the
   same argmax on 64/241. The real credit separates from noise by five frames out of 241.

The cause is printed below every run: equal-prize groups whose rows carry an IDENTICAL value, so the
pick falls to list order and ANY continuous term appears to "improve" it.

⚠️ **The numbers above were measured BEFORE the Fractional Survival Clock landed, and this probe's
tie line reads lower now.** Re-run it before citing any figure here — and note it compares
`survival_shift`, a strict SUB-population of the Flat Tie, which is identical `value`
(`fractional_clock_sweep.py` reports both, and is the one to read for the tie population). The original
draft of this docstring said the ties were *"`survival_shift` integer-quantized to 0 for every
row"*; that was measured false — quantization was 10.0% of it. The rest is a **Structural Zero**:
`incoming()` aggregates their forms with a per-turn MAX, so removing a body that is not the argmax
moves nothing at any resolution. See ADR-0117 (fractional survival clock) for the correction and
ADR-0118 (sham control) for why the sham arms are mandatory here.

## Arms

    A  shipped      CardStat.prize_value                                   the PRE-ADR-0119 baseline
    B  damage       + `state_value._forward_credit(theirs.forward_payoff)` what `threat` does
    C  prize/raw    + (forward_prize - own_prize) * halve(hops)
    D  prize/band   + _READINESS_W * (forward_prize - own_prize) * halve(hops)

    A2      null control   — arm A against itself. MUST be 0, every run.
    S_cid   sham           — (cid % 7),  band-matched. No causal claim.
    S_hp    sham           — (hp % 70),  band-matched. No causal claim.
    S_pos   sham           — position index. The degenerate case: a leg that cannot beat LIST ORDER
                             is not ordering anything.

A candidate leg's number means nothing until it is read against the sham arms. Both control kinds
are required and they are not interchangeable: the null proves the comparison is stable, the shams
prove movement is attributable.

    python tools/train/probes/opponent_target_credit_sweep.py
    python tools/train/probes/opponent_target_credit_sweep.py --examples 8

Reads what SHIPS: a fresh stateful Pilot per frame (the `snipe_decider_sweep` discipline — a reused
Pilot leaks the previous frame's board), deployment profile untouched. Offline, read-only, always
exits 0.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.probes._corpus import replay_agent                  # noqa: E402
from train.probes._sham import READING, SHAMS, argmax, legs    # noqa: E402  THE sham vocabulary
from train.gates import keyed_corrections                      # noqa: E402
from common import needs as _needs                             # noqa: E402
from common.grading import halve                               # noqa: E402
from common.state_value import _READINESS_W, _forward_credit   # noqa: E402

#: Candidate legs — each carries a causal claim. The SHAM legs beside them carry none and come from
#: `_sham.SHAMS`, shared so two probes cannot drift into two different ideas of what a sham is.
_CANDIDATES = (("B", "B damage credit"), ("C", "C prize leg, RAW"), ("D", "D prize leg, banded"))

#: Band the shams are scaled into — the largest damage-credit value observed on the corpus. A sham
#: an order of magnitude smaller would lose trivially and prove nothing (ADR-0118 sham policy).
_SHAM_BAND = 0.054


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _legs(pilot, model, row, index: int, of: int) -> dict:
    """Every arm's ADDEND for one row. Fails to a no-claim zero on an unknown card — the direction
    both `forward_payoff` suppliers already take."""
    cid, prize = row["id"], float(row["prize"])
    try:
        forward = model.theirs.forward_payoff(cid)
        damage = _forward_credit(forward)
        forward_prize = float(pilot._forward_payoff_prize_value(cid) or 0.0)
    except Exception:
        forward, damage, forward_prize = None, 0.0, prize
    hops = int(getattr(forward, "hops", 0) or 0)
    raw = max(0.0, forward_prize - prize) * halve(hops) if hops > 0 else 0.0
    try:
        hp = float(model.theirs.view_of(row["body"]).hp_remaining or 0)
    except Exception:
        hp = 0.0
    return {"A": 0.0, "A2": 0.0, "B": damage, "C": raw, "D": _READINESS_W * raw,
            **{k: legs(k, band=_SHAM_BAND, card_id=cid, hp=hp, index=index, of=of)
               for k, _ in SHAMS},
            "_meta": (cid, prize, forward_prize, hops)}


def _scan(pilot, model, rows, phase) -> tuple:
    """``(arms, labels)`` — every arm's per-row value."""
    keys = ("A", "A2") + tuple(k for k, _ in _CANDIDATES) + tuple(k for k, _ in SHAMS)
    arms = {k: [] for k in keys}
    labels = []
    for i, row in enumerate(rows):
        addends = _legs(pilot, model, row, i, len(rows))
        labels.append(addends["_meta"])
        for k in keys:
            arms[k].append(_needs.opponent_target_value(
                prize_advance=float(row["prize"]) + addends[k],
                survival_shift=row["survival_shift"], phase=phase))
    return arms, labels


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=4, help="top-1 moves to print per candidate arm")
    args = ap.parse_args(argv)
    tune = _tune()
    frames = sorted(keyed_corrections(REPO / "data" / "corrections",
                                      predicate=lambda c: bool(c.obs and c.agent)))

    scopes = {"all": {"n": 0, "moved": Counter()}, "bench": {"n": 0, "moved": Counter()}}
    null_moved = 0
    equal_prize_groups = tied = 0
    spans: dict = {k: [] for k, _ in _CANDIDATES}
    examples: dict = {k: [] for k, _ in _CANDIDATES}
    errors: Counter = Counter()
    scanned = 0

    for key, rec in frames:
        try:
            pilot = tune._build_pilot(replay_agent(rec))[0]
            obs = rec.obs
            board = pilot._board(obs, obs.get("select") or {})
            result = pilot._opponent_target_rows(obs, board)
        except Exception as e:
            errors[type(e).__name__] += 1
            continue
        if not result:
            continue
        phase, rows = result
        scanned += 1
        model = pilot._state_model

        # THE TIE POPULATION — the floor every leg clears for free. Reported because a movement
        # percentage is uninterpretable without it (ADR-0118 sham policy).
        by_prize: dict = {}
        for r in rows:
            by_prize.setdefault(r["prize"], []).append(r)
        for group in by_prize.values():
            if len(group) < 2:
                continue
            equal_prize_groups += 1
            if len({float(r["survival_shift"]) for r in group}) == 1:
                tied += 1

        for scope in ("all", "bench"):
            subset = (rows if scope == "all"
                      else [r for r in rows if r["area"] == "bench" and r["value"] > 0])
            if len(subset) < 2:
                continue
            scopes[scope]["n"] += 1
            arms, labels = _scan(pilot, model, subset, phase)
            base = argmax(arms["A"])
            if scope == "bench":
                null_moved += argmax(arms["A2"]) != base
                for k, _ in _CANDIDATES:
                    spans[k].extend(v for v in
                                    (_legs(pilot, model, r, i, len(subset))[k]
                                     for i, r in enumerate(subset)) if v > 0)
            for k, _label in _CANDIDATES + SHAMS:
                if argmax(arms[k]) != base:
                    scopes[scope]["moved"][k] += 1
                    if scope == "bench" and k in examples and len(examples[k]) < args.examples:
                        examples[k].append((key, labels[base], labels[argmax(arms[k])]))

    print(f"corpus                              : {len(frames)} replayable corrections")
    print(f"frames with opponent-target rows    : {scanned}")
    if errors:
        print(f"replay errors                       : {dict(errors)}")
    print()
    print("THE TIE POPULATION (why any continuous leg scores well here)")
    print(f"  equal-prize groups (>=2 bodies)   : {equal_prize_groups}")
    pct = f"{100 * tied / equal_prize_groups:.1f}%" if equal_prize_groups else "n/a"
    print(f"  ...PERFECTLY TIED after survival  : {tied}  ({pct})  <- pick falls to list order")
    print()
    print(f"NULL CONTROL (bench, arm A vs itself): {null_moved} moves   <- must be 0")
    print()

    b = scopes["bench"]["n"]
    a = scopes["all"]["n"]
    print(f"{'leg':<22} {'BENCH (real seam)':<22} {'all rows':<18} credit range (prizes)")
    for k, label in _CANDIDATES:
        vals = spans[k]
        rng = f"{min(vals):.6f} - {max(vals):.4f}" if vals else "all zero"
        bench = f"{scopes['bench']['moved'][k]}/{b} ({100*scopes['bench']['moved'][k]/b:.1f}%)" if b else "-"
        allr = f"{scopes['all']['moved'][k]}/{a} ({100*scopes['all']['moved'][k]/a:.1f}%)" if a else "-"
        print(f"{label:<22} {bench:<22} {allr:<18} {rng}")
    print(f"{'':-<22} {'':-<22} {'':-<18}")
    for k, label in SHAMS:
        bench = f"{scopes['bench']['moved'][k]}/{b} ({100*scopes['bench']['moved'][k]/b:.1f}%)" if b else "-"
        allr = f"{scopes['all']['moved'][k]}/{a} ({100*scopes['all']['moved'][k]/a:.1f}%)" if a else "-"
        print(f"{label:<22} {bench:<22} {allr:<18} band-matched to {_SHAM_BAND}")

    for k, label in _CANDIDATES:
        if examples[k]:
            print(f"\n  {label} — first {len(examples[k])} bench top-1 moves "
                  f"(cardId, own_prize, forward_prize, hops)")
            for key, was, now in examples[k]:
                print(f"    {key:<26} {was}  ->  {now}")

    print()
    print(READING)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
