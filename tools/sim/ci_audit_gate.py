"""CI audit gate (ADR-0032, completion-plan P3): a bounded engine audit that FAILS on any
over-prediction — the soundness class (predicted damage the engine won't deal → phantom-KO risk).

Measures the highest-risk attacks fresh (the ignore-flag family + the modifier-heavy goldens)
against the panel, diffs them against the SHIPPED oracle + tables, and exits non-zero when a gap
of class ``over_prediction`` appears. Under-predictions and scaler gaps are reported but don't
fail (the safe direction). Runtime ~1 min; the full-pool audit stays a manual tool.

    python tools/sim/ci_audit_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

# the ignore-flag family (every parse claim) + the engine-verified interaction goldens
_GATE_ATTACKS = (70, 95, 148, 207, 252, 316, 331, 426, 434, 479, 529, 540, 564, 607, 753, 837,
                 850, 867, 872, 901, 980, 990, 1226, 1305, 1517, 1487, 1488, 1042)


def main() -> int:
    from sim.audit_attacks import audit_attack, card_pool, merge_records
    from sim.diff_attack_audit import diff_records
    from cg.api import all_attack, all_card_data
    from common.cards import CardFunctions
    from common.scouting.provider import _build_cache, build_attack_stats, load_attack_overrides

    cards = card_pool()
    records: list[dict] = []
    for aid in _GATE_ATTACKS:
        records = merge_records(records, audit_attack(aid, cards=cards))
    out = diff_records(records, build_attack_stats(all_attack(), load_attack_overrides()),
                       _build_cache(all_card_data(), all_attack()), CardFunctions.load())
    over = [g for g in out["gaps"] if g["class"] == "over_prediction"]
    print(f"gate: {len(out['matched'])} match, {len(out['gaps'])} gaps "
          f"({len(over)} over-prediction), {len(out['skipped'])} skipped")
    for g in over:
        print(f"  OVER-PREDICTION attack {g['attackId']} ({g['scenario']}): "
              f"predicted {g['predicted']}, engine dealt {g['dealtActive']}")
    if over:
        print("FAIL: the closed form promises damage the engine will not deal (phantom-KO risk)")
        return 1
    print("OK: no over-predictions — the oracle never promises more than the engine deals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
