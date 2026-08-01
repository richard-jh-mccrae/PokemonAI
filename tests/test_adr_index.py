"""**The ADR index is checkable** — `docs/adr/README.md` against `docs/adr/` on disk.

Written 2026-08-01, after the numbering log's tenth collision turned out to be one nobody noticed.
Issue #164's fetch ADR and Issue #141's promote/retreat ADR both merged as `0073-*.md`, eleven hours
apart, and **nothing failed**: no rename, no log entry, and no Index row at all for the second one.
It sat that way for five days while 127 references across 49 files pointed at an ambiguous number.

The failure mode is that a duplicate prefix is *silent*. The temp-naming convention
(`docs/adr/README.md` §"Temp naming") stops a collision being CREATED at grill time; nothing looked
for one that already existed on disk, and the index — the file whose entire job is to be the
authoritative number→file→status map — could omit an ADR without complaint.

These are cheap structural checks, not a review of ADR content. Prior art for the style:
`tests/test_import_hygiene.py` (a repo-shape invariant asserted straight off the filesystem).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ADR_DIR = Path(__file__).resolve().parents[1] / "docs" / "adr"
_README = _ADR_DIR / "README.md"

#: `NNNN-glossary.md` is a companion vocabulary doc for `ADR-NNNN`, not an ADR of its own — stated
#: outright in the README for `0050-glossary.md`. Sharing the prefix is correct there, so the rule
#: excludes them by shape rather than by an exemption list that would have to be maintained.
_GLOSSARY = re.compile(r"^\d{4}-glossary\.md$")
_NUMBERED = re.compile(r"^(\d{4})-.+\.md$")

#: ADRs the index is KNOWN to be missing, each with the reason it is owed rather than forgotten.
#: Declared as data so a NEW gap fails this test instead of joining a silent backlog — which is
#: exactly how ADR-0100 went five days unindexed. Emptying this is unowned work (README §"⚠️ The
#: index below is incomplete", Issue #167's grill notes).
_INDEX_EXEMPT: dict[str, str] = {
    "0067": "landed on the #137 / 0a branch and never got a row; re-indexing is unowned work",
}


def _adr_numbers() -> dict[str, list[str]]:
    """``{number: [filenames]}`` for every numbered ADR on disk, glossaries excluded."""
    out: dict[str, list[str]] = {}
    for f in sorted(_ADR_DIR.glob("*.md")):
        if _GLOSSARY.match(f.name):
            continue
        m = _NUMBERED.match(f.name)
        if m:
            out.setdefault(m.group(1), []).append(f.name)
    return out


def _index_rows() -> dict[str, str]:
    """``{number: linked filename}`` from the Index table's `| [NNNN](NNNN-slug.md) |` first cell."""
    rows: dict[str, str] = {}
    for line in _README.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*\[(\d{4})\]\(([^)]+)\)\s*\|", line)
        if m:
            rows[m.group(1)] = m.group(2)
    return rows


@pytest.mark.req("REQ-ADRINDEX-0001")
def test_no_two_adrs_claim_the_same_number():
    """The check that would have caught the 0073 collision the day it merged, instead of five days
    later during an unrelated audit. A duplicate prefix makes every `ADR-NNNN` citation in the repo
    ambiguous — and the repo had 127 such citations across 49 files, 27 of which meant the other
    ADR."""
    dupes = {n: files for n, files in _adr_numbers().items() if len(files) > 1}
    assert dupes == {}, (
        "two ADRs claim one number. Resolve by the README's numbering log convention — first-MERGED "
        f"keeps it, the other renumbers past the highest on disk: {dupes}")


@pytest.mark.req("REQ-ADRINDEX-0001")
def test_every_adr_on_disk_has_an_index_row():
    """The index calls itself "the authoritative map of number → file → status". An ADR missing from
    it is invisible to anyone who trusts that claim — a reader following the index concluded the
    promote/retreat ADR did not exist, while 25 source comments cited it by number."""
    missing = sorted(set(_adr_numbers()) - set(_index_rows()) - set(_INDEX_EXEMPT))
    assert missing == [], (
        f"ADR(s) on disk with no row in docs/adr/README.md: {missing}. Add the row, or — if it is "
        "genuinely owed to someone else — declare it in `_INDEX_EXEMPT` with the reason.")


@pytest.mark.req("REQ-ADRINDEX-0001")
def test_every_index_row_points_at_a_file_that_exists():
    """The other direction. A row whose link 404s is worse than a missing row: it asserts the ADR is
    there. This is what a renumber breaks if the index is not updated with the rename."""
    broken = {n: target for n, target in _index_rows().items()
              if not (_ADR_DIR / target).is_file()}
    assert broken == {}, f"index rows pointing at missing files: {broken}"


@pytest.mark.req("REQ-ADRINDEX-0001")
def test_an_index_row_links_its_own_number():
    """`| [0093](0091-....md) |` would send every reader of 0093 to a different ADR. Cheap to
    mistype during a renumber, and invisible on read-through because both halves look plausible."""
    mismatched = {n: target for n, target in _index_rows().items()
                  if not target.startswith(f"{n}-")}
    assert mismatched == {}, f"index rows whose link does not match their number: {mismatched}"


@pytest.mark.req("REQ-ADRINDEX-0002")
def test_the_next_free_number_pointer_is_actually_free():
    """The pointer has been stale at least three times (README's own bracketed notes), which is why
    the convention says to trust a disk scan over it. That advice does not make a wrong pointer
    harmless — `/open-pr` cross-checks against it, so a pointer BELOW the highest ADR on disk hands
    the next branch a number that is already taken."""
    m = re.search(r"\*\*Next free number: (\d{4})\.\*\*", _README.read_text(encoding="utf-8"))
    assert m, "docs/adr/README.md has no 'Next free number' pointer"
    pointer, highest = int(m.group(1)), max(int(n) for n in _adr_numbers())
    assert pointer > highest, (
        f"pointer says {pointer:04d} is free, but {highest:04d} is already on disk. If a rebase or a "
        "merge moved the highest number, move the pointer past it in the same commit.")
