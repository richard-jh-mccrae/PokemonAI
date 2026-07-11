"""Cross-engine audit diff (ADR-0050 M4 item 7): native vs cgpy attack measurements.

Both sides are produced by the SAME harness — ``tools/sim/audit_attacks.py`` — with the
engine swapped via ``CG_ENGINE=py`` (the alias seam). Join records by identity
(``record_key``) and compare the dealt-damage split with **zero tolerance**:

- both measured, no coin involved → ``dealtActive``/``dealtBench``/``dealtSelf``/``koed``
  must be EQUAL;
- coin attacks: the plain (``coin: None``) rows ride live rng luck — skipped; the
  deterministic ``coin: min``/``max`` fork rows must be EQUAL;
- one-sided errors are coverage findings, split by whether the chain is deferred
  (expected — cgpy refuses unmodeled attacks) or live (a real gap);
- both-sided errors are jointly unmeasurable (panel gaps) and skipped.

    # the sample loop (or --all for the nightly full-pool run):
    python tools/sim/audit_attacks.py --attack 87 --out reports/attack_audit/native.json
    CG_ENGINE=py python tools/sim/audit_attacks.py --attack 87 --out reports/attack_audit/cgpy.json
    python tools/parity/diff_audit_engines.py reports/attack_audit/native.json \\
        reports/attack_audit/cgpy.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools" / "sim"))

from audit_attacks import record_key  # noqa: E402

_FIELDS = ("dealtActive", "dealtBench", "dealtSelf", "koed")


def compare(native: list[dict], cgpy: list[dict]) -> dict:
    nat = {record_key(r): r for r in native}
    cgp = {record_key(r): r for r in cgpy}
    out = {"compared": 0, "equal": 0, "divergences": [], "skipped_luck": 0,
           "both_error": 0, "only_native": [], "only_cgpy": [],
           "cgpy_error": [], "native_error": []}
    for k in sorted(set(nat) & set(cgp), key=lambda t: tuple(str(x) for x in t)):
        a, b = nat[k], cgp[k]
        a_err, b_err = "error" in a, "error" in b
        if a_err and b_err:
            out["both_error"] += 1
            continue
        if b_err:
            out["cgpy_error"].append({"key": list(k), "error": b["error"]})
            continue
        if a_err:
            out["native_error"].append({"key": list(k), "error": a["error"]})
            continue
        coin_involved = (a.get("coinLogs") or b.get("coinLogs")) and k[3] is None
        if coin_involved:
            out["skipped_luck"] += 1      # plain row of a coin attack: rng luck differs;
            continue                      # the min/max fork rows carry the comparison
        out["compared"] += 1
        diffs = {f: (a.get(f), b.get(f)) for f in _FIELDS if a.get(f) != b.get(f)}
        if diffs:
            out["divergences"].append({"key": list(k), "diffs": diffs})
        else:
            out["equal"] += 1
    for k in sorted(set(nat) - set(cgp), key=lambda t: tuple(str(x) for x in t)):
        out["only_native"].append(list(k))
    for k in sorted(set(cgp) - set(nat), key=lambda t: tuple(str(x) for x in t)):
        out["only_cgpy"].append(list(k))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Diff native-vs-cgpy audit measurements.")
    ap.add_argument("native", type=Path)
    ap.add_argument("cgpy", type=Path)
    ap.add_argument("--json", action="store_true", help="full JSON report to stdout")
    args = ap.parse_args(argv)
    native = json.loads(args.native.read_text(encoding="utf-8"))["measurements"]
    cgpy = json.loads(args.cgpy.read_text(encoding="utf-8"))["measurements"]
    rep = compare(native, cgpy)
    if args.json:
        print(json.dumps(rep, indent=1))
    else:
        print(f"compared {rep['compared']} measured pairs: {rep['equal']} equal, "
              f"{len(rep['divergences'])} DIVERGENT; {rep['skipped_luck']} coin-luck "
              f"rows skipped, {rep['both_error']} jointly unmeasurable")
        if rep["cgpy_error"]:
            print(f"cgpy-only errors ({len(rep['cgpy_error'])}):")
            for e in rep["cgpy_error"][:12]:
                print("  ", e["key"], "->", e["error"][:90])
        if rep["native_error"]:
            print(f"native-only errors ({len(rep['native_error'])}):")
            for e in rep["native_error"][:12]:
                print("  ", e["key"], "->", e["error"][:90])
        for d in rep["divergences"][:20]:
            print("DIVERGED", d["key"], d["diffs"])
    return 1 if rep["divergences"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
