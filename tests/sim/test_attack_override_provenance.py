"""**A shipped override is checkable against its own evidence** — `attack_overrides.json` against
`attack_overrides.provenance.json` (ADR-TEMP-224, Issue #224).

`reports/attack_audit/` is gitignored, so before this sidecar a shipped override could only be
*re-derived* by re-driving the engine, never *checked*. That is not a theoretical gap. Attack 274
(Skeledirge, Torcherto) shipped `{"scaleVar": "atk_hand", "scalePerUnit": 5}` — an attack that does
not scale on hand size at all. The fitter is conservative by construction (exact integer fit, zero
residuals, positive slope, >=3 points) and it *still* emitted that, because bench was a variable the
harness neither swept nor recorded, so hand size was the only thing it could fit. Nobody could see
it, because the measurements behind the entry were not in the repo.

These are structural checks over two committed files — no engine, no measurements. Prior art for the
style: `tests/test_adr_index.py` (a repo-shape invariant asserted straight off the filesystem).

Requirements:
    REQ-PROV-0001  Every shipped override has exactly one provenance row and every row a shipped
                   override; every row's `method` is in the closed vocabulary.
    REQ-PROV-0002  An `engine_fit` row carries the measurement rows that establish it; a row that
                   was NOT fitted carries no evidence and says what it is instead.
    REQ-PROV-0003  A row's recorded `fields` equal the shipped table entry EXACTLY — the freeze.
    REQ-PROV-0004  The `unaudited` id set may only SHRINK. A new unaudited entry fails.
    REQ-PROV-0005  A `text_verified` row names the issue that owes its measurement.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim.generate_attack_overrides import (ABOUT, CONTROLLED_KEYS, EVIDENCE_KEYS, METHOD_DOC,
                                           METHOD_ENGINE_FIT, METHOD_TEXT_VERIFIED,
                                           METHOD_UNAUDITED, METHODS, PROVENANCE_VERSION,
                                           load_provenance)

REPO = Path(__file__).resolve().parents[2]
_TABLE = REPO / "src" / "common" / "attack_overrides.json"
_SIDECAR = REPO / "src" / "common" / "attack_overrides.provenance.json"

#: The 111 entries that were already shipped when provenance became a requirement (2026-08-02). The
#: capture that produced each of them is gone — `reports/attack_audit/measurements.json` exists
#: nowhere — so they are recorded as unaudited rather than re-derived, and FROZEN at that.
#:
#: Asserted as a SUBSET below, never an equality, and the asymmetry is the whole gate: backfilling
#: one (unaudited -> engine_fit, once a recapture lands) shrinks the set and passes with no edit to
#: this file, while a NEW unaudited override fails — so "nobody knows where this number came from"
#: be added silently. Re-driving the pool would change shipped values rather than merely document
#: them (ADR-0083's Consequences: the old measurements are stale for bench-sensitive attacks), which
#: is why the debt is recorded rather than paid in one go.
UNAUDITED_AT_BOOTSTRAP = frozenset({
    6, 25, 52, 55, 64, 75, 81, 91, 126, 138, 173, 177, 195, 226, 228, 244, 259, 261, 326, 350,
    352, 363, 364, 391, 404, 408, 469, 486, 498, 505, 533, 551, 578, 595, 603, 630, 651, 657,
    662, 664, 668, 678, 684, 686, 708, 717, 727, 728, 733, 747, 758, 790, 792, 805, 833, 835,
    843, 879, 887, 889, 894, 951, 973, 975, 1003, 1013, 1016, 1037, 1051, 1054, 1056, 1059,
    1067, 1079, 1081, 1087, 1092, 1125, 1135, 1137, 1153, 1178, 1184, 1205, 1213, 1229, 1256,
    1260, 1266, 1270, 1271, 1309, 1319, 1328, 1335, 1346, 1366, 1369, 1382, 1428, 1439, 1453,
    1458, 1470, 1492, 1493, 1498, 1526, 1528, 1547, 1548,
})


@pytest.fixture(scope="module")
def table() -> dict[int, dict]:
    return {int(k): v for k, v in json.loads(_TABLE.read_text(encoding="utf-8")).items()}


@pytest.fixture(scope="module")
def entries() -> dict[int, dict]:
    return load_provenance(_SIDECAR)["entries"]


@pytest.mark.req("REQ-PROV-0001")
def test_the_sidecar_and_the_table_cover_exactly_the_same_attacks(table, entries):
    """The check that would have flagged 274 immediately: an override with no provenance row is an
    override nobody can check. The reverse also fails — an orphan row describes a fact that is not
    shipped, which is a sidecar drifting away from the thing it documents."""
    assert sorted(set(table) - set(entries)) == [], "shipped override with NO provenance row"
    assert sorted(set(entries) - set(table)) == [], "provenance row for an override that is not shipped"


@pytest.mark.req("REQ-PROV-0001")
def test_every_row_declares_a_method_from_the_closed_vocabulary(entries):
    """`measured`, `read off the card`, and `nobody knows any more` must not look alike in the file
    — looking alike is the state Issue #224 found the table in."""
    bad = {aid: e.get("method") for aid, e in entries.items() if e.get("method") not in METHODS}
    assert bad == {}, f"method must be one of {METHODS}"


@pytest.mark.req("REQ-PROV-0003")
def test_each_row_records_the_value_that_is_actually_shipped(table, entries):
    """THE FREEZE. The row carries the override's real value, so editing a shipped number without
    touching its provenance fails here — including for the 111 legacy entries, whose whole status is
    "this exact value, on no surviving evidence". A hash would do the same job and show the reader
    two opaque hex strings; the value itself shows them what moved."""
    drifted = {aid: (entries[aid].get("fields"), table[aid])
               for aid in sorted(set(table) & set(entries))
               if entries[aid].get("fields") != table[aid]}
    assert drifted == {}, "provenance records a value the table does not ship (row, table)"


@pytest.mark.req("REQ-PROV-0002")
def test_an_engine_fit_carries_the_measurements_that_establish_it(entries):
    """A fit whose evidence is empty is exactly the pre-Issue #224 state with a label on it."""
    for aid, e in sorted(entries.items()):
        if e.get("method") != METHOD_ENGINE_FIT:
            continue
        assert e.get("evidence"), f"{aid}: engine_fit with no evidence rows"
        for row in e["evidence"]:
            assert set(row) == set(EVIDENCE_KEYS), f"{aid}: malformed evidence row"
            assert row["dealt"] is not None, f"{aid}: an evidence row with no measured damage"


@pytest.mark.req("REQ-PROV-0002")
def test_a_scaler_fit_keeps_a_measured_FLAT_axis_not_just_the_axes_that_won(entries):
    """The rejected axes are load-bearing, not filler — and the assertion has to say so, or the test
    passes on evidence that proves nothing.

    Counting axes is not enough: a `both_bench` fit wins on `atk_bench` AND `def_bench`, so "at
    least two axes" is satisfied by the two winners alone, and evidence stripped of the flat
    hand/energy rows would sail through. What actually carries the argument is a measured axis that
    is FLAT: 274's hand rows read 100/100 *because the benches are pinned across them*, and that
    flatness is the whole reason hand size is unfittable now. Its ABSENCE is what let 274 ship
    `atk_hand` in the first place — a variable no measurement supported, in a record that would have
    looked complete.
    """
    for aid, e in sorted(entries.items()):
        if e.get("method") != METHOD_ENGINE_FIT or "scaleVar" not in e.get("fields", {}):
            continue
        dealt_by_axis: dict[str, set] = {}
        for row in e["evidence"]:
            if row["sweep"]:
                dealt_by_axis.setdefault(row["sweep"], set()).add(row["dealt"])
        flat = sorted(ax for ax, dealt in dealt_by_axis.items() if len(dealt) == 1)
        assert len(dealt_by_axis) >= 2, (
            f"{aid}: a scaler fitted from ONE axis. One sweep cannot separate atk_bench from "
            f"both_bench (ADR-0083 §3) — saw {sorted(dealt_by_axis)}")
        assert flat, (
            f"{aid}: every measured axis MOVES, so nothing here shows a variable was measured and "
            f"ruled out. Either the flat axes were dropped from the record, or the fit is ambiguous "
            f"across {sorted(dealt_by_axis)} and should not have shipped")


@pytest.mark.req("REQ-PROV-0002")
def test_no_fit_ships_on_evidence_that_contradicts_itself(entries):
    """Two measurements agreeing on every controlled variable and disagreeing on the damage do not
    establish a fact — they show the fact is not established. Vacuous today (no shipped fit has a
    contradicting pair) and deliberately so: it bites the day a recapture produces one, which is the
    day someone would otherwise ship an arbitrary survivor of a collapse. `_coin_bounds` in
    particular still takes its pair from a dict keyed on `coin` alone, so forks measured at
    different sweep points overwrite each other there — the derived value is an arbitrary survivor,
    and this is the check that refuses to let one ship quietly."""
    for aid, e in sorted(entries.items()):
        if e.get("method") != METHOD_ENGINE_FIT:
            continue
        seen: dict[tuple, int] = {}
        for row in e["evidence"]:
            key = tuple(row[k] for k in CONTROLLED_KEYS)
            assert seen.setdefault(key, row["dealt"]) == row["dealt"], (
                f"{aid}: two measurements on identical controlled state disagree "
                f"({seen[key]} vs {row['dealt']}) — this override's own evidence refutes it")


@pytest.mark.req("REQ-PROV-0002")
def test_a_row_that_was_not_fitted_says_so_instead_of_showing_evidence(entries):
    """`text_verified` and `unaudited` are claims ABOUT the absence of a fit. Evidence attached to
    one would read as measurement it does not have."""
    for aid, e in sorted(entries.items()):
        if e.get("method") == METHOD_ENGINE_FIT:
            continue
        assert e.get("evidence") == [], f"{aid}: {e.get('method')} row carrying fit evidence"


@pytest.mark.req("REQ-PROV-0005")
def test_a_text_verified_row_names_the_issue_that_owes_its_measurement(entries):
    """A human reading a card's printed sentence is a legitimate way to establish a fact and a debt
    at the same time. The debt needs an OWNER, or it is a TODO nobody holds — the four entries here
    are owed by Issue #275, which builds the axes that can actually separate their variables."""
    for aid, e in sorted(entries.items()):
        if e.get("method") != METHOD_TEXT_VERIFIED:
            continue
        assert e.get("owner"), f"{aid}: text_verified with no owning issue"
        assert e.get("note"), f"{aid}: text_verified with no printed text to check it against"


@pytest.mark.req("REQ-PROV-0004")
def test_the_unaudited_set_may_only_shrink(entries):
    """The teeth. Backfilling is welcome and free — flip a row to `engine_fit` and this passes with
    no edit here. Adding a NEW override nobody can check fails, which is the thing that used to be
    indistinguishable from adding an audited one."""
    unaudited = {aid for aid, e in entries.items() if e.get("method") == METHOD_UNAUDITED}
    new = sorted(unaudited - UNAUDITED_AT_BOOTSTRAP)
    assert new == [], (
        f"new unaudited override(s) {new}. An override shipped after 2026-08-02 must carry its "
        "measurements (run tools/sim/generate_attack_overrides.py) or, if the harness provably "
        "cannot fit it, be text_verified with an owning issue — see the four Issue #225 entries.")


@pytest.mark.req("REQ-PROV-0004")
def test_the_recorded_debt_may_only_SHRINK(entries):
    """The debt ledger, monotone in the same direction as the id set above — deliberately, because
    an equality here would contradict the sibling test's promise that backfilling costs no edit.
    Both unmeasured classes may fall to zero without anyone touching this file; either GROWING is
    a new debt, and a new debt is a decision someone signs for."""
    counts = {m: sum(1 for e in entries.values() if e.get("method") == m) for m in METHODS}
    assert counts[METHOD_TEXT_VERIFIED] <= 4, (
        f"{counts[METHOD_TEXT_VERIFIED]} text-verified entries (4 at bootstrap, Issue #225's). A new "
        "one is a fact shipped on a human reading rather than a measurement — legitimate when the "
        "harness provably cannot fit it, but rule it here and give it an owning issue.")
    assert counts[METHOD_UNAUDITED] <= 111, (
        f"{counts[METHOD_UNAUDITED]} unaudited entries (111 at bootstrap) — the debt grew.")


@pytest.mark.req("REQ-PROV-0001")
def test_the_sidecar_is_self_describing_and_its_prose_cannot_drift(entries):
    """Version and glossary live in the file, so a reader never has to leave it to know what a row
    claims — and a shape change fails loudly in `load_provenance` instead of being half-parsed.

    Asserted against the generator's own constants, not merely for shape. `main` re-emits
    `ABOUT`/`METHOD_DOC` rather than echoing the file back, so the module owns this prose; without
    this equality a hand-edit could leave the file describing a vocabulary the code no longer has —
    drift, in the one file built to make drift impossible.
    """
    payload = json.loads(_SIDECAR.read_text(encoding="utf-8"))
    assert payload["version"] == PROVENANCE_VERSION
    assert payload["about"] == ABOUT
    assert payload["methods"] == METHOD_DOC
    assert set(payload["methods"]) == set(METHODS), "the glossary and the vocabulary disagree"


@pytest.mark.req("REQ-PROV-0003")
def test_both_stores_are_committed_with_the_same_line_endings(table, entries):
    """Dev is Windows, the grader and CI are Linux (CLAUDE.md). `Path.write_text` translates "\\n" to
    the platform newline, so a generator that inherits it emits a different file on each OS and a
    regenerate reads as a whole-file rewrite — a 28-line edit once became a 661-line diff that way.
    The generator pins CRLF; this asserts both stores actually agree with it."""
    for path in (_TABLE, _SIDECAR):
        raw = path.read_bytes()
        assert raw.count(b"\n") == raw.count(b"\r\n"), f"{path.name} has bare LF line endings"
