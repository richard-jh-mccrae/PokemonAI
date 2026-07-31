"""Needs sweep — the keep-value v2 corpus reports (ADR-0065 WP-N3/N4b acceptance numbers).

Replays every committed correction through a FRESH shipped Pilot per frame (the pilots are
stateful — sharing one across games pollutes verdicts, the `test_hyperclosure_corpus` lesson) and
prints the two v2 shadow reports:

  * DISCARD  — per forced-discard frame: the DECIDED pick, v1's ranking (`eq_pick`), v2's
    needs-assignment pick (`eq2_pick`), `agree_v2`, and the human `correct`. The WP-N4 swap's
    acceptance was agree_v2 12/12 here (2026-07-20).
  * REFRESH  — per frame where the refresh-SHED magnitude shadow fired: v1's Σ keep_cost vs v2's
    whole-hand assignment marginal, the two swings, the SIGN-agreement bit, and the aggregate
    under-/over-pricing split. WP-N4b's verdict numbers (18 sign-flips, 46 under-priced), WP-N5's
    improvement (13 / 19), and WP-N6's (8 flips, mean |Δ| 9.7→6.7 with the resupply leg live)
    came from this report; the residual flips are the v2 scope gaps the grill spec's WP-N6 entry
    names (the answer_doom flat tier, the engine band).

    python tools/train/probes/needs_sweep.py            # both reports
    python tools/train/probes/needs_sweep.py --refresh  # refresh only (the slower one)
    python tools/train/probes/needs_sweep.py --discard

Offline and read-only; ~2-4 min for the full corpus (one engine-backed Pilot build per frame).
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

_DISCARD = 8


def _frames():
    """`gates.keyed_corrections` — THE Corpus Reader (ADR-0087 decision 1, Issue #243). The private
    raw-JSONL walk this replaced was short **40** records: a falsy `agent` is *recoverable* from
    `agent_build`, and only `Correction.from_dict` backfills it. Keyed by `(episode, frame)` for the
    display id this probe prints; the derived **Frame Key** is discarded here rather than
    hand-rebuilt, which is the half of ADR-0087 that cost the Decision Gate 163 keys."""
    from train.gates import keyed_corrections
    index = {(str(c.episode_id), (c.decision or {}).get("frame")): c
             for _key, c in keyed_corrections(REPO / "data" / "corrections")
             if c.obs and c.agent}
    return sorted(index.items())


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sweep_discard(tune, frames) -> None:
    print(f"{'id':<14} {'agent':<14} {'chosen':<12} {'v1':<12} {'v2':<12} agree_v2  correct")
    agree = total = 0
    for (ep, fr), rec in frames:
        if (rec.obs.get("select") or {}).get("context") != _DISCARD:
            continue
        d = tune._build_pilot(rec.agent)[0].explain(rec.obs)
        s = d.discard_shadow
        if s is None:
            continue
        total += 1
        agree += s["agree_v2"]
        print(f"{ep + '-' + str(fr):<14} {rec.agent:<14} {str(sorted(d.chosen)):<12} "
              f"{str(s['eq_pick']):<12} {str(s['eq2_pick']):<12} {str(s['agree_v2']):<8}  "
              f"{rec.correct}")
    print(f"\ndiscard agree_v2: {agree}/{total}\n")


def sweep_refresh(tune, frames) -> None:
    print(f"{'id':<14} {'agent':<14} {'cid':<6} {'v1_shed':>8} {'v2_shed':>8} "
          f"{'swing_v1':>9} {'swing_v2':>9} sign_agree")
    fired = flips = under = over = 0
    for (ep, fr), rec in frames:
        if (rec.obs.get("select") or {}).get("context") == _DISCARD:
            continue
        try:
            s = tune._build_pilot(rec.agent)[0].explain(rec.obs).refresh_shadow
        except Exception:
            continue
        if s is None:
            continue
        fired += 1
        delta = s["v2_shed"] - s["v1_shed"]
        under += delta < -0.05
        over += delta > 0.05
        flips += not s["sign_agree"]
        print(f"{ep + '-' + str(fr):<14} {rec.agent:<14} {s['cid']:<6} {s['v1_shed']:>8} "
              f"{s['v2_shed']:>8} {s['swing_v1']:>9} {s['swing_v2']:>9} {s['sign_agree']}")
    print(f"\nrefresh: fired={fired}  sign-flips={flips}  "
          f"v2-under-prices(UNSAFE)={under}  v2-over-prices(safe; the missing resupply)={over}")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Keep-value v2 shadow sweeps over the corrections corpus")
    ap.add_argument("--discard", action="store_true", help="discard report only")
    ap.add_argument("--refresh", action="store_true", help="refresh report only")
    args = ap.parse_args(argv)
    tune, frames = _tune(), _frames()
    if not args.refresh:
        sweep_discard(tune, frames)
    if not args.discard:
        sweep_refresh(tune, frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
