"""Override GENERATOR (ADR-0032 D1, ADR-0083, ADR-0108): audit measurements -> `attack_overrides.json`
plus its committed provenance sidecar, emitted in one pass.

Overrides are DELTAS — a field the parser already got right is never re-stated. Merge rule: the
generator may retract what it AUTHORED, never what a human RULED (`--prune`/`--rule` opt in).
ADR-0032 owns REQ-PROV-0001..0008; ADR-0083 owns the REQ-AUDIT decisions.

    python tools/sim/generate_attack_overrides.py             # writes the table + the sidecar
    python tools/sim/generate_attack_overrides.py --dry-run   # print, don't write
    python tools/sim/generate_attack_overrides.py --rule      # accept a fit OVER a human ruling

ADR-0032 and ADR-0083 own the requirements this module is graded against.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

_REPO = Path(__file__).resolve().parents[2]
_MEASUREMENTS = _REPO / "reports" / "attack_audit" / "measurements.json"
_OUT = _REPO / "tools" / "meta_tracker" / "attack_overrides.json"
_PROVENANCE = _REPO / "src" / "common" / "attack_overrides.provenance.json"
_SWEEP_VARS = {"hand": ("atk_hand", "myHandSize"), "energy": ("atk_active_energy", "attackerEnergies")}
_PANEL = ("vanilla", "weak", "resist", "prevent_ex")
#: The matched non-{ex} control (REQ-AUDIT-0021) — `audit_attacks.PLAIN_SCENARIO`. NOT in `_PANEL`:
#: not a modifier scenario, so it must not feed the fixed-damage or single-variable scaler paths.
_PLAIN_SCENARIO = "vanilla_plain"
_EVIDENCE_SCENARIOS = (*_PANEL, _PLAIN_SCENARIO)
# (sweep var, the seat it moves, the seat it pins). Two joined sweeps, never one (REQ-AUDIT-0019).
_BENCH_AXES = (("atk_bench", "attackerBench", "defenderBench"),
               ("def_bench", "defenderBench", "attackerBench"))
#: Joined for the same reason (REQ-AUDIT-0020): with the defender on zero Energy `atk_active_energy`
#: and `both_active_energy` are the same number at every point.
_ENERGY_AXES = (("energy", "attackerEnergies", "defenderEnergies"),
                ("def_energy", "defenderEnergies", "attackerEnergies"))

#: Closed vocabulary (REQ-PROV-0001): "measured", "read off the card" and "nobody knows any more"
#: must not look alike in the file.
METHOD_ENGINE_FIT = "engine_fit"
METHOD_TEXT_VERIFIED = "text_verified"
METHOD_UNAUDITED = "unaudited"
METHODS = (METHOD_ENGINE_FIT, METHOD_TEXT_VERIFIED, METHOD_UNAUDITED)

#: Bumped only when an entry's SHAPE changes; the reader fails loudly rather than mis-parsing.
PROVENANCE_VERSION = 2

#: ``(field, reader)``. ONE source for the row's shape AND for `_evidence`'s dedup key — stating the
#: names twice would let a new field join the row while the dedup silently kept collapsing on it.
_EVIDENCE_FIELDS = (
    ("scenario", lambda r: r.get("scenario")),
    ("sweep", lambda r: (r.get("sweep") or {}).get("var")),
    ("step", lambda r: (r.get("sweep") or {}).get("step")),
    ("coin", lambda r: r.get("coin")),
    ("atkBench", lambda r: r.get("attackerBench")),
    ("defBench", lambda r: r.get("defenderBench")),
    ("defEx", lambda r: r.get("defenderExInPlay")),
    ("atkBenchStage2", lambda r: r.get("attackerBenchStage2")),
    ("energies", lambda r: r.get("attackerEnergies")),
    ("defEnergies", lambda r: r.get("defenderEnergies")),
    ("hand", lambda r: r.get("myHandSize")),
    ("dealt", lambda r: r.get("dealtActive")),
)
EVIDENCE_KEYS = tuple(name for name, _ in _EVIDENCE_FIELDS)
#: Everything the harness CONTROLS — the row minus the one thing it measures. Two rows agreeing here
#: and disagreeing on `dealt` are a contradiction, not a duplicate.
CONTROLLED_KEYS = EVIDENCE_KEYS[:-1]
_READ = dict(_EVIDENCE_FIELDS)
#: Which sweep PLAN produced a row — a provenance label, not board state. Two plans routinely land
#: on the same board (the panel point and the `atk_bench` step-1 point both pin the benches at 1).
_LABEL_KEYS = ("sweep", "step")
#: The physical board: controlled state minus the labels, minus `coin` (the two fork outcomes ARE
#: the same board).
BOARD_KEYS = tuple(k for k in CONTROLLED_KEYS if k not in (*_LABEL_KEYS, "coin"))


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
    """Controlled ``(count, dealt)`` points for ONE bench axis, or None when it is not usable.
    Rejects unless the PINNED seat is constant across the records — a seat can miss its target."""
    def _on_axis(r):
        return (r.get("sweep") or {}).get("var", sweep_var) == sweep_var

    sel = [r for r in recs
           if r.get("scenario") == "vanilla" and not r.get("coin") and not r.get("coinLogs")
           and _on_axis(r)]
    if len({r.get(pinned) for r in sel}) != 1:
        return None                                  # pinned seat drifted -> not single-variable
    pts = [(int(r[swept]), int(r["dealtActive"])) for r in sel if r.get(swept) is not None]
    return pts if len({x for x, _ in pts}) >= 3 else None      # _fit_linear needs >=3 distinct


def _axis_slope(pts) -> int | None:
    """Per-unit damage on one axis: 0 when provably FLAT, ``k`` on an exact fit, None when noisy.
    Flat is a legitimate answer (the seat a one-sided scaler ignores); noisy names nothing."""
    if len({y for _, y in pts}) == 1:
        return 0
    fit = _fit_linear(pts)
    return fit[1] if fit else None


def _rulebox_points(recs: list[dict]) -> list[tuple[int, int, int]] | None:
    """``(defExInPlay, defenderBench, dealt)`` over the {ex} defender-bench axis AND its MATCHED
    non-{ex} control — the only shape that can tell `def_ex_in_play` from `def_bench`."""
    def _on_def_bench_axis(r):
        return (r.get("sweep") or {}).get("var", "def_bench") == "def_bench"

    sel = [r for r in recs
           if r.get("scenario") in ("vanilla", _PLAIN_SCENARIO)
           and not r.get("coin") and not r.get("coinLogs") and _on_def_bench_axis(r)]
    if len({r.get("scenario") for r in sel}) != 2:
        return None                     # no matched control -> the confound is not broken
    if len({r.get("attackerBench") for r in sel}) != 1:
        return None                     # the attacker seat drifted -> not single-variable
    pts = [(int(r["defenderExInPlay"]), int(r["defenderBench"]), int(r["dealtActive"]))
           for r in sel
           if r.get("defenderExInPlay") is not None and r.get("defenderBench") is not None]
    return pts or None


def _rulebox_family(recs: list[dict]) -> tuple[str, int] | None:
    """Name `def_ex_in_play`, only when the matched control SEPARATES it from `def_bench`: the
    points must fit the rule-box count exactly AND must NOT fit the bench count."""
    pts = _rulebox_points(recs)
    if not pts:
        return None
    fit = _fit_linear([(ex, dealt) for ex, _, dealt in pts])
    if not fit:
        return None
    if _fit_linear([(bench, dealt) for _, bench, dealt in pts]):
        return None                 # both readings still survive -> collinear, so name nothing
    return "def_ex_in_play", fit[1]


def _bench_control_refutes(recs: list[dict]) -> bool:
    """True when the matched non-{ex} control refutes a BENCH-COUNT reading. Guarded on the damage
    actually moving: treating "flat" as a refutation would block a legitimate `atk_bench` fit."""
    pts = _rulebox_points(recs)
    if not pts or len({dealt for _, _, dealt in pts}) == 1:
        return False
    return _fit_linear([(bench, dealt) for _, bench, dealt in pts]) is None


def _bench_family(recs: list[dict]) -> tuple[str, int] | None:
    """Name the bench-scaling family from the two joined sweeps, or None (REQ-AUDIT-0019). A
    defender-bench slope is additionally REFUSED when the non-{ex} control refutes it."""
    axes = {var: _axis_points(recs, var, swept, pinned) for var, swept, pinned in _BENCH_AXES}
    if any(pts is None for pts in axes.values()):
        return None                                  # an unmeasured axis names nothing
    a, d = _axis_slope(axes["atk_bench"]), _axis_slope(axes["def_bench"])
    if a is None or d is None:
        return None                                  # noisy -> gap ledger
    if d and _bench_control_refutes(recs):
        return None                                  # the count is not the variable that moved
    if a and d:
        return ("both_bench", a) if a == d else None  # unequal: not a family we can express
    if a:
        return "atk_bench", a
    return ("def_bench", d) if d else None


def _records_defender_energy(recs: list[dict]) -> bool:
    """True once the harness RECORDS the defender's attached Energy (REQ-AUDIT-0020) — the switch
    that retires the one-sided energy fit in `_scaler` and makes the join below required."""
    return any(r.get("defenderEnergies") is not None for r in recs)


def _energy_family(recs: list[dict]) -> tuple[str, int] | None:
    """Name the active-Energy family from the two joined sweeps, or None (REQ-AUDIT-0020). Mirrors
    :func:`_bench_family`: equal positive slopes on both sides name the `both_` variable."""
    axes = {var: _axis_points(recs, var, swept, pinned) for var, swept, pinned in _ENERGY_AXES}
    if any(pts is None for pts in axes.values()):
        return None                                  # an unmeasured axis names nothing
    a, d = _axis_slope(axes["energy"]), _axis_slope(axes["def_energy"])
    if a is None or d is None:
        return None                                  # noisy -> gap ledger
    if a and d:
        return ("both_active_energy", a) if a == d else None
    if a:
        return "atk_active_energy", a
    return ("def_active_energy", d) if d else None


def _plain_panel(recs: list[dict]) -> list[dict]:
    """The un-swept, coin-free panel points — one measurement per modifier scenario."""
    return [r for r in recs if not r.get("coin") and not r.get("sweep")
            and not r.get("coinLogs") and r.get("scenario") in _PANEL]


def _fork_board(r: dict) -> tuple:
    """The physical BOARD a fork was measured on. Excludes `sweep`/`step`: those are provenance
    LABELS, and two plans routinely land on the same board."""
    return tuple(_READ[k](r) for k in BOARD_KEYS)


def _coin_bounds(recs: list[dict], st) -> tuple[dict, list[dict]]:
    """Measured coin bounds from the vanilla-panel fork pairs (REQ-AUDIT-0014, ADR-0083 Amendment A).
    A bound is BOARD-SCOPED and ships only when every measured board AGREES."""
    on_panel = [r for r in recs if r.get("coin") and r.get("scenario") == "vanilla"]
    by_board: dict[tuple, dict[str, set]] = {}
    for r in on_panel:
        outcomes = by_board.setdefault(_fork_board(r), {})
        outcomes.setdefault(r["coin"], set()).add(int(r["dealtActive"]))
    pairs = set()
    for outcomes in by_board.values():
        lo_vals, hi_vals = outcomes.get("min"), outcomes.get("max")
        if not lo_vals or not hi_vals:
            continue                         # a half-measured board establishes no bound
        if len(lo_vals) > 1 or len(hi_vals) > 1:
            return {}, []                    # ONE board, two answers: not reproducible, so not a fact
        pairs.add((next(iter(lo_vals)), next(iter(hi_vals))))
    if len(pairs) != 1:
        return {}, []                        # no complete pair, or the boards disagree
    lo, hi = pairs.pop()
    if (st.damageMin, st.damageMax) == (lo, hi):
        return {}, []                                    # parser already had it (REQ-AUDIT-0017)
    return {"damageMin": lo, "damageMax": hi}, on_panel


#: The per-unit signature in a printed-0 attack's own sentence — the WHOLE vocabulary in this pool
#: (Issue #355). Widen this only against the card data, never against memory.
_PER_UNIT_TEXT = "for each"


def _fixed_damage(recs: list[dict], st, text: str = "") -> tuple[dict, list[dict]]:
    """Fixed effect damage — printed 0, one CONSTANT across >=2 modifier scenarios (REQ-AUDIT-0015).
    A printed-0 attack whose own sentence says "for each" is refused outright (Issue #355)."""
    plain = _plain_panel(recs)
    vals = {int(r["dealtActive"]) for r in plain}
    if _PER_UNIT_TEXT in (text or "").lower():
        return {}, []                        # per-unit by its own sentence: one board names nothing
    if not (st.damage == 0 and not st.scaleVar and len(plain) >= 2 and len(vals) == 1
            and vals != {0}):
        return {}, []
    return {"damage": vals.pop()}, plain


def _scaler_evidence(recs: list[dict]) -> list[dict]:
    """Every coin-free PANEL record. The REJECTED and flat axes are kept deliberately — flatness is
    what proves a variable was measured rather than missing (Issue #224)."""
    return [r for r in recs if not r.get("coin") and r.get("scenario") in _EVIDENCE_SCENARIOS]


def _scaler(recs: list[dict], st) -> tuple[dict, list[dict]]:
    """Sweep-fitted visible-state scaler — an exact linear fit the parser missed (REQ-AUDIT-0016).
    JOINED families first, least-ambiguous-first; the one-sided paths are the pre-join fallback."""
    if st.scaleVar:
        return {}, []                                    # parser already named it
    for family in (_bench_family, _rulebox_family, _energy_family):
        named = family(recs)
        if named:
            return {"scaleVar": named[0], "scalePerUnit": named[1]}, _scaler_evidence(recs)
    plain = _plain_panel(recs)
    for var, (scale_var, rec_key) in _SWEEP_VARS.items():
        if var == "energy" and _records_defender_energy(recs):
            continue                                     # the join is available -> it is required
        pts = [(int(r.get(rec_key, 0)), int(r["dealtActive"])) for r in plain
               if r.get("scenario") == "vanilla"]
        pts += [(int(r.get(rec_key, 0)), int(r["dealtActive"])) for r in recs
                if (r.get("sweep") or {}).get("var") == var
                and r.get("scenario") == "vanilla" and not r.get("coin")]
        fit = _fit_linear(pts)
        if fit:
            return {"scaleVar": scale_var, "scalePerUnit": fit[1]}, _scaler_evidence(recs)
    return {}, []


def _apply_rules(recs: list[dict], st, text: str = "") -> tuple[dict, list[dict]]:
    """Rules against one attack -> ``(delta, records that establish it)``. A bound may not ship for
    an attack with a scaler: the legacy evaluator replaces the base, so both counts it twice."""
    bound, bound_ev = _coin_bounds(recs, st)
    fixed, fixed_ev = _fixed_damage(recs, st, text)
    scaler, scaler_ev = _scaler(recs, st)
    if bound and (scaler or st.scaleVar):
        bound, bound_ev = {}, []
    return {**bound, **fixed, **scaler}, [*bound_ev, *fixed_ev, *scaler_ev]


def _evidence_row(r: dict) -> dict:
    return {name: read(r) for name, read in _EVIDENCE_FIELDS}


def _evidence(used: list[dict]) -> list[dict]:
    """De-duplicated, deterministically ordered. `dealt` is part of the key deliberately: identical
    rows collapse, contradicting ones do not."""
    rows = {tuple(str(row[k]) for k in EVIDENCE_KEYS): row
            for row in (_evidence_row(r) for r in used)}
    return [rows[k] for k in sorted(rows)]


@dataclass(frozen=True)
class Derivation:
    """One attack's override delta plus the measurements that establish it."""
    fields: dict
    evidence: list[dict] = field(default_factory=list)


def derive_entries(records: list[dict], parsed: dict,
                   texts: dict[int, str] | None = None) -> dict[int, Derivation]:
    """Measurement records + the parser's AttackStat baseline -> DELTAS and their evidence. A
    copy-attack ("use it as this attack") is excluded: its damage doesn't transfer across boards."""
    by_attack: dict[int, list[dict]] = {}
    for r in records:
        if not r.get("error"):
            by_attack.setdefault(r.get("attackId"), []).append(r)
    out: dict[int, Derivation] = {}
    for aid, recs in by_attack.items():
        st = parsed.get(aid)
        if st is None:
            continue
        text = (texts or {}).get(aid) or ""
        if "use it as this attack" in text:
            continue                                     # copy-attack: measurements don't transfer
        delta, used = _apply_rules(recs, st, text)
        if delta:
            out[aid] = Derivation(delta, _evidence(used))
    return out


def derive_overrides(records: list[dict], parsed: dict,
                     texts: dict[int, str] | None = None) -> dict[int, dict]:
    """The override deltas alone — :func:`derive_entries` without the evidence."""
    return {aid: d.fields for aid, d in derive_entries(records, parsed, texts).items()}


def measured_attacks(records: list[dict]) -> set[int]:
    """Attack ids this run actually MEASURED — an attack nothing was measured for must not have its
    shipped fact retracted."""
    return {r.get("attackId") for r in records if not r.get("error")}


def _coverage(evidence: list[dict] | None) -> set[tuple]:
    """The ``(scenario, sweep axis)`` pairs a fit's evidence measured — the unit a "narrower run" is
    measured in (REQ-PROV-0008). Scenario is required: the non-{ex} control shares its axis."""
    return {(row.get("scenario"), row.get("sweep")) for row in (evidence or [])}


def merge_provenance(derived: dict[int, Derivation], existing: dict[int, dict],
                     measured: set[int], *, prune: bool = False,
                     rule: bool = False) -> tuple[dict, list[str], list[int]]:
    """Fold a derivation run into the committed provenance -> ``(entries, notes, contradicted)``.
    A fit contradicting a ruling, or one a NARROWER run would overwrite, HALTS (REQ-PROV-0008)."""
    entries: dict[int, dict] = {}
    notes: list[str] = []
    contradicted: list[int] = []
    for aid, d in sorted(derived.items()):
        prev = existing.get(aid)
        changed = prev is not None and prev.get("fields") != d.fields
        ruled_over = changed and prev.get("method") == METHOD_TEXT_VERIFIED
        narrowed = changed and prev.get("method") == METHOD_ENGINE_FIT \
            and not _coverage(prev.get("evidence")) <= _coverage(d.evidence)
        if (ruled_over or narrowed) and not rule:
            contradicted.append(aid)
            entries[aid] = prev
            held = "human ruling" if ruled_over else "measured fit"
            why = ("Re-read the card's printed sentence against the measurement"
                   if ruled_over else
                   "This run measured FEWER (scenario, axis) points than the fit it would replace, "
                   f"so it cannot have learned anything new — missing "
                   f"{sorted(_coverage(prev.get('evidence')) - _coverage(d.evidence))}")
            notes.append(f"{aid}: CONTRADICTION — {held} {prev.get('fields')} vs engine fit "
                         f"{d.fields}; the EXISTING entry is KEPT and the fit was NOT written. "
                         f"{why}, or rerun with --rule to accept the fit.")
            continue
        entries[aid] = {"method": METHOD_ENGINE_FIT, "fields": d.fields, "evidence": d.evidence}
        if prev is None:
            notes.append(f"{aid}: NEW engine_fit {d.fields}")
        elif prev.get("fields") != d.fields:
            accepted = " — a human RULING accepted over (--rule)" if ruled_over else ""
            notes.append(f"{aid}: {prev.get('method')} {prev.get('fields')} "
                         f"-> engine_fit {d.fields}{accepted}")
        elif prev.get("method") != METHOD_ENGINE_FIT:
            notes.append(f"{aid}: {prev.get('method')} -> engine_fit (value unchanged, now measured)")
    for aid, prev in sorted(existing.items()):
        if aid in entries:
            continue
        method = prev.get("method")
        if aid not in measured:
            entries[aid] = prev                          # unmeasured: the run has nothing to say
            continue
        if method == METHOD_ENGINE_FIT:
            notes.append(f"{aid}: DROPPED — re-measured and the fit no longer holds "
                         f"(was {prev.get('fields')})")
            continue
        if prune:
            notes.append(f"{aid}: PRUNED — {method} entry the measurements do not establish "
                         f"(was {prev.get('fields')})")
            continue
        notes.append(f"{aid}: KEPT — {method} entry the measurements do not establish; re-rule it "
                     f"or rerun with --prune")
        entries[aid] = prev
    return entries, notes, sorted(contradicted)


ABOUT = ("Provenance for attack_overrides.json (ADR-0108 / Issue #224): what established each "
         "shipped override, and — for an engine fit — the measurement rows that establish it. "
         "reports/attack_audit/ is gitignored, so without this file an override can only be "
         "re-derived by re-driving the engine, never checked. Emitted by "
         "tools/sim/generate_attack_overrides.py in the same pass as the table; "
         "tests/sim/test_attack_override_provenance.py fails when the two disagree.")

#: The vocabulary, written into the emitted file itself, once — not repeated per entry.
METHOD_DOC = {
    METHOD_ENGINE_FIT: "Derived by this generator from engine measurements; `evidence` carries the "
                       "rows it fitted, INCLUDING the rejected/flat axes that prove a variable was "
                       "measured rather than missing.",
    METHOD_TEXT_VERIFIED: "A human read one card's own printed sentence into one attackId. Carries "
                          "an `owner` — the issue that owes the measurement — and a `note` giving "
                          "the text and why the harness cannot fit it today.",
    METHOD_UNAUDITED: "Shipped before provenance was recorded, and the capture that produced it no "
                      "longer exists (reports/attack_audit/ is gitignored). The value is FROZEN: "
                      "the test asserts this exact id set, so a NEW unaudited entry fails rather "
                      "than joining a silent backlog, and changing one of these values means "
                      "re-ruling it here.",
}


def _write_json(path: Path, payload: dict) -> None:
    """Write committed JSON byte-identically on Windows and Linux. Both stores are committed CRLF,
    so the ending is PINNED rather than inherited from `Path.write_text`'s platform translation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
                     .replace("\n", "\r\n").encode("utf-8"))


def load_provenance(path: Path = _PROVENANCE) -> dict:
    """The committed sidecar as ``{"version", "entries": {int: entry}}``. `about`/`methods` are NOT
    read back — this module owns them. An unknown version raises rather than being overwritten."""
    if not path.exists():
        return {"version": PROVENANCE_VERSION, "entries": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    got = payload.get("version")
    if got != PROVENANCE_VERSION:
        raise ValueError(f"{path.name} is version {got}, this generator writes "
                         f"{PROVENANCE_VERSION} — migrate it rather than overwriting it")
    return {"version": got,
            "entries": {int(k): v for k, v in (payload.get("entries") or {}).items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate attack_overrides.json + its provenance "
                                             "sidecar from audit measurements.")
    ap.add_argument("--measurements", type=Path, default=_MEASUREMENTS)
    ap.add_argument("--out", type=Path, default=_OUT)
    ap.add_argument("--provenance", type=Path, default=_PROVENANCE)
    ap.add_argument("--prune", action="store_true",
                    help="drop a measured human-ruled entry the measurements do not establish "
                         "(default: keep it and report it)")
    ap.add_argument("--rule", "--accept-contradiction", dest="rule", action="store_true",
                    help="accept an engine fit that CONTRADICTS a text_verified ruling, "
                         "overwriting it (default: keep the ruling, report it, exit non-zero)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    payload = json.loads(args.measurements.read_text(encoding="utf-8"))
    records = payload.get("measurements", payload) if isinstance(payload, dict) else payload

    from cg.api import all_attack
    from common.scouting.provider import build_attack_stats
    attacks = all_attack()
    derived = derive_entries(records, build_attack_stats(attacks),
                             texts={a.attackId: a.text or "" for a in attacks})

    prov = load_provenance(args.provenance)
    entries, notes, contradicted = merge_provenance(derived, prov["entries"],
                                                    measured_attacks(records),
                                                    prune=args.prune, rule=args.rule)
    counts = {m: sum(1 for e in entries.values() if e.get("method") == m) for m in METHODS}
    print(f"{len(derived)} attacks fitted this run; table holds {len(entries)} "
          f"({', '.join(f'{n} {m}' for m, n in counts.items())})")
    for note in notes:
        print(f"  {note}")
    if not notes:
        print("  (no change to any shipped override)")
    # Still WRITTEN on a contradiction: the ruling is kept, so what lands is correct by
    # construction. The signal is the non-zero EXIT CODE below, not a refusal to write.
    if not args.dry_run:
        _write_json(args.out, {str(k): e["fields"] for k, e in sorted(entries.items())})
        _write_json(args.provenance, {"version": PROVENANCE_VERSION, "about": ABOUT,
                                      "methods": dict(METHOD_DOC),
                                      "entries": {str(k): e for k, e in sorted(entries.items())}})
        print(f"-> {args.out}\n-> {args.provenance}")
    if contradicted:
        print(f"FAIL: {len(contradicted)} human ruling(s) contradicted by this run's measurements "
              f"and KEPT: {contradicted}. Re-read each card's printed sentence against the "
              f"evidence above; rerun with --rule only to accept the fit over the ruling.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
