"""Override GENERATOR (ADR-0032 D1): audit measurements -> shipped `attack_overrides.json`.

The audit is the *generator*, not just a checker: engine-measured facts the text parsers can't
derive are emitted as `build_attack_stats` overrides — measured coin bounds (the fork records),
fixed effect damage (Telekinesis's printed-0/deals-70), and sweep-fitted visible-state scalers.
Conservative by construction (REQ-AUDIT-0014..0017, 0019): only vanilla-panel forks (no W/R baked
in), only cross-scenario-constant effect damage, only EXACT integer linear fits — everything else
stays on the diff's gap ledger. Emitted overrides are DELTAS: a field the parser already got right
is never re-stated, so the file stays a readable list of engine-only knowledge.

A scaler's VARIABLE is named by measurement, never guessed (REQ-AUDIT-0019): the bench family needs
two joined single-variable sweeps because one sweep cannot separate `atk_bench` from `both_bench`,
and a fit may only claim a variable the harness actually controls. 274 Torcherto is the cautionary
case — a combined-bench scaler that shipped an exact-looking `atk_hand`/5 fit purely because bench
was the one variable the harness neither swept nor recorded.

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
# The bench family is named by JOINING two single-variable sweeps, never by one (REQ-AUDIT-0019):
# (sweep var, the seat it moves, the seat it pins).
_BENCH_AXES = (("atk_bench", "attackerBench", "defenderBench"),
               ("def_bench", "defenderBench", "attackerBench"))


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


def _axis_points(recs: list[dict], sweep_var: str, swept: str, pinned: str):
    """Controlled ``(count, dealt)`` points for ONE bench axis, or None when the axis is not
    usable. Takes the vanilla, coin-free records that either carry no sweep (the panel point,
    already pinned to the reference) or carry this axis's sweep.

    Rejects unless the PINNED seat is provably constant across them — read off the records, not
    trusted from the plan. Bench patience can run out and a seat can miss its target; an axis
    where the other seat drifted is not single-variable, and trusting one is precisely how the
    spurious 274 fit happened.
    """
    sel = [r for r in recs
           if r.get("scenario") == "vanilla" and not r.get("coin") and not r.get("coinLogs")
           and (r.get("sweep") or {}).get("var", sweep_var) == sweep_var]
    if len({r.get(pinned) for r in sel}) != 1:
        return None                                  # pinned seat drifted -> not single-variable
    pts = [(int(r[swept]), int(r["dealtActive"])) for r in sel if r.get(swept) is not None]
    return pts if len({x for x, _ in pts}) >= 3 else None      # _fit_linear needs >=3 distinct


def _axis_slope(pts) -> int | None:
    """Per-unit damage on one axis: 0 when the axis is provably FLAT (every measurement equal),
    ``k`` on an exact fit, None when neither — i.e. noisy. Flat and noisy must not be conflated:
    flat is the legitimate answer for the seat a one-sided scaler ignores, whereas noisy means
    the measurement cannot name anything and the whole family stays on the gap ledger."""
    if len({y for _, y in pts}) == 1:
        return 0
    fit = _fit_linear(pts)
    return fit[1] if fit else None


def _bench_family(recs: list[dict]) -> tuple[str, int] | None:
    """Name the bench-scaling family from the two joined sweeps, or None (REQ-AUDIT-0019).

    A single sweep cannot do this: moving the attacker's bench produces the SAME slope for an
    attacker-bench scaler and a combined-bench one, and a defender-bench scaler produces none.
    So both axes must be measured before anything is named — one axis alone is a guess, and the
    conservative answer is silence.
    """
    axes = {var: _axis_points(recs, var, swept, pinned) for var, swept, pinned in _BENCH_AXES}
    if any(pts is None for pts in axes.values()):
        return None                                  # an unmeasured axis names nothing
    a, d = _axis_slope(axes["atk_bench"]), _axis_slope(axes["def_bench"])
    if a is None or d is None:
        return None                                  # noisy -> gap ledger
    if a and d:
        return ("both_bench", a) if a == d else None  # unequal: not a family we can express
    if a:
        return "atk_bench", a
    return ("def_bench", d) if d else None


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
        # 3) sweep-fitted visible-state scaler — exact linear fit parser missed. The BENCH family
        # goes first: it is the only one whose variable takes two sweeps to name, and trying it
        # ahead of the single-variable families keeps a bench scaler from being mis-named off a
        # historical (bench-unpinned) hand or energy sweep.
        if not st.scaleVar:
            bench = _bench_family(recs)
            if bench:
                delta["scaleVar"], delta["scalePerUnit"] = bench
        if not st.scaleVar and not delta.get("scaleVar"):
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
