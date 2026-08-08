"""**The gate baselines' provenance tables are checkable** — `docs/ci.md` against the two
`baseline.json` files on disk (Issue #339).

The shape worth naming: a missing row is an omission a reader can detect, but a row saying *nothing
happened* when something did is an assertion that will be believed. A baseline IS a ruling record
(`CLAUDE.md`); these tables are the human-readable half of it.

**This test fails whenever someone re-stamps or re-captures without updating the doc. That is the
feature.** The fix is one line of markdown in the same commit, never a re-capture.

Deliberately structural: the recorded pin is real and the pin has a row. It does NOT validate the
`absorbed` column, which would need a git replay inside the suite.
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
    """The lines of the `### Baseline provenance` subsection that pins ``path``, delimited by the next
    heading of any level and skipping fenced blocks so a ``# comment`` in one is not a heading."""
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
    """Every `rev`-column cell of the provenance table, as a bare revision string. The italic
    parentheticals (`*(relabel only)*`, `*(pre-rebase)*`) do not match, so they need no exemption list."""
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
    """The doc's `currently pinned at` revision equals the file's own `git_rev`. Read from the FILE,
    never from the commit subject — reading the subject is what made four re-stamps look self-documenting."""
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
    """The pinned revision has a `rev`-column row of its own. Matching the TABLE rather than the section
    text is what keeps this non-vacuous, and it settles that a `restamp` gets its OWN row."""
    recorded = json.loads((_REPO / path).read_text(encoding="utf-8"))["git_rev"]
    revs = _row_revs(_provenance_section(path))
    assert recorded in revs, (
        f"`{path}` is captured at `{recorded}`, but no row of its provenance table in "
        f"`docs/ci.md` records that revision (table has: {sorted(revs)}). Every movement of a "
        "baseline owes a row saying what it absorbed and on whose ruling — including a `restamp`, "
        "which gets its own `**nothing — git_rev only, zero row changes**` row."
    )
