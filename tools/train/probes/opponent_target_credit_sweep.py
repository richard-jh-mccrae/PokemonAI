"""Opponent-target denial-credit sweep — the DIAGNOSTIC for the `_opponent_target_rows` gap.
**Not a gate.**

Issue #285 ruled that removing an opponent body is worth what its LINE becomes, not what the body
yields now (*"killing a Staryu prices 1 prize … when the doctrine's entire point is that it erases
three"*), and specified the fix as *"feed the result into `opponent_target_value`'s `prize_advance`
as a denial credit."* That function has two prize-bearing callers:

* `state_value._reachable_target_values` — **has** the credit (`_denied_forward_payoff`).
* `pilot._opponent_target_rows` — **does not.** `prize_advance` is bare `CardStat.prize_value`.

So the shipped agent carries two opinions about what an opponent body is worth to remove, and this
probe measures how often they disagree about WHICH body to take. It also prices two candidate
shapes for the prize leg `threat.blind_to` names as still missing on both seams (*"a pre-evolution
whose forward form is a 3-prize Mega ex and one whose forward form is a 1-prize body of the same
printed damage price IDENTICALLY"*).

Four arms on `prize_advance`, argmax compared per frame against arm A:

    A  shipped     CardStat.prize_value                                  what `_opponent_target_rows` does
    B  damage      + `state_value._forward_credit(theirs.forward_payoff)` what `threat` already does
    C  prize/raw   + (forward_prize - own_prize) * halve(hops)
    D  prize/band  + _READINESS_W * (forward_prize - own_prize) * halve(hops)

`forward_prize` is `pilot._forward_payoff_prize_value` (ADR-0048) — shipped, and wired to neither
seam. No new constant is introduced: C and D reuse `grading.halve` (the `EvolveBody.p_arrive`
convention) and `state_value._READINESS_W` (the anchor `development.evolve_marginal` and the
existing denial credit both carry).

    python tools/train/probes/opponent_target_credit_sweep.py
    python tools/train/probes/opponent_target_credit_sweep.py --examples 8

**Arm A is also run against ITSELF as a null control**, printed every run. An argmax sweep that
cannot report zero is not measuring anything, and this one is comparing float sums where a tie
convention decides the answer — so the control is load-bearing, not decoration.

Reads what SHIPS: a fresh stateful Pilot per frame (the `snipe_decider_sweep` discipline — a reused
Pilot leaks the previous frame's board), the deployment profile untouched. Offline and read-only.
Always exits 0: it reports, it does not gate.
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
from train.gates import keyed_corrections                      # noqa: E402
from common import needs as _needs                             # noqa: E402
from common.grading import halve                               # noqa: E402
from common.state_value import _READINESS_W, _forward_credit   # noqa: E402

_ARMS = (("A", "A shipped (control)"), ("B", "B damage credit"),
         ("C", "C prize leg, RAW"), ("D", "D prize leg, _READINESS_W"))


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _argmax(values) -> int | None:
    """Index of the maximum, FIRST-wins on a tie.

    Stated rather than left to `max`: every arm re-ranks the same rows, so an unstable tie
    convention would report movement that is a sort artefact. The null control is what proves this
    convention holds across two independent evaluations of the same arm."""
    best_i, best_v = None, None
    for i, v in enumerate(values):
        if best_v is None or v > best_v + 1e-12:
            best_i, best_v = i, v
    return best_i


def _row_credits(pilot, model, row) -> tuple:
    """``(damage_credit, prize_raw, prize_band, forward_prize, hops)`` for one opponent-target row.

    Fails to a no-claim zero on an unknown card, the direction both `forward_payoff` suppliers
    already take — a phantom credit would move the argmax this probe exists to count."""
    cid, prize = row["id"], float(row["prize"])
    try:
        forward = model.theirs.forward_payoff(cid)
        damage = _forward_credit(forward)
        forward_prize = float(pilot._forward_payoff_prize_value(cid) or 0.0)
    except Exception:
        return 0.0, 0.0, 0.0, prize, 0
    hops = int(getattr(forward, "hops", 0) or 0)
    raw = max(0.0, forward_prize - prize) * halve(hops) if hops > 0 else 0.0
    return damage, raw, _READINESS_W * raw, forward_prize, hops


def _frame_arms(pilot, model, rows, phase) -> tuple:
    """``(arms, labels, live)`` — every arm's per-row value, plus whether ANY credit is nonzero."""
    arms = {key: [] for key, _label in _ARMS}
    arms["A2"] = []
    labels, live = [], False
    for row in rows:
        prize, shift = float(row["prize"]), row["survival_shift"]
        damage, raw, band, forward_prize, hops = _row_credits(pilot, model, row)
        live = live or damage > 0.0 or raw > 0.0
        for key, extra in (("A", 0.0), ("A2", 0.0), ("B", damage), ("C", raw), ("D", band)):
            arms[key].append(_needs.opponent_target_value(
                prize_advance=prize + extra, survival_shift=shift, phase=phase))
        labels.append((row["id"], prize, forward_prize, hops))
    return arms, labels, live


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=4, help="top-1 moves to print per arm")
    args = ap.parse_args(argv)
    tune = _tune()
    frames = sorted(keyed_corrections(REPO / "data" / "corrections",
                                      predicate=lambda c: bool(c.obs and c.agent)))

    scanned = rankable = live_frames = null_moved = 0
    moved: Counter = Counter()
    spans: dict = {"B": [], "C": [], "D": []}
    examples: dict = {"B": [], "C": [], "D": []}
    errors: Counter = Counter()
    c_not_b = b_not_c = both = 0

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
        if len(rows) < 2:
            continue                          # one row: no ordering for any arm to move
        rankable += 1

        arms, labels, live = _frame_arms(pilot, pilot._state_model, rows, phase)
        live_frames += bool(live)
        for arm in ("B", "C", "D"):
            spans[arm].extend(
                v for v in (_row_credits(pilot, pilot._state_model, r)[
                    {"B": 0, "C": 1, "D": 2}[arm]] for r in rows) if v > 0)

        base = _argmax(arms["A"])
        null_moved += _argmax(arms["A2"]) != base
        hit = {}
        for arm in ("B", "C", "D"):
            hit[arm] = _argmax(arms[arm]) != base
            if hit[arm]:
                moved[arm] += 1
                if len(examples[arm]) < args.examples:
                    examples[arm].append((key, labels[base], labels[_argmax(arms[arm])]))
        both += hit["B"] and hit["C"]
        c_not_b += hit["C"] and not hit["B"]
        b_not_c += hit["B"] and not hit["C"]

    print(f"corpus                              : {len(frames)} replayable corrections")
    print(f"frames with opponent-target rows    : {scanned}")
    print(f"frames with >=2 rows (RANKABLE)     : {rankable}   <- the denominator")
    print(f"  ...with any nonzero credit        : {live_frames}   <- the only frames that CAN move")
    if errors:
        print(f"replay errors                       : {dict(errors)}")
    print(f"\nNULL CONTROL (arm A vs itself)      : {null_moved} moves   <- must be 0\n")

    print(f"{'arm':<28} {'top-1 moved':<18} credit range (prizes)")
    for arm, label in _ARMS[1:]:
        values = spans[arm]
        span = (f"{min(values):.6f} - {max(values):.4f} (n={len(values)})" if values else "all zero")
        pct = f"{moved[arm]}/{rankable}" + (f" ({100 * moved[arm] / rankable:.1f}%)" if rankable else "")
        print(f"{label:<28} {pct:<18} {span}")

    print(f"\n  both B and C move                 : {both}")
    print(f"  C moves where B does NOT          : {c_not_b}   <- the prize leg's MARGINAL over `threat`")
    print(f"  B moves where C does NOT          : {b_not_c}")

    for arm, label in _ARMS[1:]:
        if examples[arm]:
            print(f"\n  {label} — first {len(examples[arm])} top-1 moves "
                  f"(cardId, own_prize, forward_prize, hops)")
            for key, was, now in examples[arm]:
                print(f"    {key:<26} {was}  ->  {now}")

    print("\nThis probe REPORTS, it does not gate. Arm B is not a proposal — it is what "
          "`state_value.threat` already computes and `_opponent_target_rows` does not, so its "
          "column is a live disagreement between two shipped seams, not a candidate change. "
          "Top-1 MOVEMENT is not top-1 IMPROVEMENT: the corpus rules chosen OPTIONS, not target "
          "rows, so a moved argmax is a difference this probe can see and a merit it cannot. The "
          "decision test remains `decider_lab.py diff --baseline data/decider_lab/baseline.json`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
