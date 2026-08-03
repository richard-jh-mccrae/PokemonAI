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

**Every entry carries its provenance** (ADR-0108, Issue #224). `reports/attack_audit/` is
gitignored, so a shipped override used to be uncheckable against its own evidence — which is
precisely how 274 sat wrong and unseen. The generator therefore emits a committed SIDECAR,
`attack_overrides.provenance.json`, in the SAME pass as the table: one `attackId` -> how the fact
was established (`engine_fit` / `text_verified` / `unaudited`), the exact override value, and for a
fit the measurement rows that justify it — the rejected, FLAT axes included, since flatness is what
proves a variable was measured rather than missing. `tests/sim/test_attack_override_provenance.py`
fails when the two files disagree, so they cannot drift.

The merge rule: **the generator may retract what it authored; it may not retract what a human
ruled.** A previously `engine_fit` entry the fresh measurements no longer support is dropped (that
is exactly the 274 outcome); an unmeasured attack, a `text_verified` ruling, and an `unaudited`
legacy value are preserved and REPORTED, so a partial recapture can never silently regress the
shipped table. `--prune` opts into dropping the last of those. A measurement that CONTRADICTS a
ruling is a HALT, not a note (REQ-PROV-0008): the ruling is kept, the run exits non-zero, and
`--rule` is the explicit opt-in — see `merge_provenance` for the two shipped entries this was
measured on.

    python tools/sim/generate_attack_overrides.py             # writes the table + the sidecar
    python tools/sim/generate_attack_overrides.py --dry-run   # print, don't write
    python tools/sim/generate_attack_overrides.py --rule      # accept a fit OVER a human ruling

Requirements:
    REQ-PROV-0001  Table and sidecar cover exactly the same attacks; every row declares a `method`
                   from the closed vocabulary (`engine_fit` / `text_verified` / `unaudited`).
    REQ-PROV-0002  An `engine_fit` row carries the measurement records that establish it — the
                   REJECTED and flat axes included, and the modifier-panel points alongside the
                   swept ones. A row that was not fitted carries no evidence.
    REQ-PROV-0003  A row's recorded `fields` are the value actually shipped — the freeze.
    REQ-PROV-0004  The unaudited debt may only SHRINK; a new unaudited override is a failure.
    REQ-PROV-0005  A `text_verified` row names the issue that owes its measurement.
    REQ-PROV-0006  Table and sidecar are emitted in ONE pass, from one merged result, so they
                   cannot describe different derivations.
    REQ-PROV-0007  The generator may retract what it AUTHORED (a fit the fresh measurements no
                   longer support is dropped); never what a human RULED (`--prune` opts in).
    REQ-PROV-0008  A fit that CONTRADICTS a `text_verified` ruling is not written: the ruling is
                   kept, both readings are named, and the run exits non-zero (`--rule` opts in).
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
_OUT = _REPO / "src" / "common" / "attack_overrides.json"
_PROVENANCE = _REPO / "src" / "common" / "attack_overrides.provenance.json"
_SWEEP_VARS = {"hand": ("atk_hand", "myHandSize"), "energy": ("atk_active_energy", "attackerEnergies")}
_PANEL = ("vanilla", "weak", "resist", "prevent_ex")
# The bench family is named by JOINING two single-variable sweeps, never by one (REQ-AUDIT-0019):
# (sweep var, the seat it moves, the seat it pins).
_BENCH_AXES = (("atk_bench", "attackerBench", "defenderBench"),
               ("def_bench", "defenderBench", "attackerBench"))

#: How a shipped override's value was established (REQ-PROV-0001). A closed vocabulary, because the
#: whole point is that "measured" and "read off the card" and "nobody knows any more" must not look
#: alike in the file — which is the state Issue #224 found the table in.
METHOD_ENGINE_FIT = "engine_fit"
METHOD_TEXT_VERIFIED = "text_verified"
METHOD_UNAUDITED = "unaudited"
METHODS = (METHOD_ENGINE_FIT, METHOD_TEXT_VERIFIED, METHOD_UNAUDITED)

#: Bumped only when an entry's SHAPE changes; the reader fails loudly rather than mis-parsing.
PROVENANCE_VERSION = 1

#: The evidence row, as ``(field, reader)`` — the issue's own list (swept variable, swept value,
#: pinned values, dealtActive, scenario) plus `coin`, without which a bound entry's fork pair is two
#: identical-looking rows. ONE source for the row's shape AND for the dedup key: stating the field
#: names twice would let a new field join the row while `_evidence` silently kept ignoring it,
#: collapsing exactly the rows this sidecar exists to keep apart.
_EVIDENCE_FIELDS = (
    ("scenario", lambda r: r.get("scenario")),
    ("sweep", lambda r: (r.get("sweep") or {}).get("var")),
    ("step", lambda r: (r.get("sweep") or {}).get("step")),
    ("coin", lambda r: r.get("coin")),
    ("atkBench", lambda r: r.get("attackerBench")),
    ("defBench", lambda r: r.get("defenderBench")),
    ("energies", lambda r: r.get("attackerEnergies")),
    ("hand", lambda r: r.get("myHandSize")),
    ("dealt", lambda r: r.get("dealtActive")),
)
#: The row's keys, in order. Public so the provenance gate checks the shape it is actually given.
EVIDENCE_KEYS = tuple(name for name, _ in _EVIDENCE_FIELDS)
#: Everything the harness CONTROLS — the row minus the one thing it measures. Two rows agreeing here
#: and disagreeing on `dealt` are a contradiction, not a duplicate.
CONTROLLED_KEYS = EVIDENCE_KEYS[:-1]
_READ = dict(_EVIDENCE_FIELDS)
#: Which sweep PLAN produced a row — a provenance label, not board state. Two plans routinely land
#: on the same board (the panel point and the `atk_bench` step-1 point both pin the benches at 1).
_LABEL_KEYS = ("sweep", "step")
#: The physical board a measurement was taken on: the controlled state with the labels removed, and
#: with `coin` removed because the two fork outcomes ARE the same board.
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
    """Controlled ``(count, dealt)`` points for ONE bench axis, or None when the axis is not
    usable. Takes the vanilla, coin-free records that either carry no sweep (the panel point,
    already pinned to the reference) or carry this axis's sweep.

    Rejects unless the PINNED seat is provably constant across them — read off the records, not
    trusted from the plan. Bench patience can run out and a seat can miss its target; an axis
    where the other seat drifted is not single-variable, and trusting one is precisely how the
    spurious 274 fit happened.
    """
    def _on_axis(r):
        """No sweep at all (the panel point, already pinned to the reference) or THIS axis's."""
        return (r.get("sweep") or {}).get("var", sweep_var) == sweep_var

    sel = [r for r in recs
           if r.get("scenario") == "vanilla" and not r.get("coin") and not r.get("coinLogs")
           and _on_axis(r)]
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


def _plain_panel(recs: list[dict]) -> list[dict]:
    """The un-swept, coin-free panel points — one measurement per modifier scenario."""
    return [r for r in recs if not r.get("coin") and not r.get("sweep")
            and not r.get("coinLogs") and r.get("scenario") in _PANEL]


def _fork_board(r: dict) -> tuple:
    """The physical BOARD a fork was measured on.

    Deliberately excludes `sweep`/`step`. Those are provenance LABELS — which plan produced the row
    — not state, and two plans routinely land on the same board: the panel point pins both benches
    at ``_BENCH_REF = 1`` and the `atk_bench` step-1 sweep point pins them at 1 as well. Keying on
    the label would file those as two boards and let a disagreement between them read as ordinary
    board sensitivity, when it is the same board answering twice.

    A `min` and its `max` come from ONE forked position (``_coin_fork`` walks both outcomes of one
    pre-attack observation, and ``measure_attack`` stamps all three records from one ``common``
    dict), so a pair always shares this tuple exactly.
    """
    return tuple(_READ[k](r) for k in BOARD_KEYS)


def _coin_bounds(recs: list[dict], st) -> tuple[dict, list[dict]]:
    """Measured coin bounds from the vanilla-panel fork pairs (REQ-AUDIT-0014, ADR-0083 Amendment A).

    Vanilla only: a fork taken on the weak or resist panel has the modifier baked into the dealt
    number, so its bounds are not the attack's own.

    **A bound is BOARD-SCOPED.** `merge_records` keys a measurement on its sweep point, so an attack
    audited with `--sweep` legitimately holds several `coin="max"` records on the vanilla panel — one
    per board — and for a board-sensitive attack they legitimately differ. Collapsing them into
    ``{coin: record}`` kept whichever the dict landed on and shipped it as the attack's own bound:
    the 274 defect one field over, attributing variation to the one variable it recorded while
    another it did not control had also moved.

    So the pairs are grouped by board, and a bound ships only when they AGREE:

    * one board measured -> that bound;
    * several boards, all agreeing -> that bound. Corroboration, not a coincidence to discard: this
      is ADR-0083 §3's flat-axis argument applied to the bound. Refusing here would throw away the
      strongest evidence the harness can produce.
    * several boards disagreeing -> **nothing**. The bound is a function of the board (879 "flip a
      coin for each {D} Pokémon you have in play", 1256 "for each Energy attached to this Pokémon"),
      and the override table has no form that says so. Naming one board's number as the attack's is
      the arbitrary survivor with a tidier implementation. Gap ledger.

    Evidence is every vanilla fork record, so a reader sees the boards the bound was corroborated
    across rather than only the pair that won.
    """
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


#: The per-unit signature in a printed-0 attack's own sentence. `for each` is the WHOLE vocabulary
#: in this pool, read at source rather than recalled: of 381 printed-0 attacks carrying text, 124
#: announce a per-unit count and every one of them says "for each" — no "for every", no "times the
#: number of". Widen this only against the card data, never against memory.
_PER_UNIT_TEXT = "for each"


def _fixed_damage(recs: list[dict], st, text: str = "") -> tuple[dict, list[dict]]:
    """Fixed effect damage — printed 0, one CONSTANT across >=2 modifier scenarios
    (REQ-AUDIT-0015). The whole panel is the evidence: cross-scenario agreement is the claim, so
    a record that disagreed is exactly what a reader needs to see it did not happen.

    **A printed-0 attack whose own sentence says "for each" is refused outright** (Issue #355). Its
    damage is a COUNT times a per-unit number, and the modifier panel is ONE board — so agreement
    across the panel measures that board's count, not the attack. Freezing it as a flat `damage`
    ships an over-prediction the moment the count is lower, which is the soundness class
    `ci_audit_gate.py` exists to fail; and it ships it with no `scaleVar` at all, so nothing
    downstream can tell it is board-dependent. 425 Tenacious Tail escapes this only by ACCIDENT —
    `prevent_ex` zeroes it (vanilla 120, `prevent_ex` 0), so its panel disagrees and the constant
    rule rejects on its own. The shipped `unaudited` entries 651 (`damage` 80, printed "40 damage
    for each Pokemon in play that has 'Koffing' or 'Weezing' in its name") and 708 are what this
    class looks like once it is in the table: one board's answer, frozen, unmarked.

    Reading the printed text to suppress a derivation is this module's established idiom, not a new
    one — `derive_entries` already excludes a copy-attack on ``"use it as this attack" in text``.
    The conservative direction is silence: an over-refused constant lands on the gap ledger, where
    a measurement that established nothing belongs.
    """
    plain = _plain_panel(recs)
    vals = {int(r["dealtActive"]) for r in plain}
    if _PER_UNIT_TEXT in (text or "").lower():
        return {}, []                        # per-unit by its own sentence: one board names nothing
    if not (st.damage == 0 and not st.scaleVar and len(plain) >= 2 and len(vals) == 1
            and vals != {0}):
        return {}, []
    return {"damage": vals.pop()}, plain


def _scaler_evidence(recs: list[dict]) -> list[dict]:
    """Every coin-free PANEL record — the winning axis, the rejected ones, and the modifier points.

    Three things a reader needs, and only the first is what the fit consulted:

    * The winning axis, obviously.
    * The **rejected** axes. A flat energy or hand axis is what proves those variables were measured
      and do not move the damage, and their ABSENCE is what let a combined-bench scaler fit hand
      size (274 Torcherto). Keeping only the fitted points would preserve the conclusion and discard
      the reason it is sound — the auditability gap Issue #224 exists to close, one level down.
    * The **modifier** panel (weak / resist / prevent_ex). The fit is vanilla-only, so these
      establish nothing about the variable — they confirm the oracle's modifier ORDER around it
      (274's weak row reads 200 = (60+40)x2; prevent_ex zeroes 371 as an ex vs Crustle). Issue #224
      preserved them as part of "the evidence for the two entries that changed", so dropping them
      would lose part of the last surviving copy.
    """
    return [r for r in recs if not r.get("coin") and r.get("scenario") in _PANEL]


def _scaler(recs: list[dict], st) -> tuple[dict, list[dict]]:
    """Sweep-fitted visible-state scaler — an exact linear fit the parser missed (REQ-AUDIT-0016).

    The BENCH family goes first: it is the only one whose variable takes two sweeps to name, and
    trying it ahead of the single-variable families keeps a bench scaler from being mis-named off a
    historical (bench-unpinned) hand or energy sweep.
    """
    if st.scaleVar:
        return {}, []                                    # parser already named it
    bench = _bench_family(recs)
    if bench:
        return {"scaleVar": bench[0], "scalePerUnit": bench[1]}, _scaler_evidence(recs)
    plain = _plain_panel(recs)
    for var, (scale_var, rec_key) in _SWEEP_VARS.items():
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
    """Every derivation rule against one attack -> ``(delta, records that establish it)``.

    Each rule is ``(records, AttackStat) -> (fields, used)``: the override delta it establishes AND
    the measurements that establish it. Returning the evidence alongside the value is what makes
    provenance a BY-PRODUCT of deriving rather than a second, drift-prone description of it.

    Called out one by one rather than looped, because the rules are not independent — the bound and
    the scaler INTERACT, and a loop cannot say so.

    **A measured bound may not ship for an attack that HAS a scaler, whoever named it.**
    ``common/strategy/damage.py``'s `compute_active_damage` sets ``dmg = damageMin/damageMax`` — the
    bound REPLACES the base term — and only then adds ``scalePerUnit x count``. A bound measured on
    a board where the scaler contributes already contains that contribution, so shipping both adds
    it twice: an OVER-prediction, the one class `ci_audit_gate.py` exists to fail (damage the closed
    form promises that the engine will not deal -> phantom KO).

    The test is the EFFECTIVE scaler — ``st.scaleVar`` (the parser's) or this run's fit — because
    the oracle adds the scaling term whenever `scaleVar` is set and does not care where it came
    from. Testing only the fit was the first version of this guard and it missed the commoner case
    by construction: `_scaler` returns nothing when the parser already named the variable, so a
    parser-named scaler plus a fork pair sailed straight through. Measured on a probe: a printed-60
    `atk_hand`/20 attack with a fork pair measured at hand 6 shipped ``damageMax 100`` and the
    oracle then read 160 at hand 3.

    The scaler survives because it is base-relative and sound; the bound is dropped, and the attack
    keeps the text parser's bounds, which are read off the printed sentence and are base-relative
    too. Recovering the base as ``dealt - scalePerUnit x count`` was rejected: it compounds one
    inference on another, and this generator's discipline is that an ambiguity emits silence.

    A refused bound leaves NO trace in the provenance sidecar, deliberately: that file's contract is
    that evidence justifies what SHIPPED, and a refused bound did not. The gap ledger
    (`diff_attack_audit.py`) is where a measurement that established nothing belongs.
    """
    bound, bound_ev = _coin_bounds(recs, st)
    fixed, fixed_ev = _fixed_damage(recs, st, text)
    scaler, scaler_ev = _scaler(recs, st)
    if bound and (scaler or st.scaleVar):
        bound, bound_ev = {}, []
    return {**bound, **fixed, **scaler}, [*bound_ev, *fixed_ev, *scaler_ev]


def _evidence_row(r: dict) -> dict:
    """One measurement, distilled to what justifies a fit — the swept variable and its value, the
    pinned values, the scenario, and what the engine actually dealt."""
    return {name: read(r) for name, read in _EVIDENCE_FIELDS}


def _evidence(used: list[dict]) -> list[dict]:
    """De-duplicated, deterministically ordered evidence rows.

    Two rules can consult the same record (the panel point feeds both the fixed-damage and the
    scaler paths), and a regenerated sidecar that differs only in row ORDER would read as a real
    change in every review. Keying on the WHOLE row fixes both — and `dealt` is deliberately part
    of that key: two measurements agreeing on every controlled variable and disagreeing on the
    damage is a contradiction, and collapsing it to whichever came last would silently discard the
    one record a reader most needs to see. Identical rows collapse; contradicting ones do not.
    """
    rows = {tuple(str(row[k]) for k in EVIDENCE_KEYS): row
            for row in (_evidence_row(r) for r in used)}
    return [rows[k] for k in sorted(rows)]


@dataclass(frozen=True)
class Derivation:
    """One attack's override delta together with the measurements that establish it."""
    fields: dict
    evidence: list[dict] = field(default_factory=list)


def derive_entries(records: list[dict], parsed: dict,
                   texts: dict[int, str] | None = None) -> dict[int, Derivation]:
    """Pure derivation: measurement records + the parsed AttackStat table -> deltas AND evidence.

    Args:
        records: audit measurement records (``audit_attacks`` shapes).
        parsed: ``{attackId: AttackStat}`` as the text parsers built it (the baseline).
        texts: optional ``{attackId: text}`` — a COPY-attack ("use it as this attack") is
            excluded from bound generation: its measured damage is the copied attack's, which
            is defender-dependent and doesn't transfer across boards.

    Returns:
        ``{attackId: Derivation}`` — only fields the measurements establish and the parser missed
        (deltas, REQ-AUDIT-0017), each paired with the records that justify them (REQ-PROV-0002).
    """
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
    """Attack ids this run actually MEASURED — a run that only ledgered errors measured nothing,
    and an attack nothing was measured for must not have its shipped fact retracted."""
    return {r.get("attackId") for r in records if not r.get("error")}


def merge_provenance(derived: dict[int, Derivation], existing: dict[int, dict],
                     measured: set[int], *, prune: bool = False,
                     rule: bool = False) -> tuple[dict, list[str], list[int]]:
    """Fold a derivation run into the committed provenance, without regressing an unmeasured fact.

    **The generator may retract what it authored; it may not retract what a human ruled.** A
    previously ``engine_fit`` entry the fresh measurements no longer support is dropped — that is
    exactly the right outcome for 274, whose shipped `atk_hand` fit today's fitter would not emit.
    A ``text_verified`` ruling and an ``unaudited`` legacy value are the generator's to report, not
    to overrule: dropping them on a partial run would silently un-price attacks (425 Tenacious Tail
    reverts to dealing ZERO, which is a blind spot rather than an under-read), and the harness
    provably cannot fit some of them on today's axes. ``prune`` opts into dropping them anyway.

    **A measurement that CONTRADICTS a ruling halts** (REQ-PROV-0008, Issue #355). The rule above
    used to have a hole exactly the size of the case it was written for: the write happened
    unconditionally and the disagreement became a `notes.append`, while the protective ``KEPT`` /
    ``--prune`` branch below opens ``if aid in entries: continue`` — so it could never see an attack
    the run had derived something for. It fired only when the run derived NOTHING, which is the one
    situation in which no ruling is under threat. Measured, on two shipped entries. `pick_panel`
    takes the highest-HP ability-free basic, which for 425's attacker (306 Dudunsparce ex) is card
    1056 Mega Zygarde ex — ``megaEx=True``, and a Mega Evolution Pokemon ex IS a Pokemon ex
    (`docs/rulebook.txt` L337, which is why `cgpy/damage.py:56-58` counts ``ex or megaEx``). So
    every body the panel puts on that bench is an {ex}, `def_ex_in_play` is perfectly collinear with
    `def_bench`, and 425's ruling was overwritten with `def_bench`/60 — 60 damage per plain Basic on
    the opponent's bench, invented, and straight into `state_value`'s `threat` and `survival` terms.
    120's `both_active_energy` went the same way to `atk_active_energy`, because its own panel's
    defender holds no Energy and the two variables are then indistinguishable at every point.

    The ruling therefore WINS by default and the fit is not written; ``rule`` (the ``--rule`` flag,
    mirroring ``--prune``'s "the human has looked at this") opts into accepting it. The test is the
    VALUE, not the method: a fit that reproduces the ruling is the debt being paid off as intended
    (REQ-PROV-0004), and halting on that too would make ``--rule`` the routine flag — i.e. no guard.

    A contradiction is deliberately NOT recorded in the sidecar. That file's contract is that its
    evidence justifies what SHIPPED, and a refused derivation did not ship — the same ruling
    `_apply_rules` already states for a refused coin bound, whose trace belongs on
    `diff_attack_audit.py`'s gap ledger rather than here. What makes a contradiction impossible to
    absorb silently is the returned id list and the non-zero exit it drives, not a durable row.

    Args:
        derived: this run's :func:`derive_entries` output.
        existing: the committed ``{attackId: entry}`` provenance rows.
        measured: :func:`measured_attacks` — what this run can speak about at all.
        prune: drop a measured, human-ruled entry the run could not reproduce.
        rule: accept a fit that contradicts a ``text_verified`` ruling, overwriting it.

    Returns:
        ``(entries, notes, contradicted)`` — the merged provenance rows, the human-readable log of
        every entry that changed, was dropped, or was kept, and the sorted attack ids whose ruling
        the run contradicted and did NOT overwrite. The ids are returned rather than re-derived by
        the caller for the reason the evidence rides along with the value elsewhere in this module:
        a second, separate description of the same traversal is a description that can drift.
    """
    entries: dict[int, dict] = {}
    notes: list[str] = []
    contradicted: list[int] = []
    for aid, d in sorted(derived.items()):
        prev = existing.get(aid)
        ruled_over = prev is not None and prev.get("method") == METHOD_TEXT_VERIFIED \
            and prev.get("fields") != d.fields
        if ruled_over and not rule:
            contradicted.append(aid)
            entries[aid] = prev
            notes.append(f"{aid}: CONTRADICTION — human ruling {prev.get('fields')} vs engine fit "
                         f"{d.fields}; the RULING is KEPT and the fit was NOT written. Re-read the "
                         f"card's printed sentence against the measurement, or rerun with --rule "
                         f"to accept the fit.")
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

#: The vocabulary, written into the file itself so a reader never has to leave it to know what a
#: row CLAIMS. Stated once here rather than repeated per entry — 111 identical `note` strings would
#: be noise, and noise is what stops a file being read.
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
    """Write committed JSON byte-identically on Windows and Linux.

    `Path.write_text` translates "\\n" to the platform newline, so the same generator run produces
    a different file on each OS and a regenerate reads as a whole-file rewrite. Both stores here are
    committed CRLF, so the ending is pinned rather than inherited (CLAUDE.md: binary-safe writes to
    committed data).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
                     .replace("\n", "\r\n").encode("utf-8"))


def load_provenance(path: Path = _PROVENANCE) -> dict:
    """The committed sidecar as ``{"version", "entries": {int: entry}}``.

    The `about` and `methods` prose is deliberately NOT read back. This module owns it, so a
    regenerate re-emits ``ABOUT``/``METHOD_DOC`` rather than echoing whatever is on disk — echoing
    would let the file's own description of the vocabulary drift away from the vocabulary, in the
    one file built to make drift impossible.

    A missing file reads as empty — bootstrapping is a real state. A version this generator does
    not know raises: silently re-emitting a shape it cannot read is how a sidecar would lose the
    very entries it exists to preserve.
    """
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
    # The files are still WRITTEN on a contradiction. The ruling is kept, so what lands is correct
    # by construction, and every other attack's legitimate re-measurement survives the run —
    # whereas refusing to write would leave `--rule`, the flag that accepts the wrong number, as
    # the only way to get any output at all. The signal is the EXIT CODE: informative, per ADR-0032
    # (96.6% of 9.5k measurements predict exactly, so a disagreement is ~1 in 30 and worth a human),
    # and non-zero so a scripted regeneration stops before it commits rather than after.
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
