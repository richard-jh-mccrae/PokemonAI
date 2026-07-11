"""One-command card onboarding: seed → capture → replay → ledger (ADR-0050 M4 item 6).

The future-card path: when the competition ships new cards (or a chain needs its first
verification), this runs the whole loop for one card:

1. regenerate the machine seed layer (`seed_chains.py` — picks up new table rows; run
   `snapshot_tables.py` first if the DLL itself changed),
2. capture N per-card micro-traces on the native engine (`capture_card.py`),
3. replay them through cgpy (`replay_diff.py` semantics) — divergences are the spec,
4. on all-green: optionally promote the traces to committed fixtures (`--promote`) and
   rebuild the coverage ledger so the card's chains flip to `verified`.

A genuinely new mechanic (a new native symbol) still needs an interpreter op + a
conformance fixture — `extract_dsl.py --check` is the alarm for that.

    python tools/parity/onboard_card.py 674 -n 2
    python tools/parity/onboard_card.py 121 --attack 154 --promote
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools" / "parity"))

FIXTURES = REPO / "tests" / "fixtures" / "parity"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Onboard one card end-to-end (M4).")
    ap.add_argument("card", type=int)
    ap.add_argument("--attack", type=int, default=None,
                    help="target one attackId (default: card-play / all attacks)")
    ap.add_argument("-n", "--games", type=int, default=2)
    ap.add_argument("--seed", type=int, default=9900)
    ap.add_argument("--promote", action="store_true",
                    help="on all-green: copy the traces into tests/fixtures/parity/ "
                         "and rebuild the coverage ledger")
    args = ap.parse_args(argv)

    import capture_card
    import replay_diff
    import seed_chains

    print("== 1/4 seed layer")
    seed_chains.main([])
    from cgpy.chain import load_chain_defs
    load_chain_defs.cache_clear()

    print(f"== 2/4 capture {args.games} micro-trace(s) for card {args.card}")
    out = REPO / "data" / "parity" / "micro"
    prefix = f"onboard{args.card}" + (f"a{args.attack}" if args.attack else "")
    paths = []
    for i in range(args.games):
        tr = capture_card.capture_card(args.card, args.seed + i, attack_id=args.attack)
        p = out / f"{prefix}_{args.seed + i}.trace.json.gz"
        tr.save(p)
        paths.append(p)
        print(f"   wrote {p} frames={tr.meta['result']['steps']}")

    print("== 3/4 replay")
    rc = replay_diff.main([str(p) for p in paths])
    if rc != 0:
        print("-> divergences above are the card's remaining specification "
              "(author, then re-run)")
        return rc

    if not args.promote:
        print(f"== 4/4 all green — promote with: cp {out}/{prefix}_*.trace.json.gz "
              f"{FIXTURES}/ (then rebuild the ledger: python tools/parity/report.py)")
        return 0
    print("== 4/4 promote + ledger")
    for p in paths:
        shutil.copy2(p, FIXTURES / f"micro_{p.name}")
        print(f"   -> {FIXTURES / ('micro_' + p.name)}")
    import report
    ledger = report.build_ledger()
    print(report.rollup(ledger))
    report.LEDGER.parent.mkdir(parents=True, exist_ok=True)
    import json
    report.LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
    print(f"   wrote {report.LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
