"""Attack-audit DIFF (ADR-0032 item 5, join half): measurements vs the damage oracle.

Loads ``reports/attack_audit/measurements.json`` (from ``audit_attacks.py``) and diffs each panel
measurement against ``compute_active_damage`` — the EXACT function the runtime routes through, so
a match here is a verification of the shipped closed form, and every mismatch is a discovered gap
(a mechanic the model doesn't capture yet). Report-only: confirmed fixes land as
``build_attack_stats`` overrides (or oracle changes), by hand.

    python tools/sim/diff_attack_audit.py                    # diff the accumulated measurements
    python tools/sim/diff_attack_audit.py --json out.json    # machine-readable gap list

Requirements:
    REQ-AUDIT-0011  Each successful measurement diffs against the oracle — a coin-fork record
                    against its own bound (min/max), a sweep/panel record with the attacker-side
                    scaling context off the record; match iff equal.
    REQ-AUDIT-0012  Error-ledger, live-coin (random outcome, no fork), and unknown-attack records
                    are classified SKIPS — counted, never silently dropped.
    REQ-AUDIT-0013  A gap carries ids, scenario, printed/dealt/predicted and a coarse class:
                    ``scaler`` (printed 0, dealt >0 — the formula tier's queue),
                    ``over_prediction`` (dealt 0, predicted >0 — conditional/does-nothing?),
                    else ``modifier`` (a wrong/missing flag or an unmodeled rider).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.strategy.damage import compute_active_damage  # noqa: E402

_DEFAULT_IN = Path(__file__).resolve().parents[2] / "reports" / "attack_audit" / "measurements.json"


def diff_records(records, attack_stats, card_stats, functions) -> dict:
    """Diff measurement records against the oracle (pure — REQ-AUDIT-0011..0013).

    Args:
        records: the measurement list (``audit_attacks.shape_record`` / ``error_record`` dicts).
        attack_stats: ``{attackId: AttackStat}`` (the shipped table under test).
        card_stats: ``{cardId: CardStat}`` or a provider with ``.get``.
        functions: the ``CardFunctions`` table (defender tags — prevention).

    Returns:
        ``{"matched": [...], "gaps": [...], "skipped": [{record, reason}, ...]}``.
    """
    get_stat = card_stats.get if hasattr(card_stats, "get") else (lambda cid: None)
    matched, gaps, skipped = [], [], []
    for rec in records:
        if rec.get("error"):
            skipped.append({"record": rec, "reason": "error_ledger"})
            continue
        if rec.get("coinLogs") and not rec.get("coin"):
            # a LIVE battle flips coins randomly (no select) — the outcome isn't deterministic, so
            # the record can't diff against a deterministic prediction; the coin FORK records
            # (min/max, below) are this attack's real measurement
            skipped.append({"record": rec, "reason": "coin_rng_live"})
            continue
        attack = attack_stats.get(rec.get("attackId"))
        if attack is None:
            skipped.append({"record": rec, "reason": "no_attack_record"})
            continue
        d_id = rec.get("defenderCardId")
        tags = frozenset(functions.tags(d_id)) if (functions and d_id is not None) else frozenset()
        # a coin-fork record measured that branch's worst/best — diff it against the same bound;
        # attacker-side scaling context comes off the record (def-side counts aren't recorded)
        bound = rec.get("coin") or "exact"
        context = {"atk_hand": rec.get("myHandSize"), "atk_active_energy": rec.get("attackerEnergies")}
        predicted = compute_active_damage(attack, get_stat(rec.get("attackerCardId")),
                                          get_stat(d_id) if d_id is not None else None, tags,
                                          bound=bound, context=context)
        dealt = rec.get("dealtActive", 0)
        if predicted == dealt:
            matched.append(rec)
            continue
        # a conditional attack whose live outcome landed WITHIN its modeled [min, max] is bounded-
        # correct: the exact branch is unknowable from one record, but Lethal (floor) and Incoming
        # (ceiling) both read it soundly — a match of kind "bounded", not a gap
        if not rec.get("coin") and attack.damageMin is not None:
            lo = compute_active_damage(attack, get_stat(rec.get("attackerCardId")),
                                       get_stat(d_id) if d_id is not None else None, tags,
                                       bound="min", context=context)
            hi = compute_active_damage(attack, get_stat(rec.get("attackerCardId")),
                                       get_stat(d_id) if d_id is not None else None, tags,
                                       bound="max", context=context)
            if lo <= dealt <= hi:
                matched.append({**rec, "bounded": True})
                continue
        cls = ("scaler" if (rec.get("printed", 0) == 0 and dealt > 0)
               else "over_prediction" if (dealt == 0 and predicted > 0) else "modifier")
        gaps.append({**{k: rec.get(k) for k in ("attackId", "attackerCardId", "scenario",
                                                "defenderCardId", "printed", "dealtActive", "koed")},
                     "coin": rec.get("coin"), "sweep": rec.get("sweep"),
                     "predicted": predicted, "class": cls})
    return {"matched": matched, "gaps": gaps, "skipped": skipped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Diff attack-audit measurements vs the damage oracle.")
    ap.add_argument("--measurements", type=Path, default=_DEFAULT_IN)
    ap.add_argument("--json", type=Path, default=None, help="write the gap list as JSON")
    args = ap.parse_args(argv)
    if not args.measurements.exists():
        print(f"no measurements at {args.measurements} — run audit_attacks.py first")
        return 1
    payload = json.loads(args.measurements.read_text(encoding="utf-8"))
    records = payload.get("measurements", payload) if isinstance(payload, dict) else payload

    from cg.api import all_attack, all_card_data  # engine tables — the runtime's own inputs
    from common.cards import CardFunctions
    from common.scouting.provider import _build_cache, build_attack_stats, load_attack_overrides
    # the SHIPPED table: text seeds + the audit-generated overrides — exactly what the agent loads
    out = diff_records(records, build_attack_stats(all_attack(), load_attack_overrides()),
                       _build_cache(all_card_data(), all_attack()), CardFunctions.load())

    n = len(out["matched"]) + len(out["gaps"])
    print(f"diffed {n} measurements: {len(out['matched'])} match, {len(out['gaps'])} gaps, "
          f"{len(out['skipped'])} skipped")
    for reason, cnt in Counter(s["reason"] for s in out["skipped"]).most_common():
        print(f"  skip[{reason}]: {cnt}")
    for cls, cnt in Counter(g["class"] for g in out["gaps"]).most_common():
        print(f"  gap[{cls}]: {cnt}")
    for g in out["gaps"]:
        print(f"    attack {g['attackId']} ({g['scenario']} vs {g['defenderCardId']}): "
              f"printed {g['printed']}, predicted {g['predicted']}, dealt {g['dealtActive']}"
              f"{' [koed]' if g.get('koed') else ''} -> {g['class']}")
    if args.json:
        args.json.write_text(json.dumps(out["gaps"], indent=1), encoding="utf-8")
        print(f"gaps -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
