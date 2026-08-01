"""Needs sweep — the keep-value v2 DISCARD report (ADR-0065 WP-N3/N4 acceptance number).

Replays every committed correction through a FRESH shipped Pilot per frame (the pilots are
stateful — sharing one across games pollutes verdicts, the `test_hyperclosure_corpus` lesson) and
prints the v2 discard shadow report: per forced-discard frame the DECIDED pick, v1's ranking
(`eq_pick`), v2's needs-assignment pick (`eq2_pick`), `agree_v2`, and the human `correct`. The
WP-N4 swap's acceptance was agree_v2 12/12 (2026-07-20), re-confirmed at `4be1db3` over the full
372-frame corpus.

    python tools/train/probes/needs_sweep.py

**The REFRESH half is gone (ADR-0101, Issue #261 item 2b).** It measured v1's Σ keep_cost against
v2's whole-hand assignment marginal to decide whether to promote the SHED; the promotion HAPPENED,
so the question it existed to answer is answered and its script is retired rather than left
runnable — a diagnostic whose shadow no longer exists can only report on itself (ADR-0089 Probe
Fate: a RULING's script is deleted once its answer is written down). Its final reading — 96 frames
fired, 16 sign-flips, v2 under-prices 53 / over-prices 39, measured at `ccd3a28` — is recorded in
ADR-0101 with the per-frame table, and the frames it named are the wave-2 ruling packet.

Offline and read-only; ~1-2 min for the full corpus (one engine-backed Pilot build per frame).
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
    """THE Corpus Reader, via the shared probe helper (ADR-0087 / ADR-0089)."""
    from train.probes._corpus import frames
    return frames()


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


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    # No flags left now the refresh half is retired — the parser stays so `--help` works and a
    # stale `--refresh` from muscle memory is REFUSED rather than silently ignored.
    argparse.ArgumentParser(
        description="Keep-value v2 discard shadow sweep over the corrections corpus").parse_args(argv)
    sweep_discard(_tune(), _frames())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
