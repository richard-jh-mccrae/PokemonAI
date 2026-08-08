"""A shipped override is checkable against its own evidence — `attack_overrides.json` against
`attack_overrides.provenance.json` (ADR-0108, Issue #224).

`reports/attack_audit/` is gitignored, so before the sidecar an override could only be *re-derived*,
never *checked* — which is how attack 274 shipped a scaler on a variable no measurement supported.

Structural checks over two committed files: no engine, no measurements.
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

#: Overrides already shipped when provenance became a requirement, their captures gone. Asserted as
#: a SUBSET, never an equality: backfilling one must cost no edit here, adding one must fail.
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
    """An override with no row is one nobody can check; an orphan row is a sidecar already drifting."""
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
    """THE FREEZE: editing a shipped number without touching its provenance fails here. The value
    rather than a hash, so the failure shows what moved."""
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
    """Counting axes is not enough — a `both_bench` fit wins on two by itself. What carries the
    argument is a measured axis that stayed FLAT, i.e. a variable measured and RULED OUT."""
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
    """Vacuous today, deliberately: it bites the day a recapture produces a contradicting pair.
    `_coin_bounds` keys on `coin` alone, so forks at different sweep points overwrite each other."""
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
    """A printed sentence establishes a fact and a debt at once; an unowned debt is a TODO nobody
    holds. These are owed by Issue #275."""
    for aid, e in sorted(entries.items()):
        if e.get("method") != METHOD_TEXT_VERIFIED:
            continue
        assert e.get("owner"), f"{aid}: text_verified with no owning issue"
        assert e.get("note"), f"{aid}: text_verified with no printed text to check it against"


@pytest.mark.req("REQ-PROV-0004")
def test_the_unaudited_set_may_only_shrink(entries):
    """The teeth: backfilling to `engine_fit` costs no edit here; a NEW uncheckable override fails."""
    unaudited = {aid for aid, e in entries.items() if e.get("method") == METHOD_UNAUDITED}
    new = sorted(unaudited - UNAUDITED_AT_BOOTSTRAP)
    assert new == [], (
        f"new unaudited override(s) {new}. An override shipped after 2026-08-02 must carry its "
        "measurements (run tools/sim/generate_attack_overrides.py) or, if the harness provably "
        "cannot fit it, be text_verified with an owning issue — see the four Issue #225 entries.")


@pytest.mark.req("REQ-PROV-0004")
def test_the_recorded_debt_may_only_SHRINK(entries):
    """Monotone in the same direction as the id set above; an equality would contradict the sibling
    test's promise that backfilling costs no edit."""
    counts = {m: sum(1 for e in entries.values() if e.get("method") == m) for m in METHODS}
    assert counts[METHOD_TEXT_VERIFIED] <= 4, (
        f"{counts[METHOD_TEXT_VERIFIED]} text-verified entries (4 at bootstrap, Issue #225's). A new "
        "one is a fact shipped on a human reading rather than a measurement — legitimate when the "
        "harness provably cannot fit it, but rule it here and give it an owning issue.")
    assert counts[METHOD_UNAUDITED] <= 111, (
        f"{counts[METHOD_UNAUDITED]} unaudited entries (111 at bootstrap) — the debt grew.")


@pytest.mark.req("REQ-PROV-0001")
def test_the_sidecar_is_self_describing_and_its_prose_cannot_drift(entries):
    """Asserted against the generator's own constants, not merely for shape: `main` re-emits
    `ABOUT`/`METHOD_DOC`, so a hand-edit could otherwise leave the file describing a dead vocabulary."""
    payload = json.loads(_SIDECAR.read_text(encoding="utf-8"))
    assert payload["version"] == PROVENANCE_VERSION
    assert payload["about"] == ABOUT
    assert payload["methods"] == METHOD_DOC
    assert set(payload["methods"]) == set(METHODS), "the glossary and the vocabulary disagree"


@pytest.mark.req("REQ-PROV-0003")
def test_both_stores_are_committed_with_the_same_line_endings(table, entries):
    """`Path.write_text` translates "\\n" to the platform newline, so a generator inheriting it emits
    a different file per OS and a regenerate reads as a whole-file rewrite. The generator pins CRLF."""
    for path in (_TABLE, _SIDECAR):
        raw = path.read_bytes()
        assert raw.count(b"\n") == raw.count(b"\r\n"), f"{path.name} has bare LF line endings"
