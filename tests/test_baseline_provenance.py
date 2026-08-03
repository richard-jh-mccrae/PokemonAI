"""**The gate baselines' provenance tables are checkable** — `docs/ci.md` against the two
`baseline.json` files on disk.

Written 2026-08-03 (Issue #339), after the leaf table went five movements stale without anything
noticing — including one movement that was a real, ruling-bearing re-capture (Issue #261's wave-2
ACCEPT) whose absorbed `OK → MISS` flips reached no reader. In the same audit the *sibling* table
turned out to be two rows stale as well, and two existing leaf rows were found asserting
**"nothing — zero row changes"** about commits that moved 49 rows and 1 row respectively.

That last shape is the one worth naming: a missing row is an omission a reader can detect, but a row
that says *nothing happened* when something did is an assertion that will be believed. `CLAUDE.md`
says a baseline **is** a ruling record; these tables are the human-readable half of it, and until now
the only thing keeping them true was the discipline of whoever re-captured — the identical reliance
ADR-0094 removed for the *write* and left in place for the *record of the write*.

**This test fails whenever someone re-stamps or re-captures without updating the doc. That is the
feature.** The fix is one line of markdown in the same commit, never a re-capture: a baseline is
ruled, not conformed.

Deliberately structural, not a content review. It checks that the recorded pin is real and that the
pin has a row — it does **not** try to validate the `absorbed` column, which would need a git replay
inside the suite and is where over-engineering would actually start. Prior art for the style:
`tests/test_adr_index.py` (a hand-maintained index checked against the filesystem it describes).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_CI_DOC = _REPO / "docs" / "ci.md"

#: The two gate baselines, by the repo-relative path `docs/ci.md` names them under.
_BASELINES = ("data/leaf_lab/baseline.json", "data/decider_lab/baseline.json")

_HEADING = re.compile(r"^#{1,6} ")
_FENCE = re.compile(r"^\s*```")


def _pin_line(path: str) -> re.Pattern[str]:
    """The lead sentence that records which revision a baseline is currently captured at."""
    return re.compile(rf"`{re.escape(path)}` is currently pinned at \*\*`([0-9a-f]{{7,40}})`")


def _doc_lines() -> list[str]:
    return _CI_DOC.read_text(encoding="utf-8").splitlines()


def _provenance_section(path: str) -> list[str]:
    """The lines of the `### Baseline provenance` subsection that pins ``path``.

    Delimited by the next heading of any level, skipping fenced code blocks so that a ``# comment``
    inside a ```bash fence cannot be mistaken for a heading.
    """
    lines = _doc_lines()
    pin = _pin_line(path)
    start = next((i for i, ln in enumerate(lines) if pin.search(ln)), None)
    if start is None:
        pytest.fail(
            f"`docs/ci.md` records no `currently pinned at` line for `{path}`. Every gate baseline "
            "needs one — it is the pointer a reader uses to reconstruct what the gate compares to."
        )
    fenced = False
    for i in range(start + 1, len(lines)):
        if _FENCE.match(lines[i]):
            fenced = not fenced
        elif not fenced and _HEADING.match(lines[i]):
            return lines[start:i]
    return lines[start:]


def _row_revs(section: list[str]) -> set[str]:
    """Every `rev`-column cell of the provenance table, as a bare revision string.

    Cells that are not a revision at all — the italic parentheticals `*(relabel only)*` and
    `*(pre-rebase)*`, which record captures whose commit was rewritten away before it reached
    `main` — simply do not match, so they need no exemption list.
    """
    revs: set[str] = set()
    for line in section:
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.fullmatch(r"`([0-9a-f]{7,40})`", cells[1])
        if m:
            revs.add(m.group(1))
    return revs


@pytest.mark.parametrize("path", _BASELINES)
def test_each_baselines_pin_matches_the_committed_file(path: str):
    """The doc's `currently pinned at` revision equals the file's own `git_rev`.

    This is the entire defect of Issue #339: `docs/ci.md` claimed `a8da62d` while the committed
    leaf baseline read `d8ef7a0`, and it would have failed the moment `d5e6b307` landed. Read from
    the file, never from the commit subject — reading the subject is exactly what made four
    consecutive re-stamps look self-documenting while the doc drifted.
    """
    recorded = json.loads((_REPO / path).read_text(encoding="utf-8"))["git_rev"]
    m = _pin_line(path).search(_CI_DOC.read_text(encoding="utf-8"))
    assert m, f"no `currently pinned at` line for `{path}` in docs/ci.md"
    documented = m.group(1)
    assert documented == recorded, (
        f"`docs/ci.md` says `{path}` is pinned at `{documented}`, but the committed file's "
        f"`git_rev` is `{recorded}`. Fix the DOC (and add the missing provenance row) — never "
        "re-capture or re-stamp the baseline to match the doc. A baseline is a ruling record."
    )


@pytest.mark.parametrize("path", _BASELINES)
def test_each_baselines_pin_appears_in_its_own_provenance_section(path: str):
    """The pinned revision has a `rev`-column row of its own in that baseline's table.

    Matching the pin against the *table* rather than against the section text is what keeps this
    non-vacuous: the lead sentence names the pin too, so a plain substring check over the section
    would pass on that sentence alone and assert nothing.

    This is also what settles the convention the two tables used to disagree on (Issue #339): a
    `restamp` gets **its own row**, it is not folded into the preceding capture's row with that
    row's revision rewritten. Rewriting a historical row edits the ruling record; appending one
    does not.
    """
    recorded = json.loads((_REPO / path).read_text(encoding="utf-8"))["git_rev"]
    revs = _row_revs(_provenance_section(path))
    assert recorded in revs, (
        f"`{path}` is captured at `{recorded}`, but no row of its provenance table in "
        f"`docs/ci.md` records that revision (table has: {sorted(revs)}). Every movement of a "
        "baseline owes a row saying what it absorbed and on whose ruling — including a `restamp`, "
        "which gets its own `**nothing — git_rev only, zero row changes**` row."
    )
