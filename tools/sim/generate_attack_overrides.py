"""Override GENERATOR (ADR-0032 D1): audit measurements -> shipped `attack_overrides.json`.

The audit is the *generator*, not just a checker: engine-measured facts the text parsers can't
derive are emitted as `build_attack_stats` overrides — measured coin bounds (the fork records),
fixed effect damage (Telekinesis's printed-0/deals-70), and sweep-fitted visible-state scalers.
Conservative by construction (REQ-AUDIT-0014..0017): only vanilla-panel forks (no W/R baked in),
only cross-scenario-constant effect damage, only EXACT integer linear fits — everything else stays
on the diff's gap ledger. Emitted overrides are DELTAS: a field the parser already got right is
never re-stated, so the file stays a readable list of engine-only knowledge.

    python tools/sim/generate_attack_overrides.py             # writes src/common/attack_overrides.json
    python tools/sim/generate_attack_overrides.py --dry-run   # print, don't write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

_MEASUREMENTS = Path(__file__).resolve().parents[2] / "reports" / "attack_audit" / "measurements.json"
_OUT = Path(__file__).resolve().parents[2] / "src" / "common" / "attack_overrides.json"
_SWEEP_VARS = {"hand": ("atk_hand", "myHandSize"), "energy": ("atk_active_energy", "attackerEnergies")}
_PANEL = ("vanilla", "weak", "resist", "prevent_ex")


def _fit_linear(points: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Exact integer fit ``dealt = base + k*x`` over >=3 distinct points; None unless every
    residual is 0 and k > 0 (a noisy or non-linear scaler stays on the ledger)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return None
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    if x1 == x0 or (y1 - y0) % (x1 - x0):
        return None
    k = (y1 - y0) // (x1 - x0)
    base = y0 - k * x0
    if k <= 0 or any(base + k * x != y for x, y in pts):
        return None
    return base, k


def derive_overrides(records: list[dict], parsed: dict,
                     texts: dict[int, str] | None = None) -> dict[int, dict]:
    """Pure derivation: measurement records + the parsed AttackStat table -> override deltas.

    Args:
        records: audit measurement records (``audit_attacks`` shapes).
        parsed: ``{attackId: AttackStat}`` as the text parsers built it (the baseline).
        texts: optional ``{attackId: text}`` — a COPY-attack ("use it as this attack") is
            excluded from bound generation: its measured damage is the copied attack's, which
            is defender-dependent and doesn't transfer across boards.

    Returns:
        ``{attackId: {field: value}}`` — only fields the measurements establish and the
        parser missed (deltas, REQ-AUDIT-0017).
    """
    by_attack: dict[int, list[dict]] = {}
    for r in records:
        if not r.get("error"):
            by_attack.setdefault(r.get("attackId"), []).append(r)
    out: dict[int, dict] = {}
    for aid, recs in by_attack.items():
        st = parsed.get(aid)
        if st is None:
            continue
        if texts and "use it as this attack" in (texts.get(aid) or ""):
            continue                                     # copy-attack: measurements don't transfer
        delta: dict = {}
        # 1) measured coin bounds — vanilla-panel forks only (no W/R baked into dealt number)
        forks = {r["coin"]: r["dealtActive"] for r in recs
                 if r.get("coin") and r.get("scenario") == "vanilla"}
        if "min" in forks and "max" in forks:
            lo, hi = int(forks["min"]), int(forks["max"])
            if (st.damageMin, st.damageMax) != (lo, hi):
                delta["damageMin"], delta["damageMax"] = lo, hi
        # 2) fixed effect damage — printed 0, constant across >=2 modifier scenarios
        plain = [r for r in recs if not r.get("coin") and not r.get("sweep")
                 and not r.get("coinLogs") and r.get("scenario") in _PANEL]
        vals = {int(r["dealtActive"]) for r in plain}
        if (st.damage == 0 and not st.scaleVar and len(plain) >= 2 and len(vals) == 1
                and vals != {0}):
            delta["damage"] = vals.pop()
        # 3) sweep-fitted visible-state scaler — exact linear fit parser missed
        if not st.scaleVar:
            for var, (scale_var, field) in _SWEEP_VARS.items():
                pts = [(int(r.get(field, 0)), int(r["dealtActive"])) for r in plain
                       if r.get("scenario") == "vanilla"]
                pts += [(int(r.get(field, 0)), int(r["dealtActive"])) for r in recs
                        if (r.get("sweep") or {}).get("var") == var
                        and r.get("scenario") == "vanilla" and not r.get("coin")]
                fit = _fit_linear(pts)
                if fit:
                    delta["scaleVar"], delta["scalePerUnit"] = scale_var, fit[1]
                    break
        if delta:
            out[aid] = delta
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate attack_overrides.json from audit measurements.")
    ap.add_argument("--measurements", type=Path, default=_MEASUREMENTS)
    ap.add_argument("--out", type=Path, default=_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    payload = json.loads(args.measurements.read_text(encoding="utf-8"))
    records = payload.get("measurements", payload) if isinstance(payload, dict) else payload

    from cg.api import all_attack
    from common.scouting.provider import build_attack_stats
    attacks = all_attack()
    overrides = derive_overrides(records, build_attack_stats(attacks),
                                 texts={a.attackId: a.text or "" for a in attacks})

    print(f"{len(overrides)} attacks gain engine-derived overrides")
    for aid, fields in sorted(overrides.items()):
        print(f"  {aid}: {fields}")
    if not args.dry_run:
        args.out.write_text(json.dumps({str(k): v for k, v in sorted(overrides.items())},
                                       indent=1), encoding="utf-8")
        print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
